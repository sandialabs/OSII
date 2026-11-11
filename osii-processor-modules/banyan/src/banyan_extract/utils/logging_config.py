# Centralized Logging Configuration
# This module provides centralized logging setup to avoid duplication across the codebase

import logging
import sys
from typing import Optional


def setup_logger(name: str, level: int = logging.INFO, 
                handler: Optional[logging.Handler] = None) -> logging.Logger:
    """
    Set up and configure a logger with consistent formatting.
    
    Args:
        name: Name of the logger
        level: Logging level (default: logging.INFO)
        handler: Optional custom handler (default: None, uses StreamHandler)
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if no handlers are already set up
    if not logger.handlers:
        logger.setLevel(level)
        
        # Use provided handler or create default StreamHandler
        if handler is None:
            handler = logging.StreamHandler(sys.stdout)
        
        handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the standard configuration.
    
    Args:
        name: Name of the logger (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return setup_logger(name)


# Module-level logger for this module
logger = get_logger(__name__)
