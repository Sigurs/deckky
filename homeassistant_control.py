"""Home Assistant WebSocket control for lights and other entities"""

import asyncio
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, Callable, Set

logger = logging.getLogger(__name__)

try:
    import websockets
    import aiohttp
    HA_AVAILABLE = True
except ImportError:
    HA_AVAILABLE = False
    logger.warning("websockets and aiohttp not installed. Home Assistant controls will be disabled.")


class HomeAssistantControl:
    """Controls Home Assistant via WebSocket API with real-time status monitoring"""

    def __init__(self, host: str = "localhost", port: int = 8123, access_token: str = "", ssl: bool = True):
        self.host = host
        self.port = port
        self.access_token = access_token
        self.ssl = ssl
        self.ws = None
        self.session = None
        self.connected = False

        # Entity state tracking
        self.entity_states = {}  # entity_id -> state dict
        self.light_entities = set()  # Set of light entity IDs we're tracking

        # Status change callbacks
        self.status_callbacks = []

        # WebSocket thread
        self.ws_thread = None
        self.ws_loop = None
        self.monitoring = False
        self.reconnect_interval = 5  # Seconds between reconnection attempts

        if not HA_AVAILABLE:
            logger.error("Home Assistant libraries not available. Install with: pip install websockets aiohttp")
            return

        # Start WebSocket connection in background thread
        self._start_websocket_client()

    def _get_websocket_url(self) -> str:
        """Get WebSocket URL for Home Assistant"""
        protocol = "wss" if self.ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/api/websocket"

    def _get_api_url(self) -> str:
        """Get REST API URL for Home Assistant"""
        protocol = "https" if self.ssl else "http"
        return f"{protocol}://{self.host}:{self.port}/api"

    def _start_websocket_client(self):
        """Start WebSocket client in background thread"""
        self.monitoring = True
        self.ws_thread = threading.Thread(target=self._websocket_client_thread, daemon=True)
        self.ws_thread.start()
        logger.debug("Started Home Assistant WebSocket client thread")

    def _websocket_client_thread(self):
        """WebSocket client running in background thread"""
        # Create new event loop for this thread
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)

        try:
            self.ws_loop.run_until_complete(self._websocket_client())
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")
        finally:
            self.ws_loop.close()

    async def _websocket_client(self):
        """Main WebSocket client loop"""
        while self.monitoring:
            try:
                await self._connect_websocket()
                await self._listen_websocket()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                self.connected = False
                
            if self.monitoring:
                logger.info(f"Reconnecting to Home Assistant in {self.reconnect_interval} seconds...")
                await asyncio.sleep(self.reconnect_interval)

    async def _connect_websocket(self):
        """Connect to Home Assistant WebSocket"""
        if not self.access_token:
            logger.error("Home Assistant access token not configured")
            return False

        try:
            # Connect to WebSocket
            self.ws = await websockets.connect(self._get_websocket_url())
            
            # Wait for auth required message
            auth_msg = await self.ws.recv()
            auth_data = json.loads(auth_msg)
            
            if auth_data.get('type') != 'auth_required':
                logger.error("Unexpected auth message from Home Assistant")
                return False

            # Send authentication
            auth_response = {
                "type": "auth",
                "access_token": self.access_token
            }
            await self.ws.send(json.dumps(auth_response))
            
            # Wait for auth response
            auth_result = await self.ws.recv()
            auth_result_data = json.loads(auth_result)
            
            if auth_result_data.get('type') != 'auth_ok':
                logger.error(f"Home Assistant authentication failed: {auth_result_data}")
                return False

            self.connected = True
            logger.info(f"Connected to Home Assistant WebSocket at {self.host}:{self.port}")

            # Subscribe to state changes
            await self._subscribe_to_events()
            
            # Get initial states for tracked entities
            await self._get_initial_states()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to Home Assistant WebSocket: {e}")
            return False

    async def _subscribe_to_events(self):
        """Subscribe to state change events"""
        try:
            # Subscribe to all state changes
            subscribe_msg = {
                "id": 1,
                "type": "subscribe_events",
                "event_type": "state_changed"
            }
            await self.ws.send(json.dumps(subscribe_msg))
            logger.debug("Subscribed to Home Assistant state change events")
        except Exception as e:
            logger.error(f"Failed to subscribe to Home Assistant events: {e}")

    async def _fetch_entity_state(self, entity_id: str, retry_delay: float = 0.1):
        """Fetch current state for a specific entity

        Args:
            entity_id: Entity ID to fetch state for
            retry_delay: Delay before fetching to allow HA to process state change
        """
        if not self.access_token:
            return

        # Small delay to allow Home Assistant to process the state change
        # This helps avoid race conditions where we fetch before HA updates
        if retry_delay > 0:
            await asyncio.sleep(retry_delay)

        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            url = f"{self._get_api_url()}/states/{entity_id}"

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        state_data = await response.json()
                        old_state = self.entity_states.get(entity_id, {}).get('state')
                        new_state = state_data.get('state')

                        self.entity_states[entity_id] = state_data
                        logger.info(f"Fetched updated state for {entity_id}: {old_state} -> {new_state}")

                        # Notify callbacks of state change
                        self._notify_callbacks()
                    else:
                        logger.warning(f"Failed to fetch state for {entity_id}: {response.status}")
        except Exception as e:
            logger.error(f"Error fetching state for {entity_id}: {e}")

    async def _get_initial_states(self):
        """Get initial states for all tracked entities"""
        if not self.light_entities:
            return

        try:
            # Create HTTP session for REST API
            headers = {"Authorization": f"Bearer {self.access_token}"}

            async with aiohttp.ClientSession(headers=headers) as session:
                # Get states for all tracked light entities
                for entity_id in self.light_entities:
                    try:
                        url = f"{self._get_api_url()}/states/{entity_id}"
                        async with session.get(url) as response:
                            if response.status == 200:
                                state_data = await response.json()
                                self.entity_states[entity_id] = state_data
                                logger.debug(f"Got initial state for {entity_id}: {state_data.get('state')}")
                            else:
                                logger.warning(f"Failed to get state for {entity_id}: {response.status}")
                    except Exception as e:
                        logger.error(f"Error getting state for {entity_id}: {e}")

            # Notify callbacks of initial state
            self._notify_callbacks()

        except Exception as e:
            logger.error(f"Failed to get initial Home Assistant states: {e}")

    async def _listen_websocket(self):
        """Listen for WebSocket messages"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    await self._handle_websocket_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from Home Assistant WebSocket: {e}")
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Home Assistant WebSocket connection closed")
        except Exception as e:
            logger.error(f"WebSocket listening error: {e}")

    async def _handle_websocket_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        message_type = data.get('type')

        if message_type == 'event':
            event_data = data.get('event', {})
            event_type = event_data.get('event_type')
            
            if event_type == 'state_changed':
                await self._handle_state_change(event_data)

    async def _handle_state_change(self, event_data: Dict[str, Any]):
        """Handle state change event"""
        try:
            event = event_data.get('data', {})
            entity_id = event.get('entity_id')
            
            # Only process if we're tracking this entity
            if entity_id not in self.light_entities:
                return

            new_state = event.get('new_state')
            old_state = event.get('old_state')

            if new_state:
                self.entity_states[entity_id] = new_state
                logger.debug(f"State changed for {entity_id}: {old_state.get('state') if old_state else 'None'} -> {new_state.get('state')}")
                
                # Notify callbacks of state change
                self._notify_callbacks()

        except Exception as e:
            logger.error(f"Error handling state change: {e}")

    def _notify_callbacks(self):
        """Notify all registered callbacks of status changes"""
        for callback in self.status_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in Home Assistant status callback: {e}")

    def add_status_callback(self, callback: Callable[[], None]):
        """Add a callback to be called when entity states change"""
        self.status_callbacks.append(callback)

    def track_light_entity(self, entity_id: str):
        """Start tracking a light entity for state updates"""
        self.light_entities.add(entity_id)
        logger.debug(f"Now tracking light entity: {entity_id}")
        
        # If connected, get initial state for this entity
        if self.connected and self.ws_loop:
            # Schedule the initial state fetch in the WebSocket thread
            asyncio.run_coroutine_threadsafe(
                self._get_initial_states(), 
                self.ws_loop
            )

    def untrack_light_entity(self, entity_id: str):
        """Stop tracking a light entity"""
        self.light_entities.discard(entity_id)
        if entity_id in self.entity_states:
            del self.entity_states[entity_id]
        logger.debug(f"No longer tracking light entity: {entity_id}")

    def _call_service_sync(self, domain: str, service: str, entity_id: str, **kwargs) -> bool:
        """Synchronous wrapper for calling Home Assistant service"""
        if not self.ws_loop:
            logger.error("WebSocket loop not available")
            return False

        # Check if the event loop is still running
        if self.ws_loop.is_closed():
            logger.error("WebSocket event loop is closed")
            return False

        if not self.ws_loop.is_running():
            logger.error("WebSocket event loop is not running")
            return False

        try:
            # Run the async service call in the WebSocket thread
            future = asyncio.run_coroutine_threadsafe(
                self._call_service_async(domain, service, entity_id, **kwargs),
                self.ws_loop
            )
            return future.result(timeout=10)  # 10 second timeout
        except Exception as e:
            logger.error(f"Failed to call Home Assistant service: {e}")
            return False

    async def _call_service_async(self, domain: str, service: str, entity_id: str, **kwargs) -> bool:
        """Call Home Assistant service via REST API"""
        if not self.access_token:
            logger.error("Home Assistant access token not configured")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.access_token}"}

            service_data = {"entity_id": entity_id}
            service_data.update(kwargs)

            url = f"{self._get_api_url()}/services/{domain}/{service}"

            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(url, json=service_data) as response:
                    if response.status == 200:
                        logger.info(f"Called Home Assistant service {domain}.{service} for {entity_id}")

                        # Immediately fetch updated state after successful service call
                        # This provides faster UI feedback while we wait for WebSocket event
                        await self._fetch_entity_state(entity_id)

                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to call Home Assistant service {domain}.{service}: {response.status} - {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error calling Home Assistant service {domain}.{service}: {e}")
            return False

    def toggle_light(self, entity_id: str) -> bool:
        """Toggle a light"""
        return self._call_service_sync("light", "toggle", entity_id)

    def turn_on_light(self, entity_id: str, **kwargs) -> bool:
        """Turn on a light"""
        return self._call_service_sync("light", "turn_on", entity_id, **kwargs)

    def turn_off_light(self, entity_id: str, **kwargs) -> bool:
        """Turn off a light"""
        return self._call_service_sync("light", "turn_off", entity_id, **kwargs)

    def get_light_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get current state of a light entity"""
        return self.entity_states.get(entity_id)

    def is_light_on(self, entity_id: str) -> bool:
        """Check if a light is currently on"""
        state_data = self.get_light_state(entity_id)
        if state_data:
            state = state_data.get('state')
            logger.debug(f"is_light_on({entity_id}): state='{state}'")
            return state == 'on'
        logger.warning(f"is_light_on({entity_id}): No state data available, assuming OFF")
        return False

    def setup_homeassistant_button(self, button_config: dict, create_image_callback) -> bytes:
        """Setup Home Assistant button with visual feedback based on current state

        Args:
            button_config: Button configuration dictionary
            create_image_callback: Function to create button image with text/colors

        Returns:
            Button image bytes
        """
        action = button_config.get('action')
        entity_id = button_config.get('entity_id', '')

        # Determine button appearance based on current light state
        bg_color = 'black'
        fg_color = '#7aa2f7'  # Default blue (default/off state)

        # Always use the label from button config (static label)
        label = button_config.get('label', '')

        # Check if this is a light entity and update color based on state
        if entity_id.startswith('light.'):
            is_on = self.is_light_on(entity_id)
            logger.debug(f"Button setup for {entity_id}: is_on={is_on}, label='{label}'")

            if is_on:
                fg_color = '#9ece6a'  # Green for lights that are on
            else:
                fg_color = '#7aa2f7'  # Blue for lights that are off

        # Create a button image with determined colors
        font_size = button_config.get('font_size', 'dynamic')
        return create_image_callback(label, bg_color=bg_color, fg_color=fg_color, font_size=font_size)

    def update_homeassistant_buttons(self, groups: dict, group_pages: dict, button_to_group: dict,
                                   deck, create_image_callback):
        """Update all Home Assistant buttons with current state

        Args:
            groups: Groups configuration
            group_pages: Current page for each group
            button_to_group: Mapping of button numbers to groups
            deck: Stream Deck object
            create_image_callback: Function to create button images
        """
        updated_count = 0
        for group_name, group_config in groups.items():
            pages = group_config.get('pages', {})
            button_range = group_config.get('buttons', [])

            # Get the current page for this group
            current_page = group_pages.get(group_name, 0)

            # Only update buttons on the currently visible page for this group
            if current_page not in pages:
                continue

            page_config = pages[current_page]
            page_buttons = page_config.get('buttons', {})

            for button_id, button_config in page_buttons.items():
                button_num = int(button_id)

                # Only update Home Assistant buttons
                if (button_config.get('type') == 'homeassistant' and
                    button_num in button_range):

                    entity_id = button_config.get('entity_id', '')
                    font_size = button_config.get('font_size', 'dynamic')
                    image = self.setup_homeassistant_button(button_config, create_image_callback)
                    deck.set_key_image(button_num, image)
                    updated_count += 1
                    logger.debug(f"Updated HA button {button_num} for {entity_id}")

        if updated_count > 0:
            logger.info(f"Updated {updated_count} Home Assistant button(s)")

    def disconnect(self):
        """Disconnect from Home Assistant WebSocket"""
        self.monitoring = False

        if self.ws and self.connected:
            try:
                # Schedule the disconnect in the WebSocket thread
                if self.ws_loop and not self.ws_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(self.ws.close(), self.ws_loop)
                logger.info("Disconnected from Home Assistant WebSocket")
            except Exception as e:
                logger.error(f"Error disconnecting from Home Assistant WebSocket: {e}")
            finally:
                self.connected = False
                self.ws = None

        if self.ws_thread and self.ws_thread.is_alive():
            self.ws_thread.join(timeout=2)

        # Clear the event loop reference after thread has stopped
        self.ws_loop = None
