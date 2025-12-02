"""
Centralized logging configuration for the VivaAI Secure Exam Proctoring System.

This module provides single source of truth for structlog configuration
used across multiple modules (Principle #2: SSOT).
"""

import os
import logging
import structlog


def get_log_level() -> str:
    """
    Get log level from environment variable.
    
    Returns:
        Log level string (default: "INFO")
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    if log_level not in valid_levels:
        # Default to INFO if invalid level specified
        return "INFO"
    
    return log_level


def setup_structlog() -> None:
    """
    Configure structured logging with standard processors.
    
    This function centralizes structlog configuration to ensure consistency
    across all modules. Call this once at module initialization.
    
    OBSERVABILITY: Structured logging with JSON output for production (Principle #13).
    Log level is configurable via LOG_LEVEL environment variable.
    """
    # Get log level from environment
    log_level = get_log_level()
    
    # Configure standard library logging level
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level),
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()  # JSON output for production
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger():
    """
    Get configured structlog logger instance.
    
    Returns:
        Configured structlog logger
    """
    return structlog.get_logger()


__all__ = [
    "setup_structlog",
    "get_logger",
]

