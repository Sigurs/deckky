"""Configuration file loader and validator"""

import yaml
from pathlib import Path
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Loads and validates YAML configuration"""

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with override taking priority

        Args:
            base: Base configuration dictionary
            override: Override configuration dictionary (takes priority)

        Returns:
            Merged dictionary with override values taking priority
        """
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = ConfigLoader._deep_merge(result[key], value)
            else:
                # Override value (or add new key)
                result[key] = value

        return result

    @staticmethod
    def load(config_path: Path) -> Dict[str, Any]:
        """Load configuration from YAML file, merging with secrets.yaml if present

        Config loading priority:
        1. Load base config.yaml
        2. If secrets.yaml exists in same directory, load and merge it (secrets take priority)
        3. Validate final merged configuration

        Args:
            config_path: Path to config.yaml

        Returns:
            Merged and validated configuration dictionary
        """
        # Load base config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        logger.info(f"Loaded base config from: {config_path}")

        # Check for secrets.yaml in same directory
        secrets_path = config_path.parent / "secrets.yaml"
        if secrets_path.exists():
            logger.info(f"Found secrets file: {secrets_path}")
            with open(secrets_path, 'r') as f:
                secrets = yaml.safe_load(f)

            # Merge secrets into config (secrets take priority)
            if secrets:
                config = ConfigLoader._deep_merge(config, secrets)
                logger.info("Merged secrets.yaml into configuration")
        else:
            logger.debug(f"No secrets file found at: {secrets_path}")

        # Normalize button IDs to strings (YAML may parse them as integers)
        if 'groups' in config:
            for group_name, group_config in config['groups'].items():
                if 'pages' in group_config:
                    for page_id, page_config in group_config['pages'].items():
                        if 'buttons' in page_config:
                            page_config['buttons'] = {str(k): v for k, v in page_config['buttons'].items()}

        ConfigLoader._validate(config)
        return config

    @staticmethod
    def _validate(config: Dict[str, Any]) -> None:
        """Validate configuration structure"""
        if 'groups' not in config:
            raise ValueError("Configuration must contain 'groups' section")

        if not isinstance(config['groups'], dict):
            raise ValueError("'groups' must be a dictionary")

        # Get all group names for validation
        group_names = set(config['groups'].keys())

        for group_name, group_config in config['groups'].items():
            if 'buttons' not in group_config:
                raise ValueError(f"Group '{group_name}' missing 'buttons' field (list of button numbers)")

            if not isinstance(group_config['buttons'], list):
                raise ValueError(f"Group '{group_name}' 'buttons' must be a list")

            if 'pages' not in group_config:
                raise ValueError(f"Group '{group_name}' missing 'pages' section")

            if not isinstance(group_config['pages'], dict):
                raise ValueError(f"Group '{group_name}' 'pages' must be a dictionary")

            for page_id, page_config in group_config['pages'].items():
                if 'buttons' not in page_config:
                    raise ValueError(f"Group '{group_name}', Page {page_id} missing 'buttons' section")

                ConfigLoader._validate_buttons(page_config['buttons'], f"Group '{group_name}', Page {page_id}", group_names)

    @staticmethod
    def _validate_buttons(buttons: Dict[str, Any], context: str = "", group_names: set = None):
        """Validate button configurations"""
        if group_names is None:
            group_names = set()

        for button_id, button_config in buttons.items():
            if 'type' not in button_config:
                raise ValueError(f"{context} Button {button_id} missing 'type' field")

            button_type = button_config['type']
            if button_type not in ['hotkey', 'volume', 'discord', 'page_switch', 'obs', 'homeassistant']:
                raise ValueError(f"{context} Button {button_id} has invalid type: {button_type}")

            if button_type == 'volume' and 'action' not in button_config:
                raise ValueError(f"{context} Volume button {button_id} missing 'action' field")

            if button_type == 'discord' and 'action' not in button_config:
                raise ValueError(f"{context} Discord button {button_id} missing 'action' field")

            if button_type == 'page_switch' and 'page' not in button_config:
                raise ValueError(f"{context} Page switch button {button_id} missing 'page' field")

            if button_type == 'obs' and 'action' not in button_config:
                raise ValueError(f"{context} OBS button {button_id} missing 'action' field")

            if button_type == 'obs':
                action = button_config['action']
                valid_actions = ['scene_switch', 'start_recording', 'stop_recording', 'start_streaming', 'stop_streaming', 'toggle_recording', 'toggle_streaming']
                if action not in valid_actions:
                    raise ValueError(f"{context} OBS button {button_id} has invalid action '{action}'. Valid actions: {', '.join(valid_actions)}")

                if action == 'scene_switch' and 'scene' not in button_config:
                    raise ValueError(f"{context} OBS scene switch button {button_id} missing 'scene' field")

            if button_type == 'homeassistant' and 'action' not in button_config:
                raise ValueError(f"{context} Home Assistant button {button_id} missing 'action' field")

            if button_type == 'homeassistant':
                action = button_config['action']
                valid_actions = ['toggle_light', 'turn_on_light', 'turn_off_light']
                if action not in valid_actions:
                    raise ValueError(f"{context} Home Assistant button {button_id} has invalid action '{action}'. Valid actions: {', '.join(valid_actions)}")

                if 'entity_id' not in button_config:
                    raise ValueError(f"{context} Home Assistant button {button_id} missing 'entity_id' field")

            if button_type == 'page_switch' and 'group' in button_config:
                target_group = button_config['group']
                if not isinstance(target_group, str):
                    raise ValueError(f"{context} Page switch button {button_id} 'group' field must be a string")
                if target_group not in group_names:
                    raise ValueError(f"{context} Page switch button {button_id} references non-existent group '{target_group}'. Available groups: {', '.join(sorted(group_names))}")
