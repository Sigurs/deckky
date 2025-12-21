"""Keyboard input handling for Wayland and X11"""

import os
import subprocess
import logging
from typing import List, Union
import time

logger = logging.getLogger(__name__)


class InputHandler:
    """Handles keyboard input simulation for both Wayland and X11"""

    # Map common key names to their X11 names
    KEY_MAP_X11 = {
        'ctrl': 'Control_L',
        'control': 'Control_L',
        'shift': 'Shift_L',
        'alt': 'Alt_L',
        'super': 'Super_L',
        'win': 'Super_L',
        'enter': 'Return',
        'esc': 'Escape',
        'tab': 'Tab',
        'space': 'space',
        'backspace': 'BackSpace',
        # F keys work directly in X11 with their names
        'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4',
        'f5': 'F5', 'f6': 'F6', 'f7': 'F7', 'f8': 'F8',
        'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
        'f13': 'F13', 'f14': 'F14', 'f15': 'F15', 'f16': 'F16',
        'f17': 'F17', 'f18': 'F18', 'f19': 'F19', 'f20': 'F20',
        'f21': 'F21', 'f22': 'F22', 'f23': 'F23', 'f24': 'F24',
    }

    # Map common key names to Linux input event codes for ydotool
    KEY_MAP_YDOTOOL = {
        'ctrl': '29',      # KEY_LEFTCTRL
        'control': '29',
        'shift': '42',     # KEY_LEFTSHIFT
        'alt': '56',       # KEY_LEFTALT
        'super': '125',    # KEY_LEFTMETA
        'win': '125',
        'enter': '28',     # KEY_ENTER
        'esc': '1',        # KEY_ESC
        'tab': '15',       # KEY_TAB
        'space': '57',     # KEY_SPACE
        'backspace': '14', # KEY_BACKSPACE
        # F keys (F1-F24)
        'f1': '59',        # KEY_F1
        'f2': '60',        # KEY_F2
        'f3': '61',        # KEY_F3
        'f4': '62',        # KEY_F4
        'f5': '63',        # KEY_F5
        'f6': '64',        # KEY_F6
        'f7': '65',        # KEY_F7
        'f8': '66',        # KEY_F8
        'f9': '67',        # KEY_F9
        'f10': '68',       # KEY_F10
        'f11': '87',       # KEY_F11
        'f12': '88',       # KEY_F12
        'f13': '183',      # KEY_F13
        'f14': '184',      # KEY_F14
        'f15': '185',      # KEY_F15
        'f16': '186',      # KEY_F16
        'f17': '187',      # KEY_F17
        'f18': '188',      # KEY_F18
        'f19': '189',      # KEY_F19
        'f20': '190',      # KEY_F20
        'f21': '191',      # KEY_F21
        'f22': '192',      # KEY_F22
        'f23': '193',      # KEY_F23
        'f24': '194',      # KEY_F24
        # Common letter keys
        't': '20',         # KEY_T
        'g': '34',         # KEY_G
        'i': '23',         # KEY_I
        'h': '35',         # KEY_H
        'u': '22',         # KEY_U
        'b': '48',         # KEY_B
        'c': '46',         # KEY_C
        'o': '24',         # KEY_O
        'm': '50',         # KEY_M
        'v': '47',         # KEY_V
        'p': '25',         # KEY_P
        'd': '32',         # KEY_D
        '.': '52',         # KEY_DOT
    }

    def __init__(self):
        self.session_type = os.environ.get('XDG_SESSION_TYPE', 'x11')
        logger.info(f"Detected session type: {self.session_type}")

        # Check if we're on Wayland
        self.is_wayland = self.session_type == 'wayland'

        if self.is_wayland:
            # For Wayland, we'll use ydotool (requires ydotoold running)
            if not self._check_ydotool():
                logger.warning("ydotool not available, hotkeys may not work on Wayland")
        else:
            # For X11, we'll use xdotool
            if not self._check_xdotool():
                logger.warning("xdotool not available, hotkeys may not work on X11")

    def _check_ydotool(self) -> bool:
        """Check if ydotool is available"""
        try:
            subprocess.run(['ydotool', '--help'], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    def _check_xdotool(self) -> bool:
        """Check if xdotool is available"""
        try:
            subprocess.run(['xdotool', '--version'], capture_output=True, check=False)
            return True
        except FileNotFoundError:
            return False

    def _run_tool_command(self, args: List[str], tool_name: str):
        """Run input tool command with consistent error handling"""
        try:
            subprocess.run(args, check=not self.is_wayland)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to execute {tool_name} command {' '.join(args)}: {e}")
        except FileNotFoundError:
            logger.error(f"{tool_name} not found. Please install it.")

    def _normalize_key(self, key: str, for_wayland: bool = False) -> str:
        """Normalize key name"""
        key_lower = key.lower()
        if for_wayland:
            # For ydotool, return the event code if available, otherwise try to map single char
            code = self.KEY_MAP_YDOTOOL.get(key_lower)
            if code:
                return code
            # For single lowercase letters a-z not in map
            if len(key_lower) == 1 and 'a' <= key_lower <= 'z':
                # KEY_A is 30, KEY_B is 48, etc. (not sequential!)
                # Return the key as-is and let ydotool type handle it
                return key_lower
            return key_lower
        else:
            return self.KEY_MAP_X11.get(key_lower, key)

    def send_hotkey(self, keys: Union[str, List[str]]):
        """Send a hotkey combination"""
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split('+')]

        if self.is_wayland:
            normalized_keys = [self._normalize_key(k, for_wayland=True) for k in keys]
            self._send_hotkey_wayland(normalized_keys)
        else:
            normalized_keys = [self._normalize_key(k, for_wayland=False) for k in keys]
            self._send_hotkey_x11(normalized_keys)

    def _send_hotkey_x11(self, keys: List[str]):
        """Send hotkey using xdotool for X11"""
        key_combo = '+'.join(keys)
        self._run_tool_command(['xdotool', 'key', key_combo], 'xdotool')
        logger.debug(f"Sent X11 hotkey: {key_combo}")

    def _send_hotkey_wayland(self, keys: List[str]):
        """Send hotkey using ydotool for Wayland"""
        # ydotool uses key codes, press all modifier keys first
        for key in keys:
            self._run_tool_command(['ydotool', 'key', f'{key}:1'], 'ydotool')
            time.sleep(0.005)

        time.sleep(0.02)

        # Release in reverse order
        for key in reversed(keys):
            self._run_tool_command(['ydotool', 'key', f'{key}:0'], 'ydotool')
            time.sleep(0.005)

        logger.debug(f"Sent Wayland hotkey codes: {'+'.join(keys)}")

    def send_keys(self, keys: List[Union[str, dict]]):
        """Send a sequence of keys with optional delays"""
        for item in keys:
            if isinstance(item, dict) and 'delay' in item:
                # Delay in milliseconds
                time.sleep(item['delay'] / 1000.0)
            elif isinstance(item, list):
                # Hotkey combination
                self.send_hotkey(item)
            else:
                # Single key
                self._send_single_key(item)

    def _send_single_key(self, key: str):
        """Send a single key press"""
        if self.is_wayland:
            # For single characters on Wayland, use ydotool type for simplicity
            if len(key) == 1:
                self._run_tool_command(['ydotool', 'type', key], 'ydotool')
                logger.debug(f"Sent Wayland char: {key}")
            else:
                # For special keys, use key codes
                normalized_key = self._normalize_key(key, for_wayland=True)
                self._run_tool_command(['ydotool', 'key', normalized_key], 'ydotool')
                logger.debug(f"Sent Wayland key code: {normalized_key}")
        else:
            normalized_key = self._normalize_key(key, for_wayland=False)
            self._run_tool_command(['xdotool', 'key', normalized_key], 'xdotool')
            logger.debug(f"Sent X11 key: {normalized_key}")

    def key_down(self, key: str):
        """Press and hold a key"""
        normalized_key = self._normalize_key(key, for_wayland=self.is_wayland)

        if self.is_wayland:
            self._run_tool_command(['ydotool', 'key', f'{normalized_key}:1'], 'ydotool')
            logger.debug(f"Key down (Wayland): {normalized_key}")
        else:
            self._run_tool_command(['xdotool', 'keydown', normalized_key], 'xdotool')
            logger.debug(f"Key down (X11): {normalized_key}")

    def key_up(self, key: str):
        """Release a held key"""
        normalized_key = self._normalize_key(key, for_wayland=self.is_wayland)

        if self.is_wayland:
            self._run_tool_command(['ydotool', 'key', f'{normalized_key}:0'], 'ydotool')
            logger.debug(f"Key up (Wayland): {normalized_key}")
        else:
            self._run_tool_command(['xdotool', 'keyup', normalized_key], 'xdotool')
            logger.debug(f"Key up (X11): {normalized_key}")
