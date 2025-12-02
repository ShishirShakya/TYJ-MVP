"""
Centralized configuration for prof.ipynb.

This module centralizes all configuration constants, making them easier to
maintain and modify. Parameters are organized by category.
"""

# Import centralized logging configuration (SSOT - Principle #2)
from shared.logging_config import setup_structlog, get_logger
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret
# Import centralized constants (SSOT - Principle #2)
from shared.constants import MAX_PDF_SIZE

# Configure structured logging (centralized)
setup_structlog()

# Get logger instance
logger = get_logger()

# =========================
# PDF Configuration
# =========================
# MAX_PDF_SIZE imported from shared.constants (SSOT - Principle #2)

# =========================
# Security Configuration
# =========================
# HMAC_SECRET retrieved from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)

