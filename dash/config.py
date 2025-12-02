"""
Centralized configuration for dash.ipynb.

This module centralizes all configuration constants, making them easier to
maintain and modify. Parameters are organized by category.

OBSERVABILITY: Structured logging with correlation ID support (Principle #13).
"""

import uuid
# Import centralized logging configuration (SSOT - Principle #2)
from shared.logging_config import setup_structlog, get_logger
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret

# Configure structured logging (centralized)
setup_structlog()

# Get logger instance
logger = get_logger()


def generate_correlation_id() -> str:
    """
    Generate a correlation ID for request tracing.
    
    OBSERVABILITY: Correlation IDs enable tracing requests across operations (Principle #13).
    
    Returns:
        UUID string for correlation
    """
    return str(uuid.uuid4())


def get_logger_with_correlation(correlation_id: str = None):
    """
    Get logger instance with correlation ID bound.
    
    OBSERVABILITY: Binds correlation ID to logger for request tracing (Principle #13).
    SECURITY: Validates correlation ID format to prevent log injection (Principle #12).
    
    Args:
        correlation_id: Optional correlation ID (generates new one if not provided)
        
    Returns:
        Logger instance with correlation_id bound
    """
    if correlation_id is None:
        correlation_id = generate_correlation_id()
    else:
        # SECURITY: Validate correlation ID format to prevent log injection
        # Allow UUID format (with or without hyphens) or generate new one if invalid
        import re
        uuid_pattern = re.compile(
            r'^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$',
            re.IGNORECASE
        )
        if not uuid_pattern.match(correlation_id):
            logger.warning(
                "invalid_correlation_id_format",
                provided_id=correlation_id[:50],  # Truncate for safety
                action="generating_new_correlation_id"
            )
            correlation_id = generate_correlation_id()
    
    return logger.bind(correlation_id=correlation_id)

# =========================
# Cache Configuration
# =========================
TRANSCRIPT_CACHE_TIMEOUT_SECONDS = 3600  # 1 hour expiration (FERPA compliance)

# =========================
# Security Configuration
# =========================
# HMAC_SECRET retrieved from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)

