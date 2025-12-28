#!/usr/bin/env python3
"""
Deckky - Personal Stream Deck utility for Linux
"""

import sys
import yaml
import logging
from pathlib import Path
from deckky.streamdeck_manager import StreamDeckManager
from deckky.config_loader import ConfigLoader
from deckky.logging_config import setup_logging

logger = logging.getLogger(__name__)


def find_config_file() -> Path:
    """Find config file in prioritized locations

    Priority:
    1. ~/.config/deckky/config.yaml (XDG config directory)
    2. ./config.yaml (current working directory)

    Returns:
        Path to config file

    Raises:
        FileNotFoundError: If no config file is found
    """
    # Priority 1: XDG config directory
    xdg_config = Path.home() / ".config" / "deckky" / "config.yaml"
    if xdg_config.exists():
        logger.info(f"Using config from: {xdg_config}")
        return xdg_config

    # Priority 2: Current working directory
    cwd_config = Path.cwd() / "config.yaml"
    if cwd_config.exists():
        logger.info(f"Using config from: {cwd_config}")
        return cwd_config

    # No config found, provide helpful error message
    logger.error("Configuration file not found in any of these locations:")
    logger.error(f"  1. {xdg_config} (preferred)")
    logger.error(f"  2. {cwd_config}")
    logger.info(f"Please create config.yaml in one of these locations")
    logger.info(f"See config.example.yaml for reference")

    raise FileNotFoundError("No config.yaml found")


def main():
    """Main application entry point"""
    try:
        config_file = find_config_file()
    except FileNotFoundError:
        sys.exit(1)

    try:
        config = ConfigLoader.load(config_file)
        # Setup logging after loading config (to respect logging config)
        setup_logging(config)
        logger.info("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    try:
        deck_manager = StreamDeckManager(config, config_file)
        deck_manager.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
