"""
Logging Configuration
=====================
Unified logging setup using Rich for beautiful console output.
"""

import logging
from rich.logging import RichHandler

def setup_logger(level: str = "INFO"):
    """
    Configure the root logger with RichHandler.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    """
    return logging.getLogger(name)