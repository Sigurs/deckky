"""DLZ Creator pad control for Stream Deck"""

import asyncio
import logging
import threading
import time
from typing import Dict, Any, Callable, List, Optional
from deckky.dlz_creator_client import DLZCreatorClient, DLZPad

logger = logging.getLogger(__name__)


class DLZControl:
    """Manages DLZ Creator pad control and status tracking"""

    def __init__(self, host: str = "localhost"):
        """Initialize DLZ Control
        
        Args:
            host: DLZ Creator WebSocket server host
        """
        self.host = host
        self.client = DLZCreatorClient(host=host)
        self.connected = False
        self.pads: List[DLZPad] = []
        self.status_callback: Optional[Callable] = None
        
        # Register update callback with client
        self.client.update_callback = self._on_pad_update
        
        # Start connection in background thread
        self._connection_thread = None
        self._running = False
        self._start_connection()

    def _start_connection(self):
        """Start DLZ connection in background thread"""
        self._running = True
        self._connection_thread = threading.Thread(target=self._run_connection_loop, daemon=True)
        self._connection_thread.start()
        logger.info(f"DLZ Control connection thread started for {self.host}")

    def _run_connection_loop(self):
        """Run the asyncio connection loop in a background thread"""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the connection
            loop.run_until_complete(self.client.connect_and_listen())
        except Exception as e:
            logger.error(f"DLZ connection error: {e}")
        finally:
            self._running = False
            self.connected = False
            try:
                loop.close()
            except:
                pass

    def get_pads(self) -> List[DLZPad]:
        """Get list of available pads from DLZ Creator
        
        Returns:
            List of DLZPad objects
        """
        return self.client.pads

    def get_pad_for_button(self, button_index: int) -> Optional[DLZPad]:
        """Get the DLZ pad that should be displayed on a specific button
        
        Args:
            button_index: Button index within the dlz_pads group (0-based)
            
        Returns:
            DLZPad object or None if no pad available for this button
        """
        pads = self.get_pads()
        if 0 <= button_index < len(pads):
            return pads[button_index]
        return None

    def play_pad(self, button_index: int) -> bool:
        """Trigger playback for a pad
        
        Args:
            button_index: Button index within the dlz_pads group
            
        Returns:
            True if successful, False otherwise
        """
        pad = self.get_pad_for_button(button_index)
        if pad:
            success = self.client.play_sync(pad)
            if success:
                logger.info(f"Triggered DLZ pad: {pad.name} (Bank {pad.bank}, Pad {pad.pad})")
                # Wait for pad to actually reach playing state before refreshing UI
                # Poll for up to 1 second for the state to update
                timeout = 1.0  # seconds
                poll_interval = 0.05  # 50ms between checks
                elapsed = 0.0
                
                while elapsed < timeout:
                    if self.is_pad_playing(pad):
                        logger.debug(f"Pad {pad.name} confirmed playing after {elapsed:.3f}s")
                        break
                    time.sleep(poll_interval)
                    elapsed += poll_interval
                
                # Trigger status update to refresh button appearances
                # This will show the updated playing status
                if self.status_callback:
                    self.status_callback()
            return success
        else:
            logger.warning(f"No DLZ pad configured for button {button_index}")
            return False

    def is_pad_playing(self, pad: DLZPad) -> bool:
        """Check if a pad is currently playing
        
        Args:
            pad: DLZPad object to check
            
        Returns:
            True if pad is playing (active == 1), False otherwise
        """
        return pad.active == 1

    def add_status_callback(self, callback: Callable):
        """Add a callback function to be called when pad status changes
        
        Args:
            callback: Function to call when status changes
        """
        self.status_callback = callback

    def _on_pad_update(self):
        """Internal callback called by client when any pad data changes
        
        This is triggered by DLZCreatorClient whenever pad properties are updated
        (name, state, curtime, etc.) and triggers a visual refresh of all DLZ buttons.
        """
        logger.debug("DLZ pad data updated, triggering visual refresh")
        # Trigger the external status callback to refresh button appearances
        if self.status_callback:
            self.status_callback()

    def setup_dlz_button(self, button_config: Dict[str, Any], 
                        create_image_callback: Callable,
                        button_index: int):
        """Set up a DLZ pad button with appropriate label and appearance
        
        Args:
            button_config: Button configuration dictionary
            create_image_callback: Function to create button images
            button_index: Button index within the dlz_pads group
            
        Returns:
            Button image bytes, or None if no pad configured
        """
        pad = self.get_pad_for_button(button_index)
        
        if pad:
            # Use pad name as label
            label = pad.name if pad.name else f"B{pad.bank}.P{pad.pad}"
            
            # Use black background (like Home Assistant lights)
            bg_color = 'black'
            
            # Show visual feedback if pad is playing (green text, like HA lights when on)
            if self.is_pad_playing(pad):
                fg_color = '#9ece6a'  # Green for playing pads
            else:
                fg_color = '#7aa2f7'  # Blue for stopped pads
            
            # Create button image with determined colors
            font_size = button_config.get('font_size', 'dynamic')
            image = create_image_callback(label, bg_color=bg_color, fg_color=fg_color, font_size=font_size)
        else:
            # No pad configured for this button - return None to leave button blank
            return None
        
        return image

    def update_dlz_buttons(self, groups: Dict[str, Any], 
                          group_pages: Dict[str, int],
                          button_to_group: Dict[int, str],
                          deck,
                          create_image_callback: Callable):
        """Update all DLZ pad buttons with current playing status
        
        Args:
            groups: Groups configuration dictionary
            group_pages: Current page for each group
            button_to_group: Mapping of button numbers to group names
            deck: StreamDeck instance
            create_image_callback: Function to create button images
        """
        # Check if connection to DLZ Creator is active
        is_connected = self.client.is_connected
        
        if not is_connected:
            logger.debug("DLZ Creator connection lost, clearing DLZ buttons")
        
        for group_name, group_config in groups.items():
            # Check if this group has DLZ pads
            buttons = group_config.get('buttons', [])
            
            for button_num in buttons:
                # Check if this button is in the dlz_pads group
                if button_to_group.get(button_num) == group_name:
                    # Get current page config
                    page_num = group_pages.get(group_name, 0)
                    pages = group_config.get('pages', {})
                    page_config = pages.get(page_num, {})
                    page_buttons = page_config.get('buttons', {})
                    
                    # Check if this button is a DLZ pad button
                    button_config = page_buttons.get(str(button_num))
                    if button_config and button_config.get('type') == 'dlz_pad':
                        # Update this button
                        logger.debug(f"Updating DLZ button {button_num} in group '{group_name}'")
                        
                        if is_connected:
                            # Connection is active - show pad status
                            # Calculate button index within group (for pad mapping)
                            button_index = buttons.index(button_num)
                            
                            # Create new image and update button (only if pad is available)
                            image = self.setup_dlz_button(
                                button_config, 
                                create_image_callback,
                                button_index
                            )
                            # Only update if image is not None (pad exists)
                            if image:
                                deck.set_key_image(button_num, image)
                        else:
                            # Connection is lost - clear the button
                            logger.debug(f"Clearing DLZ button {button_num} (disconnected)")
                            deck.set_key_image(button_num, create_image_callback('', bg_color='black', fg_color='black'))

    def disconnect(self):
        """Disconnect from DLZ Creator"""
        self._running = False
        if self._connection_thread and self._connection_thread.is_alive():
            self._connection_thread.join(timeout=2.0)
        self.connected = False
        logger.info("DLZ Control disconnected")
