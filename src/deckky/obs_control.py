"""OBS WebSocket control for scene switching and recording/streaming"""

import logging
import socket
import threading
import time
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

try:
    import obswebsocket
    from obswebsocket import obsws, events, requests
    OBS_AVAILABLE = True
except ImportError:
    OBS_AVAILABLE = False
    logger.warning("obs-websocket-py not installed. OBS controls will be disabled.")


class OBSControl:
    """Controls OBS via WebSocket connection with event-based status monitoring"""

    def __init__(self, host: str = "localhost", port: int = 4455, password: str = "", poll_interval: int = 1):
        self.host = host
        self.port = port
        self.password = password
        self.poll_interval = poll_interval  # Only used for reconnection attempts now
        self.ws = None
        self.connected = False

        # Status tracking
        self.current_scene = None
        self.is_recording = False
        self.is_streaming = False

        # Status change callbacks
        self.status_callbacks = []

        # Reconnection thread
        self.reconnection_thread = None
        self.monitoring = False

        if not OBS_AVAILABLE:
            logger.error("OBS WebSocket library not available. Install with: pip install obs-websocket-py")
            return

        # Check if OBS is actually running before attempting connection
        if self._is_obs_running():
            # Try initial connection
            self._connect()
            # Get initial state
            self._get_initial_state()
        else:
            logger.info(f"OBS WebSocket server not detected at {self.host}:{self.port}, will retry when OBS starts")

        # Start reconnection monitor (will connect when OBS becomes available)
        self._start_reconnection_monitor()

    def _is_obs_running(self) -> bool:
        """Check if OBS WebSocket server is listening on the configured port"""
        try:
            # Try to connect to the port with a short timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)  # 500ms timeout
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result == 0
        except Exception as e:
            logger.debug(f"OBS port check failed: {e}")
            return False

    def _connect(self) -> bool:
        """Connect to OBS WebSocket and register event handlers"""
        if not OBS_AVAILABLE:
            return False

        try:
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            logger.info(f"Connected to OBS WebSocket at {self.host}:{self.port}")

            # Register event handlers for real-time updates
            self._register_event_handlers()

            return True
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to OBS WebSocket at {self.host}:{self.port}: {e}")
            return False

    def _register_event_handlers(self):
        """Register OBS event callbacks for real-time status updates"""
        if not self.ws:
            return

        try:
            # Register handlers for scene changes
            self.ws.register(self._on_scene_changed, events.CurrentProgramSceneChanged)

            # Register handlers for recording state changes
            self.ws.register(self._on_record_state_changed, events.RecordStateChanged)

            # Register handlers for streaming state changes
            self.ws.register(self._on_stream_state_changed, events.StreamStateChanged)

            logger.debug("Registered OBS event handlers")
        except Exception as e:
            logger.error(f"Failed to register OBS event handlers: {e}")

    def _get_initial_state(self):
        """Get initial OBS state before starting monitoring"""
        if not self.connected:
            logger.warning("OBS not connected, skipping initial state fetch")
            return
            
        try:
            # Get initial state
            current_scene = self.get_current_scene()
            recording_status = self.get_recording_status()
            streaming_status = self.get_streaming_status()

            # Set initial tracked status
            if current_scene:
                self.current_scene = current_scene
                logger.debug(f"Initial OBS scene: {current_scene}")
            
            if recording_status:
                self.is_recording = recording_status.get('isRecording', False)
                logger.debug(f"Initial OBS recording state: {self.is_recording}")
            
            if streaming_status:
                self.is_streaming = streaming_status.get('isActive', False)
                logger.debug(f"Initial OBS streaming state: {self.is_streaming}")
                
        except Exception as e:
            logger.error(f"Failed to get initial OBS state: {e}")
            # Don't let OBS connection failures break the entire application
            logger.warning("OBS connection issues detected, continuing with limited functionality")

    def _on_scene_changed(self, event):
        """Event handler for scene changes"""
        try:
            scene_name = event.getSceneName()
            if scene_name != self.current_scene:
                logger.debug(f"Scene changed: {self.current_scene} -> {scene_name}")
                self.current_scene = scene_name
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling scene change event: {e}")

    def _on_record_state_changed(self, event):
        """Event handler for recording state changes"""
        try:
            # Event has outputActive field for recording state
            is_active = event.getOutputActive()
            if is_active != self.is_recording:
                logger.debug(f"Recording state changed: {self.is_recording} -> {is_active}")
                self.is_recording = is_active
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling recording state change event: {e}")

    def _on_stream_state_changed(self, event):
        """Event handler for streaming state changes"""
        try:
            # Event has outputActive field for streaming state
            is_active = event.getOutputActive()
            if is_active != self.is_streaming:
                logger.debug(f"Streaming state changed: {self.is_streaming} -> {is_active}")
                self.is_streaming = is_active
                self._notify_callbacks()
        except Exception as e:
            logger.error(f"Error handling streaming state change event: {e}")

    def _notify_callbacks(self):
        """Notify all registered callbacks of status changes"""
        for callback in self.status_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def _start_reconnection_monitor(self):
        """Start reconnection monitoring thread (only attempts reconnect when disconnected)"""
        if not OBS_AVAILABLE:
            return

        self.monitoring = True
        self.reconnection_thread = threading.Thread(target=self._reconnection_monitor, daemon=True)
        self.reconnection_thread.start()
        logger.debug("Started OBS reconnection monitor")

    def _reconnection_monitor(self):
        """Monitor connection and attempt reconnection if disconnected"""
        reconnect_interval = 5  # Seconds between reconnection attempts

        while self.monitoring:
            # Only attempt reconnection if disconnected
            if not self.connected:
                # First check if OBS is actually running before attempting connection
                if self._is_obs_running():
                    logger.info("OBS WebSocket server detected, attempting to connect...")
                    if self._connect():
                        # Successfully reconnected, get initial state
                        self._get_initial_state()
                        # Notify callbacks to update button states
                        self._notify_callbacks()
                    else:
                        # Connection failed despite port being open, wait before trying again
                        time.sleep(reconnect_interval)
                        continue
                else:
                    # OBS not running, wait before checking again
                    time.sleep(reconnect_interval)
                    continue

            # When connected, just sleep and check periodically
            time.sleep(reconnect_interval)

    def add_status_callback(self, callback: Callable[[], None]):
        """Add a callback to be called when OBS status changes"""
        self.status_callbacks.append(callback)

    def _ensure_connected(self) -> bool:
        """Ensure WebSocket connection is active"""
        if not self.connected or not self.ws:
            return self._connect()

        # Try a simple ping to check if connection is still alive
        try:
            self.ws.call(requests.GetVersion())
            return True
        except Exception:
            # Connection is dead, try to reconnect
            self.connected = False
            return self._connect()

    def switch_scene(self, scene_name: str) -> bool:
        """Switch to specified scene"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.SetCurrentProgramScene(sceneName=scene_name))
            logger.info(f"Switched to OBS scene: {scene_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to switch OBS scene to '{scene_name}': {e}")
            return False

    def toggle_recording(self) -> bool:
        """Toggle recording based on current state"""
        if self.is_recording:
            return self.stop_recording()
        else:
            return self.start_recording()

    def toggle_streaming(self) -> bool:
        """Toggle streaming based on current state"""
        if self.is_streaming:
            return self.stop_streaming()
        else:
            return self.start_streaming()

    def start_recording(self) -> bool:
        """Start recording"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StartRecord())
            logger.info("Started OBS recording")
            return True
        except Exception as e:
            logger.error(f"Failed to start OBS recording: {e}")
            return False

    def stop_recording(self) -> bool:
        """Stop recording"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StopRecord())
            logger.info("Stopped OBS recording")
            return True
        except Exception as e:
            logger.error(f"Failed to stop OBS recording: {e}")
            return False

    def start_streaming(self) -> bool:
        """Start streaming"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StartStream())
            logger.info("Started OBS streaming")
            return True
        except Exception as e:
            logger.error(f"Failed to start OBS streaming: {e}")
            return False

    def stop_streaming(self) -> bool:
        """Stop streaming"""
        if not self._ensure_connected():
            return False

        try:
            self.ws.call(requests.StopStream())
            logger.info("Stopped OBS streaming")
            return True
        except Exception as e:
            logger.error(f"Failed to stop OBS streaming: {e}")
            return False

    def get_current_scene(self) -> Optional[str]:
        """Get current scene name"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetCurrentProgramScene())
            return result.getCurrentProgramSceneName()
        except Exception as e:
            logger.error(f"Failed to get current OBS scene: {e}")
            return None

    def get_recording_status(self) -> Optional[Dict[str, Any]]:
        """Get recording status"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetRecordStatus())
            return {
                'isRecording': result.getOutputActive(),
                'paused': result.getOutputPaused(),
                'timecode': result.getOutputTimecode(),
                'duration': result.getOutputDuration()
            }
        except Exception as e:
            logger.error(f"Failed to get OBS recording status: {e}")
            return None

    def get_streaming_status(self) -> Optional[Dict[str, Any]]:
        """Get streaming status"""
        if not self._ensure_connected():
            return None

        try:
            result = self.ws.call(requests.GetStreamStatus())
            return {
                'isActive': result.getOutputActive(),
                'timecode': result.getOutputTimecode(),
                'duration': result.getOutputDuration()
            }
        except Exception as e:
            logger.error(f"Failed to get OBS streaming status: {e}")
            return None

    def setup_obs_button(self, button_config: dict, create_image_callback, bg_color: str = 'black') -> bytes:
        """Setup OBS button with visual feedback based on current state

        Args:
            button_config: Button configuration dictionary
            create_image_callback: Function to create button image with text/colors
            bg_color: Background color for the button (default: black)

        Returns:
            Button image bytes
        """
        action = button_config.get('action')
        scene_name = button_config.get('scene', '')

        # Determine button appearance based on current OBS state
        fg_color = '#7aa2f7'  # Default blue
        
        # Initialize label with default from button config
        label = button_config.get('label', '')
        
        if action == 'scene_switch' and scene_name:
            # Green text if this scene is currently active (case-insensitive comparison)
            current_scene_normalized = self.current_scene.strip().lower() if self.current_scene else None
            button_scene_normalized = scene_name.strip().lower()

            logger.debug(f"Scene button check: button_scene='{scene_name}', current_scene='{self.current_scene}', match={current_scene_normalized == button_scene_normalized}")

            if current_scene_normalized == button_scene_normalized:
                fg_color = '#9ece6a'  # Green for active scene
                logger.debug(f"Scene '{scene_name}' is active, highlighting button")
        
        elif action in ['toggle_recording', 'start_recording', 'stop_recording']:
            # Red text if recording is active
            if self.is_recording:
                fg_color = '#f7768e'  # Red for active recording
                if action == 'toggle_recording':
                    label = "Stop\nRecord"
                else:
                    label = "Recording"
            else:
                if action == 'toggle_recording':
                    label = "Start\nRecord"
                else:
                    label = button_config.get('label', 'Record')
        
        elif action in ['toggle_streaming', 'start_streaming', 'stop_streaming']:
            # Red text if streaming is active
            if self.is_streaming:
                fg_color = '#f7768e'  # Red for active streaming
                if action == 'toggle_streaming':
                    label = "Stop\nStream"
                else:
                    label = "Streaming"
            else:
                if action == 'toggle_streaming':
                    label = "Start\nStream"
                else:
                    label = button_config.get('label', 'Stream')
        
        # Create a button image with determined colors
        font_size = button_config.get('font_size', 'dynamic')
        return create_image_callback(label, bg_color=bg_color, fg_color=fg_color, font_size=font_size)

    def update_obs_buttons(self, groups: dict, group_pages: dict, button_to_group: dict,
                           deck, create_image_callback):
        """Update all OBS buttons with current state

        Args:
            groups: Groups configuration
            group_pages: Current page for each group
            button_to_group: Mapping of button numbers to groups
            deck: Stream Deck object
            create_image_callback: Function to create button images
        """
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

                # Only update OBS buttons
                if (button_config.get('type') == 'obs' and
                    button_num in button_range):

                    font_size = button_config.get('font_size', 'dynamic')
                    image = self.setup_obs_button(button_config, create_image_callback)
                    deck.set_key_image(button_num, image)

    def disconnect(self):
        """Disconnect from OBS WebSocket"""
        self.monitoring = False
        if self.reconnection_thread:
            self.reconnection_thread.join(timeout=2)
            
        if self.ws and self.connected:
            try:
                self.ws.disconnect()
                logger.info("Disconnected from OBS WebSocket")
            except Exception as e:
                logger.error(f"Error disconnecting from OBS WebSocket: {e}")
            finally:
                self.connected = False
                self.ws = None
