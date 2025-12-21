"""Volume control for Pipewire/PulseAudio"""

import subprocess
import logging
import re
import threading
from functools import wraps
from typing import Callable

logger = logging.getLogger(__name__)


def require_available(default_return=None):
    """Decorator to check if volume control is available before executing method"""
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.available:
                logger.warning(f"Volume control not available for {func.__name__}")
                return default_return
            return func(self, *args, **kwargs)
        return wrapper
    return decorator


class VolumeControl:
    """Handles volume control via pactl (Pipewire/PulseAudio)"""

    def __init__(self):
        if not self._check_pactl():
            logger.warning("pactl not found - volume control will not work")
            self.available = False
        else:
            self.available = True
            logger.info("Volume control initialized (pactl)")

        # Event-based monitoring
        self.change_callbacks = []
        self.monitoring = False
        self.monitor_thread = None

        # Start monitoring if available
        if self.available:
            self._start_monitoring()

    def _check_pactl(self) -> bool:
        """Check if pactl is available"""
        try:
            subprocess.run(['pactl', '--version'], capture_output=True, check=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    def _get_default_sink(self) -> str:
        """Get the default audio sink"""
        try:
            result = subprocess.run(
                ['pactl', 'get-default-sink'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get default sink: {e}")
            return ""

    @require_available()
    def increase(self, amount: int = 5):
        """Increase volume by percentage"""
        try:
            subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'+{amount}%'],
                check=True
            )
            logger.debug(f"Increased volume by {amount}%")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to increase volume: {e}")

    @require_available()
    def decrease(self, amount: int = 5):
        """Decrease volume by percentage"""
        try:
            subprocess.run(
                ['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'-{amount}%'],
                check=True
            )
            logger.debug(f"Decreased volume by {amount}%")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to decrease volume: {e}")

    @require_available()
    def mute_toggle(self):
        """Toggle mute state"""
        try:
            subprocess.run(
                ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'],
                check=True
            )
            logger.debug("Toggled mute")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to toggle mute: {e}")

    @require_available(default_return=0)
    def get_volume(self) -> int:
        """Get current volume percentage"""
        sink = self._get_default_sink()
        if not sink:
            return 0

        try:
            result = subprocess.run(
                ['pactl', 'get-sink-volume', sink],
                capture_output=True,
                text=True,
                check=True
            )

            # Parse output like: "Volume: front-left: 65536 / 100% / 0.00 dB"
            match = re.search(r'(\d+)%', result.stdout)
            if match:
                return int(match.group(1))
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get volume: {e}")

        return 0

    def setup_volume_button(self, button_config: dict, create_image_callback, bg_color: str = 'black') -> bytes:
        """Setup volume button with visual feedback based on current state

        Args:
            button_config: Button configuration dictionary
            create_image_callback: Function to create button image with text/colors
            bg_color: Background color for the button (default: black)

        Returns:
            Button image bytes
        """
        action = button_config.get('action')

        # For display buttons, show current volume/mute status
        if action == 'display':
            volume = self.get_volume()
            is_muted = self.is_muted()

            if is_muted:
                label = f"Vol\nMuted"
                fg_color = '#f7768e'  # Tokyo Night red for muted
            else:
                label = f"Vol\n{volume}%"
                fg_color = '#7aa2f7'  # Tokyo Night blue for normal

            font_size = button_config.get('font_size', 'dynamic')
            return create_image_callback(label, bg_color=bg_color, fg_color=fg_color, font_size=font_size)

        # For other volume actions, just return the configured label
        label = button_config.get('label', '')
        font_size = button_config.get('font_size', 'dynamic')
        return create_image_callback(label, bg_color=bg_color, font_size=font_size)

    def update_volume_display(self, button_config: dict, create_image_callback) -> bytes:
        """Update a button to display current volume (legacy wrapper for backward compatibility)

        Args:
            button_config: Button configuration dictionary
            create_image_callback: Function to create button image with text

        Returns:
            Button image bytes
        """
        # Call the new setup method with default bg_color
        return self.setup_volume_button(button_config, create_image_callback)

    @require_available(default_return=False)
    def is_muted(self) -> bool:
        """Check if audio is muted"""
        sink = self._get_default_sink()
        if not sink:
            return False

        try:
            result = subprocess.run(
                ['pactl', 'get-sink-mute', sink],
                capture_output=True,
                text=True,
                check=True
            )

            return 'yes' in result.stdout.lower()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get mute state: {e}")

        return False

    def update_volume_buttons(self, groups: dict, group_pages: dict, button_to_group: dict,
                              deck, create_image_callback):
        """Update all volume display buttons with current state

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
            group_bg_color = group_config.get('bg_color', 'black')

            # Get the current page for this group
            current_page = group_pages.get(group_name, 0)

            # Only update buttons on the currently visible page for this group
            if current_page not in pages:
                continue

            page_config = pages[current_page]
            page_buttons = page_config.get('buttons', {})

            for button_id, button_config in page_buttons.items():
                button_num = int(button_id)

                # Only update volume display buttons
                if (button_config.get('type') == 'volume' and
                    button_config.get('action') == 'display' and
                    button_num in button_range):

                    image = self.setup_volume_button(button_config, create_image_callback, group_bg_color)
                    deck.set_key_image(button_num, image)

    def add_change_callback(self, callback: Callable[[], None]):
        """Add a callback to be called when volume or mute state changes"""
        self.change_callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks of volume changes"""
        for callback in self.change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in volume change callback: {e}")

    def _start_monitoring(self):
        """Start monitoring volume changes via pactl subscribe"""
        if not self.available:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_volume, daemon=True)
        self.monitor_thread.start()
        logger.debug("Started volume monitoring via pactl subscribe")

    def _monitor_volume(self):
        """Monitor volume changes using pactl subscribe"""
        process = None

        while self.monitoring:
            try:
                # pactl subscribe outputs events for all PulseAudio/Pipewire changes
                # We filter for sink (audio output) events
                process = subprocess.Popen(
                    ['pactl', 'subscribe'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1
                )

                logger.debug(f"Started pactl subscribe process (PID: {process.pid})")

                for line in process.stdout:
                    if not self.monitoring:
                        logger.debug("Monitoring stopped, terminating pactl process")
                        break

                    # Look for sink (audio output) change events
                    # Example line: "Event 'change' on sink #0"
                    if 'sink' in line.lower() and 'change' in line.lower():
                        logger.debug(f"Volume change detected: {line.strip()}")
                        self._notify_callbacks()

            except Exception as e:
                logger.error(f"Error in volume monitoring: {e}")
            finally:
                # Always clean up the process
                if process and process.poll() is None:
                    try:
                        process.terminate()
                        # Give it a moment to terminate gracefully
                        import time
                        time.sleep(0.1)

                        # Force kill if still running
                        if process.poll() is None:
                            process.kill()
                            logger.debug("Force killed pactl subscribe process")

                        process.wait(timeout=1)
                    except Exception as cleanup_error:
                        logger.error(f"Error cleaning up pactl process: {cleanup_error}")

                # Ensure process is fully cleaned up before continuing
                if process:
                    try:
                        # Final verification that process is dead
                        process.wait(timeout=0.5)
                        logger.debug(f"pactl subscribe process (PID: {process.pid}) terminated successfully")
                    except:
                        pass
                    process = None

                # Wait before retrying if we're still monitoring
                if self.monitoring:
                    import time
                    time.sleep(2)
                    logger.debug("Restarting volume monitoring")

    def stop_monitoring(self):
        """Stop volume monitoring"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
