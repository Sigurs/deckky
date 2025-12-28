"""Centralized logging configuration for Deckky"""

import logging
from typing import Dict, Any


def setup_logging(config: Dict[str, Any] = None):
    """Setup logging configuration for the application
    
    Args:
        config: Configuration dictionary that may contain logging settings
    """
    # Get log level from config, default to INFO
    log_level = logging.INFO
    if config and 'logging' in config:
        level_str = config['logging'].get('level', 'INFO').upper()
        log_level = getattr(logging, level_str, logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Get logger for this module and log the configuration
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized at level {logging.getLevelName(log_level)}")
