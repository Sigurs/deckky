"""Action handler for Stream Deck button presses"""

import logging
import threading
from typing import Dict, Any
from deckky.input_handler import InputHandler
from deckky.volume_control import VolumeControl
from deckky.obs_control import OBSControl
from deckky.homeassistant_control import HomeAssistantControl
from deckky.dlz_control import DLZControl

logger = logging.getLogger(__name__)


class ActionHandler:
    """Handles actions triggered by Stream Deck button presses"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.input_handler = InputHandler()
        self.volume_control = VolumeControl()
        self.held_keys = {}
        self.volume_ramp_threads = {}  # Track volume ramping threads
        
        # Initialize OBS control if configured
        obs_config = config.get('obs', {})
        self.obs_control = OBSControl(
            host=obs_config.get('host', 'localhost'),
            port=obs_config.get('port', 4455),
            password=obs_config.get('password', ''),
            poll_interval=obs_config.get('poll_interval', 1)
        )

        # Initialize Home Assistant control if configured
        ha_config = config.get('homeassistant', {})
        self.ha_control = HomeAssistantControl(
            host=ha_config.get('host', 'localhost'),
            port=ha_config.get('port', 8123),
            access_token=ha_config.get('access_token', ''),
            ssl=ha_config.get('ssl', True)
        )

        # Initialize DLZ Creator control
        dlz_host = config.get('dlz', {}).get('host', 'localhost')
        self.dlz_control = DLZControl(host=dlz_host)

    def handle_press(self, button_id: int, button_config: Dict[str, Any]):
        """Handle button press event"""
        action_type = button_config.get('type')

        if action_type == 'hotkey':
            self._handle_hotkey(button_id, button_config, is_press=True)
        elif action_type == 'volume':
            self._handle_volume(button_id, button_config, is_press=True)
        elif action_type == 'discord':
            self._handle_discord(button_id, button_config, is_press=True)
        elif action_type == 'obs':
            self._handle_obs(button_config)
        elif action_type == 'homeassistant':
            self._handle_homeassistant(button_config)
        elif action_type == 'dlz_pad':
            self._handle_dlz_pad(button_id, button_config)
        else:
            logger.warning(f"Unknown action type: {action_type}")

    def handle_release(self, button_id: int, button_config: Dict[str, Any]):
        """Handle button release event"""
        action_type = button_config.get('type')

        if action_type == 'hotkey':
            self._handle_hotkey(button_id, button_config, is_press=False)
        elif action_type == 'volume':
            self._handle_volume(button_id, button_config, is_press=False)
        elif action_type == 'discord':
            self._handle_discord(button_id, button_config, is_press=False)

    def _handle_hotkey(self, button_id: int, config: Dict[str, Any], is_press: bool):
        """Handle hotkey action"""
        keys = config.get('keys', [])

        if not keys:
            logger.warning(f"No keys configured for hotkey button {button_id}")
            return

        # Only trigger on button press (not release)
        if not is_press:
            return

        # Check if keys is a simple list of key names (hotkey combo)
        # or a complex macro with delays
        if isinstance(keys, list) and len(keys) > 0:
            # Check if it's a simple hotkey (all strings) or a macro
            is_simple_hotkey = all(isinstance(k, str) for k in keys)

            if is_simple_hotkey:
                # Simple hotkey combination
                self.input_handler.send_hotkey(keys)
            else:
                # Complex macro with delays
                self.input_handler.send_keys(keys)

    def _handle_volume(self, button_id: int, config: Dict[str, Any], is_press: bool):
        """Handle volume control action"""
        action = config.get('action')
        amount = config.get('amount', 5)

        if action == 'increase':
            if is_press:
                # Start volume ramping on press
                self._start_volume_ramp(button_id, 'increase', amount)
            else:
                # Stop volume ramping on release
                self._stop_volume_ramp(button_id)
        elif action == 'decrease':
            if is_press:
                # Start volume ramping on press
                self._start_volume_ramp(button_id, 'decrease', amount)
            else:
                # Stop volume ramping on release
                self._stop_volume_ramp(button_id)
        elif action == 'mute':
            if is_press:
                self.volume_control.mute_toggle()
        elif action == 'display':
            # Volume display button also acts as mute toggle when pressed
            if is_press:
                self.volume_control.mute_toggle()
        else:
            logger.warning(f"Unknown volume action: {action}")

    def _start_volume_ramp(self, button_id: int, action: str, amount: int):
        """Start continuous volume adjustment while button is held"""
        # Stop any existing ramp for this button
        self._stop_volume_ramp(button_id)

        # Create stop event for this ramp
        stop_event = threading.Event()

        def ramp_volume():
            # Initial adjustment (immediate feedback)
            if action == 'increase':
                self.volume_control.increase(amount)
            else:
                self.volume_control.decrease(amount)

            # Continue ramping while button is held
            while not stop_event.wait(0.2):  # 200ms intervals
                if action == 'increase':
                    self.volume_control.increase(amount)
                else:
                    self.volume_control.decrease(amount)

        # Start ramping thread
        ramp_thread = threading.Thread(target=ramp_volume, daemon=True)
        ramp_thread.start()

        # Store thread and stop event
        self.volume_ramp_threads[button_id] = {
            'thread': ramp_thread,
            'stop_event': stop_event
        }

        logger.debug(f"Started volume ramp for button {button_id}: {action}")

    def _stop_volume_ramp(self, button_id: int):
        """Stop continuous volume adjustment"""
        if button_id in self.volume_ramp_threads:
            ramp_info = self.volume_ramp_threads[button_id]
            ramp_info['stop_event'].set()
            ramp_info['thread'].join(timeout=0.5)
            del self.volume_ramp_threads[button_id]
            logger.debug(f"Stopped volume ramp for button {button_id}")

    def _handle_discord(self, button_id: int, config: Dict[str, Any], is_press: bool):
        """Handle Discord action (uses hotkeys configured in Discord)"""
        action = config.get('action')
        key = config.get('key')

        if not key:
            logger.warning(f"No key configured for Discord button {button_id}")
            return

        # For push-to-talk, hold key while button is pressed
        if action == 'push_to_talk':
            if is_press:
                # Parse the key combination and hold all keys
                keys = [k.strip() for k in key.split('+')]
                for k in keys:
                    self.input_handler.key_down(k)
                self.held_keys[button_id] = keys
            else:
                # Release all held keys
                if button_id in self.held_keys:
                    for k in reversed(self.held_keys[button_id]):
                        self.input_handler.key_up(k)
                    del self.held_keys[button_id]

        # For toggle actions (mute, deafen), send hotkey on press only
        elif action in ['mute', 'deafen']:
            if is_press:
                self.input_handler.send_hotkey(key)
        else:
            logger.warning(f"Unknown Discord action: {action}")

    def _handle_obs(self, config: Dict[str, Any]):
        """Handle OBS WebSocket action"""
        action = config.get('action')

        # Dispatch table for OBS actions
        obs_actions = {
            'scene_switch': lambda: self.obs_control.switch_scene(config.get('scene')),
            'toggle_recording': lambda: self.obs_control.toggle_recording(),
            'toggle_streaming': lambda: self.obs_control.toggle_streaming(),
            'start_recording': lambda: self.obs_control.start_recording(),
            'stop_recording': lambda: self.obs_control.stop_recording(),
            'start_streaming': lambda: self.obs_control.start_streaming(),
            'stop_streaming': lambda: self.obs_control.stop_streaming(),
        }

        if action == 'scene_switch' and not config.get('scene'):
            logger.error("OBS scene switch action missing 'scene' parameter")
            return

        if action in obs_actions:
            obs_actions[action]()
        else:
            logger.warning(f"Unknown OBS action: {action}")

    def _handle_homeassistant(self, config: Dict[str, Any]):
        """Handle Home Assistant action"""
        action = config.get('action')
        entity_id = config.get('entity_id')

        if not entity_id:
            logger.error("Home Assistant action missing 'entity_id' parameter")
            return

        # Start tracking this entity if not already tracking
        if entity_id.startswith('light.'):
            self.ha_control.track_light_entity(entity_id)

        # Dispatch table for Home Assistant actions
        ha_actions = {
            'toggle_light': lambda: self.ha_control.toggle_light(entity_id),
            'turn_on_light': lambda: self.ha_control.turn_on_light(entity_id),
            'turn_off_light': lambda: self.ha_control.turn_off_light(entity_id),
        }

        if action in ha_actions:
            ha_actions[action]()
        else:
            logger.warning(f"Unknown Home Assistant action: {action}")

    def _handle_dlz_pad(self, button_id: int, button_config: Dict[str, Any]):
        """Handle DLZ Creator pad playback"""
        # The button_id is the physical button number on the Stream Deck
        # We need to find which button index this is within the dlz_pads group
        # Get the dlz_pads group configuration
        dlz_pads_group = self.config.get('groups', {}).get('dlz_pads', {})
        dlz_pads_buttons = dlz_pads_group.get('buttons', [])
        
        # Find the button index within the dlz_pads group
        try:
            button_index = dlz_pads_buttons.index(button_id)
            self.dlz_control.play_pad(button_index)
        except (ValueError, AttributeError):
            logger.warning(f"Button {button_id} not found in dlz_pads group")
