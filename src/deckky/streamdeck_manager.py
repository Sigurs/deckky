"""Stream Deck device manager"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Any
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.ImageHelpers import PILHelper
from PIL import Image, ImageDraw, ImageFont
from deckky.action_handler import ActionHandler
from deckky.config_loader import ConfigLoader
from deckky.volume_control import VolumeControl

logger = logging.getLogger(__name__)

# Try to import inotify for efficient file watching
try:
    from inotify_simple import INotify, flags
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False
    logger.warning("inotify_simple not installed. Using polling for config file changes. Install with: pip install inotify_simple")


class StreamDeckManager:
    """Manages Stream Deck device connection and events"""

    def __init__(self, config: Dict[str, Any], config_path: Path = Path("config.yaml")):
        self.config = config
        self.config_path = config_path
        self.deck = None
        self.action_handler = ActionHandler(config)
        self.volume_control = VolumeControl()
        self.button_states = {}
        self.config_last_modified = config_path.stat().st_mtime if config_path.exists() else 0
        self.config_lock = threading.Lock()
        self.running = True
        self.group_pages = {}  # Track current page for each group: {group_name: page_num}
        self.button_to_group = {}  # Map button numbers to their group: {button_num: group_name}
        self.groups = {}  # Store group configurations

        # Performance caches
        self.font_cache = {}  # Cache loaded fonts: {(font_path, size): font_object}
        self.available_font_path = None  # First available font path (cached)
        self.image_cache = {}  # Cache generated images: {(text, bg, fg, size): image_bytes}

        # Font configuration
        self.font_paths = self._get_font_paths()

        # Page switch hold-to-home tracking
        self.page_switch_timers = {}  # Track hold timers for page switch buttons: {button_id: timer}

    def run(self):
        """Initialize and run the Stream Deck manager"""
        streamdecks = DeviceManager().enumerate()

        if not streamdecks:
            raise RuntimeError("No Stream Deck devices found")

        self.deck = streamdecks[0]
        self.deck.open()

        # Give the USB device a moment to stabilize after opening
        time.sleep(0.1)

        # Try to reset the device, but don't fail if it errors
        # Some USB controllers have issues with the reset command
        try:
            self.deck.reset()
        except Exception as e:
            logger.warning(f"Failed to reset Stream Deck (continuing anyway): {e}")

        logger.info(f"Connected to {self.deck.deck_type()} "
                   f"({self.deck.key_count()} keys)")

        # Set brightness
        brightness = self.config.get('streamdeck', {}).get('brightness', 80)
        try:
            self.deck.set_brightness(brightness)
        except Exception as e:
            logger.warning(f"Failed to set brightness (continuing anyway): {e}")

        # Set up OBS status callback for visual feedback BEFORE initializing buttons
        if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
            self.action_handler.obs_control.add_status_callback(self._on_obs_status_change)
            # Small delay to ensure OBS initial state is fetched
            time.sleep(0.5)

        # Set up Home Assistant status callback for visual feedback BEFORE initializing buttons
        if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
            self.action_handler.ha_control.add_status_callback(self._on_ha_status_change)
            # Pre-track all Home Assistant entities from config to ensure initial states are fetched
            self._track_all_ha_entities()
            # Longer delay to ensure Home Assistant initial states are fetched
            time.sleep(2.0)

        # Initialize buttons (now OBS and HA states will be available)
        self._initialize_buttons()

        # Force an OBS button refresh to ensure proper highlighting
        if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
            self._on_obs_status_change()

        # Force a Home Assistant button refresh to ensure proper highlighting
        if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
            self._on_ha_status_change()

        # Set up volume change callback for event-based updates
        self.volume_control.add_change_callback(self._on_volume_change)

        # Register button callback
        self.deck.set_key_callback(self._key_change_callback)

        # Start config file watcher thread
        config_watcher = threading.Thread(target=self._watch_config_file, daemon=True)
        config_watcher.start()

        logger.info("Stream Deck ready. Press Ctrl+C to exit.")
        logger.info("Config file auto-reload enabled")

        # Keep running
        try:
            while self.running:
                time.sleep(0.1)
        finally:
            self._cleanup()

    def _track_all_ha_entities(self):
        """Pre-track all Home Assistant entities from config to ensure initial states are fetched"""
        if not hasattr(self.action_handler, 'ha_control') or not self.action_handler.ha_control:
            return

        ha_control = self.action_handler.ha_control
        groups = self.config.get('groups', {})

        for group_name, group_config in groups.items():
            pages = group_config.get('pages', {})
            
            for page_num, page_config in pages.items():
                page_buttons = page_config.get('buttons', {})
                
                for button_id, button_config in page_buttons.items():
                    if button_config.get('type') == 'homeassistant':
                        entity_id = button_config.get('entity_id')
                        if entity_id and entity_id.startswith('light.'):
                            logger.debug(f"Pre-tracking Home Assistant entity: {entity_id}")
                            ha_control.track_light_entity(entity_id)

    def _get_font_paths(self) -> list:
        """Get font paths from config or use defaults

        Expands ~ to user home directory in all paths.
        """
        # Try to get custom font paths from config
        custom_fonts = self.config.get('streamdeck', {}).get('font_paths', [])

        if custom_fonts and isinstance(custom_fonts, list):
            # Expand ~ in custom font paths
            expanded_fonts = [str(Path(font_path).expanduser()) for font_path in custom_fonts]
            logger.debug(f"Using custom font paths from config: {len(expanded_fonts)} fonts")
            return expanded_fonts

        # Default font paths (already absolute, but expand ~ just in case)
        default_fonts = [
            "~/.local/share/fonts/FiraCodeSigurs/FiraCodeSigurs-SemiBold.ttf",
            "/usr/share/fonts/adobe-source-code-pro/SourceCodePro-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        ]
        # Expand ~ in default font paths too
        expanded_defaults = [str(Path(font_path).expanduser()) for font_path in default_fonts]
        logger.debug(f"Using default font paths: {len(expanded_defaults)} fonts")
        return expanded_defaults

    def _initialize_buttons(self):
        """Initialize all configured buttons with labels"""
        self.groups = self.config['groups']
        logger.info(f"Using spatial group system with {len(self.groups)} groups")

        # Clear all buttons on the deck first (important for config reloads)
        self._clear_all_buttons()

        # Build button-to-group mapping and initialize each group to page 0
        self.button_to_group = {}
        self.group_pages = {}

        for group_name, group_config in self.groups.items():
            # Initialize each group to page 0
            self.group_pages[group_name] = 0

            # Map buttons to this group
            button_range = group_config.get('buttons', [])
            for button_num in button_range:
                self.button_to_group[button_num] = group_name

            logger.info(f"Group '{group_name}' owns buttons {button_range}")

        # Load all groups at their initial pages
        self._load_all_groups()

    def _load_all_groups(self):
        """Load all groups at their current pages"""
        for group_name in self.groups.keys():
            page_num = self.group_pages.get(group_name, 0)
            self._load_group_page(group_name, page_num)

    def _load_group_page(self, group_name: str, page_num: int):
        """Load a specific page for a specific group (only updates that group's buttons)"""
        if group_name not in self.groups:
            logger.error(f"Group '{group_name}' not found!")
            return

        group_config = self.groups[group_name]
        pages = group_config.get('pages', {})
        button_range = group_config.get('buttons', [])

        if page_num not in pages:
            logger.warning(f"Page {page_num} not found in group '{group_name}', using page 0")
            page_num = 0
            if page_num not in pages:
                logger.error(f"No pages configured in group '{group_name}'!")
                return

        # Update the current page for this group
        self.group_pages[group_name] = page_num

        page_config = pages[page_num]
        page_buttons = page_config.get('buttons', {})

        logger.info(f"Loading group '{group_name}', page {page_num}: {page_config.get('name', 'Unnamed')}")

        # Clear buttons in this group's range that aren't configured
        configured_in_page = set(int(btn_id) for btn_id in page_buttons.keys())
        for button_num in button_range:
            if button_num not in configured_in_page:
                self.deck.set_key_image(button_num, self._create_blank_image())

        # Load buttons for this page
        for button_id, button_config in page_buttons.items():
            button_num = int(button_id)

            # Verify button belongs to this group
            if button_num not in button_range:
                logger.warning(f"Button {button_num} in group '{group_name}' page {page_num} "
                             f"is outside group's button range {button_range}")
                continue

            label = button_config.get('label', '')
            font_size = button_config.get('font_size', 'dynamic')
            button_type = button_config.get('type', '')
            action = button_config.get('action', '')

            logger.debug(f"Button {button_num}: type={button_type}, label='{label}'")

            # Get group background color if specified
            group_bg_color = group_config.get('bg_color', 'black')

            # Handle page_switch buttons
            if button_type == 'page_switch':
                target_page = button_config.get('page', 0)
                target_group = button_config.get('group', group_name)  # Default to current group
                page_label = label if label else f"Page\n{target_page}"
                image = self._create_button_image(page_label, bg_color=group_bg_color, font_size=font_size)
                self.deck.set_key_image(button_num, image)
            # Handle OBS buttons with visual feedback
            elif button_type == 'obs':
                if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
                    logger.debug(f"Setting up OBS button {button_num}: {button_config}")
                    image = self.action_handler.obs_control.setup_obs_button(
                        button_config, self._create_button_image, group_bg_color
                    )
                    self.deck.set_key_image(button_num, image)
            # Handle Home Assistant buttons with visual feedback
            elif button_type == 'homeassistant':
                if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
                    logger.debug(f"Setting up Home Assistant button {button_num}: {button_config}")
                    image = self.action_handler.ha_control.setup_homeassistant_button(
                        button_config, self._create_button_image
                    )
                    self.deck.set_key_image(button_num, image)
            # Handle volume buttons with visual feedback
            elif button_type == 'volume':
                logger.debug(f"Setting up volume button {button_num}: {button_config}")
                image = self.volume_control.setup_volume_button(
                    button_config, self._create_button_image, group_bg_color
                )
                self.deck.set_key_image(button_num, image)
            elif label:
                image = self._create_button_image(label, bg_color=group_bg_color, font_size=font_size)
                self.deck.set_key_image(button_num, image)


    def _on_obs_status_change(self):
        """Callback for OBS status changes - update button appearances"""
        if not self.running:
            return
            
        # Use OBS control module to update all OBS buttons
        if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
            self.action_handler.obs_control.update_obs_buttons(
                self.groups, self.group_pages, self.button_to_group, 
                self.deck, self._create_button_image
            )

    def _on_ha_status_change(self):
        """Callback for Home Assistant status changes - update button appearances"""
        if not self.running:
            return
            
        # Use Home Assistant control module to update all HA buttons
        if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
            self.action_handler.ha_control.update_homeassistant_buttons(
                self.groups, self.group_pages, self.button_to_group, 
                self.deck, self._create_button_image
            )

    def switch_page(self, group_name: str, page_num: int):
        """Switch to a different page within a specific group"""
        logger.info(f"Switching group '{group_name}' to page {page_num}")
        self._load_group_page(group_name, page_num)

    def _create_blank_image(self) -> bytes:
        """Create a blank black button image"""
        image = Image.new('RGB', self.deck.key_image_format()['size'], 'black')
        return PILHelper.to_native_format(self.deck, image)

    def _clear_all_buttons(self):
        """Clear all buttons on the Stream Deck"""
        blank_image = self._create_blank_image()
        key_count = self.deck.key_count()
        for key in range(key_count):
            self.deck.set_key_image(key, blank_image)
        logger.debug(f"Cleared all {key_count} buttons")

    def _load_font_cached(self, font_paths: list, size: int):
        """Load a font with caching to avoid repeated file I/O

        Args:
            font_paths: List of font file paths to try
            size: Font size in pixels

        Returns:
            Font object or None if no font could be loaded
        """
        # Try to use cached available font path first
        if self.available_font_path:
            cache_key = (self.available_font_path, size)
            if cache_key in self.font_cache:
                return self.font_cache[cache_key]

            try:
                font = ImageFont.truetype(self.available_font_path, size)
                self.font_cache[cache_key] = font
                return font
            except (OSError, IOError):
                # Cached font path no longer works, clear it
                self.available_font_path = None

        # Find and cache an available font path
        for font_path in font_paths:
            cache_key = (font_path, size)

            # Check if already in cache
            if cache_key in self.font_cache:
                self.available_font_path = font_path
                return self.font_cache[cache_key]

            # Try to load this font
            try:
                font = ImageFont.truetype(font_path, size)
                self.font_cache[cache_key] = font
                self.available_font_path = font_path  # Cache working path
                return font
            except (OSError, IOError):
                continue

        return None

    def _create_button_image(self, text: str, bg_color: str = 'black',
                            fg_color: str = '#7aa2f7', font_size='dynamic') -> bytes:
        """Create a button image with text label

        Args:
            text: Text to display on button
            bg_color: Background color (hex or name)
            fg_color: Foreground/text color (hex or name)
            font_size: Font size in pixels, or 'dynamic' to auto-fit with padding
        """
        # Check cache first (skip for dynamic size as text might vary)
        if font_size != 'dynamic':
            cache_key = (text, bg_color, fg_color, font_size)
            if cache_key in self.image_cache:
                return self.image_cache[cache_key]

        # Get the image size for this deck
        image = Image.new('RGB', self.deck.key_image_format()['size'], bg_color)
        draw = ImageDraw.Draw(image)

        # Use configured font paths
        font_paths = self.font_paths

        # Determine font size
        if font_size == 'dynamic':
            # Start with a reasonable size and adjust down if needed
            target_font_size = self._calculate_dynamic_font_size(
                text, image.width, image.height, font_paths, draw
            )
        else:
            target_font_size = int(font_size)

        # Load font with determined size (with caching)
        font = self._load_font_cached(font_paths, target_font_size)

        if font is None:
            # Fall back to default (small, but better than nothing)
            font = ImageFont.load_default()

        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Calculate position for centered text
        # Adjust for bbox offset to properly center the text
        position = (
            (image.width - text_width) // 2 - bbox[0],
            (image.height - text_height) // 2 - bbox[1]
        )

        # Draw text with proper alignment for multi-line text
        draw.text(position, text, font=font, fill=fg_color, align='center')

        # Convert to format expected by Stream Deck
        result = PILHelper.to_native_format(self.deck, image)

        # Cache the result for static images
        if font_size != 'dynamic':
            cache_key = (text, bg_color, fg_color, font_size)
            self.image_cache[cache_key] = result

        return result

    def _calculate_dynamic_font_size(self, text: str, img_width: int, img_height: int,
                                     font_paths: list, draw: ImageDraw.ImageDraw) -> int:
        """Calculate optimal font size to fit text with padding

        Args:
            text: Text to fit
            img_width: Image width in pixels
            img_height: Image height in pixels
            font_paths: List of font file paths to try
            draw: ImageDraw object for measuring text

        Returns:
            Optimal font size in pixels
        """
        # Padding only left-to-right (horizontal), no vertical padding
        horizontal_padding_ratio = 0.1  # 10% padding on left and right
        max_width = img_width * (1 - 2 * horizontal_padding_ratio)
        max_height = img_height  # Use full height

        # Start with a reasonable maximum and binary search for optimal size
        min_size = 8
        max_size = 50
        optimal_size = min_size

        # Use cached font path if available, otherwise find one
        test_font_path = self.available_font_path

        if not test_font_path:
            # Find an available font
            for font_path in font_paths:
                try:
                    ImageFont.truetype(font_path, min_size)
                    test_font_path = font_path
                    self.available_font_path = font_path  # Cache it
                    break
                except (OSError, IOError):
                    continue

        if test_font_path is None:
            # Can't load any font, return a safe default
            return 14

        # Binary search for optimal font size
        while min_size <= max_size:
            mid_size = (min_size + max_size) // 2

            # Use cached font loading
            test_font = self._load_font_cached([test_font_path], mid_size)
            if test_font is None:
                break

            bbox = draw.textbbox((0, 0), text, font=test_font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            if text_width <= max_width and text_height <= max_height:
                # This size fits, try larger
                optimal_size = mid_size
                min_size = mid_size + 1
            else:
                # Too big, try smaller
                max_size = mid_size - 1

        return optimal_size

    def _on_volume_change(self):
        """Callback for volume changes - update all volume display buttons"""
        if not self.running:
            return

        # Use volume control module to update all volume buttons
        self.volume_control.update_volume_buttons(
            self.groups, self.group_pages, self.button_to_group,
            self.deck, self._create_button_image
        )

    def _watch_config_file(self):
        """Watch config file for changes and reload if valid"""
        if INOTIFY_AVAILABLE:
            self._watch_config_file_inotify()
        else:
            self._watch_config_file_polling()

    def _watch_config_file_inotify(self):
        """Watch config file using inotify for efficient event-based monitoring"""
        logger.debug(f"Config watcher thread started (inotify), watching: {self.config_path}")

        inotify = INotify()
        watch_flags = flags.MODIFY | flags.CLOSE_WRITE

        try:
            # Watch the parent directory since editors often replace files
            watch_dir = self.config_path.parent
            wd = inotify.add_watch(str(watch_dir), watch_flags)
            logger.debug(f"Added inotify watch on directory: {watch_dir}")

            while self.running:
                # Wait for events with timeout to allow checking self.running
                events = inotify.read(timeout=1000)

                for event in events:
                    # Check if the event is for our config file
                    if event.name == self.config_path.name:
                        logger.info("Config file changed (inotify), attempting reload...")
                        self._reload_config()

        except Exception as e:
            logger.error(f"Error in inotify config watcher: {e}")
            logger.info("Falling back to polling-based config watching")
            self._watch_config_file_polling()
        finally:
            inotify.close()

    def _watch_config_file_polling(self):
        """Watch config file using polling (fallback method)"""
        logger.debug(f"Config watcher thread started (polling), watching: {self.config_path}")

        while self.running:
            try:
                if not self.config_path.exists():
                    logger.warning(f"Config file does not exist: {self.config_path}")
                    time.sleep(1)
                    continue

                current_mtime = self.config_path.stat().st_mtime

                if current_mtime > self.config_last_modified:
                    logger.info("Config file changed (polling), attempting reload...")
                    self._reload_config()

                time.sleep(1)  # Check every second
            except Exception as e:
                logger.error(f"Error in config watcher: {e}")
                time.sleep(1)

    def _reload_config(self):
        """Reload config file and update all components"""
        # Small delay to ensure file write is complete
        time.sleep(0.1)

        # Try to load the new config
        try:
            new_config = ConfigLoader.load(self.config_path)
            current_mtime = self.config_path.stat().st_mtime

            # Disconnect old Home Assistant and OBS connections before creating new ones
            if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
                logger.info("Disconnecting old Home Assistant WebSocket before reload")
                self.action_handler.ha_control.disconnect()
                # Give it a moment to fully disconnect
                time.sleep(0.2)

            if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
                logger.info("Disconnecting old OBS WebSocket before reload")
                self.action_handler.obs_control.disconnect()
                # Give it a moment to fully disconnect
                time.sleep(0.2)

            # Config is valid, update
            with self.config_lock:
                self.config = new_config
                self.config_last_modified = current_mtime
                self.action_handler = ActionHandler(new_config)
                self.groups = new_config['groups']

            logger.info("Config reloaded successfully")

            # Set up OBS status callback for visual feedback
            if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
                self.action_handler.obs_control.add_status_callback(self._on_obs_status_change)
                # Small delay to ensure OBS initial state is fetched
                time.sleep(0.5)

            # Set up Home Assistant status callback for visual feedback
            if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
                self.action_handler.ha_control.add_status_callback(self._on_ha_status_change)
                # Pre-track all Home Assistant entities from config to ensure initial states are fetched
                self._track_all_ha_entities()
                # Longer delay to ensure Home Assistant initial states are fetched
                time.sleep(2.0)

            # Update brightness if changed
            brightness = new_config.get('streamdeck', {}).get('brightness', 80)
            self.deck.set_brightness(brightness)
            logger.debug(f"Brightness updated to {brightness}")

            # Update font paths if changed
            self.font_paths = self._get_font_paths()

            # Clear caches on config reload
            self.font_cache.clear()
            self.image_cache.clear()
            self.available_font_path = None  # Clear cached font path

            # Reinitialize buttons with new config
            self._initialize_buttons()

            # Force refresh OBS buttons to ensure proper highlighting
            if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
                self._on_obs_status_change()

            # Force refresh Home Assistant buttons to ensure proper highlighting
            if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
                self._on_ha_status_change()

        except Exception as e:
            logger.error(f"Failed to reload config (keeping old config): {e}")

    def _key_change_callback(self, deck, key, state):
        """Handle button press/release events"""
        logger.debug(f"Key callback: key={key} (type={type(key).__name__}), state={state}")

        # Find which group this button belongs to
        group_name = self.button_to_group.get(key)
        if not group_name:
            logger.warning(f"Button {key} not assigned to any group")
            return

        # Get the current page for this group
        page_num = self.group_pages.get(group_name, 0)
        group_config = self.groups[group_name]
        pages = group_config.get('pages', {})
        page_config = pages.get(page_num, {})
        buttons = page_config.get('buttons', {})

        logger.debug(f"Button {key} in group '{group_name}', page {page_num}, buttons: {list(buttons.keys())}")

        button_config = buttons.get(str(key))

        if not button_config:
            logger.warning(f"No action configured for button {key}")
            return

        # state is True for press, False for release
        if state:
            logger.info(f"Button {key} pressed - action: {button_config.get('type')}")

            # Handle page_switch specially
            if button_config.get('type') == 'page_switch':
                # Start a timer - if held for 500ms, go to page 0 instead
                def go_to_page_0():
                    logger.info(f"Page switch button {key} held for 500ms - going to page 0")
                    self.switch_page(group_name, 0)
                    # Mark that we went to page 0 so we don't also switch on release
                    self.page_switch_timers[key] = 'triggered'

                # Cancel any existing timer for this button
                if key in self.page_switch_timers and isinstance(self.page_switch_timers[key], threading.Timer):
                    self.page_switch_timers[key].cancel()

                # Start new timer for hold-to-home
                timer = threading.Timer(0.5, go_to_page_0)
                timer.daemon = True
                timer.start()
                self.page_switch_timers[key] = timer
            else:
                self.action_handler.handle_press(key, button_config)
        else:
            logger.debug(f"Button {key} released")
            button_type = button_config.get('type')

            if button_type == 'page_switch':
                # Cancel the timer if still running
                if key in self.page_switch_timers:
                    timer_or_flag = self.page_switch_timers[key]

                    if isinstance(timer_or_flag, threading.Timer):
                        # Timer still running - cancel it and do normal page switch
                        timer_or_flag.cancel()
                        target_page = button_config.get('page', 0)
                        target_group = button_config.get('group', self.button_to_group.get(key))
                        self.switch_page(target_group, target_page)
                    # else: timer already triggered (went to page 0), don't switch again

                    # Clean up
                    del self.page_switch_timers[key]
            else:
                self.action_handler.handle_release(key, button_config)

    def _cleanup(self):
        """Clean up Stream Deck connection and resources"""
        self.running = False

        # Stop volume monitoring
        if self.volume_control:
            logger.info("Stopping volume monitoring")
            self.volume_control.stop_monitoring()

        # Disconnect OBS WebSocket
        if hasattr(self.action_handler, 'obs_control') and self.action_handler.obs_control:
            logger.info("Disconnecting OBS WebSocket")
            self.action_handler.obs_control.disconnect()

        # Disconnect Home Assistant WebSocket
        if hasattr(self.action_handler, 'ha_control') and self.action_handler.ha_control:
            logger.info("Disconnecting Home Assistant WebSocket")
            self.action_handler.ha_control.disconnect()

        # Close Stream Deck
        if self.deck:
            logger.info("Closing Stream Deck connection")
            try:
                self.deck.reset()
            except Exception as e:
                logger.warning(f"Failed to reset Stream Deck during cleanup: {e}")
            try:
                self.deck.close()
            except Exception as e:
                logger.warning(f"Failed to close Stream Deck: {e}")
