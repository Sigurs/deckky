"""Utility functions for button update operations"""

import logging
from typing import Dict, Any, Callable

logger = logging.getLogger(__name__)


def update_buttons_for_type(
    groups: Dict[str, Any],
    group_pages: Dict[str, int],
    button_to_group: Dict[int, str],
    deck,
    create_image_callback: Callable,
    button_type: str,
    setup_button_func: Callable,
) -> int:
    """Update all buttons of a specific type across all groups. Returns count updated."""
    updated_count = 0
    
    for group_name, group_config in groups.items():
        pages = group_config.get('pages', {})
        button_range = group_config.get('buttons', [])
        
        current_page = group_pages.get(group_name, 0)
        
        if current_page not in pages:
            continue
            
        page_config = pages[current_page]
        page_buttons = page_config.get('buttons', {})
        
        for button_id, button_config in page_buttons.items():
            button_num = int(button_id)
            
            if (button_config.get('type') == button_type and
                button_num in button_range):
                
                group_bg_color = group_config.get('bg_color', 'black')
                image = setup_button_func(button_config, create_image_callback, group_bg_color)
                
                if image:
                    deck.set_key_image(button_num, image)
                    updated_count += 1
    
    return updated_count
