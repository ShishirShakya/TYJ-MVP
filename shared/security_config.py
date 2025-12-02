"""
Centralized security configuration for the VivaAI Secure Exam Proctoring System.

This module provides single source of truth for security-related configuration
like HMAC secret validation (Principle #2: SSOT).

CONFIGURATION & SECRETS DISCIPLINE: Never hardcodes secrets, validates at access (Principle #23).
Secrets are retrieved from environment variables and never appear in logs or error messages.
"""

import os
from typing import Optional
from dotenv import load_dotenv
import structlog

# Load environment variables
load_dotenv()

# Get logger (assumes structlog is already configured)
logger = structlog.get_logger()


def get_hmac_secret(required: bool = True) -> str:
    """
    Get HMAC secret from environment with validation.
    
    This function centralizes HMAC secret retrieval and validation to ensure
    consistency across all modules (Principle #2: SSOT).
    
    SECURITY: Fails hard if secret not set in production (Principle #23).
    
    Args:
        required: If True, fail hard if not set (default: True)
        
    Returns:
        HMAC secret string
        
    Raises:
        ValueError: If required and secret not set
    """
    secret = os.getenv("VIVA_HMAC_SECRET")
    
    if not secret:
        if required:
            # SECURITY: Fail hard if HMAC_SECRET is not set (no fallback)
            # This prevents accidental use of weak/default secrets in production
            error_msg = (
                "VIVA_HMAC_SECRET environment variable must be set. "
                "This is required for security. Set it in your .env file or environment variables."
            )
            logger.error(
                "hmac_secret_missing",
                message=error_msg,
                environment=os.getenv("ENVIRONMENT", "unknown"),
                action="failing_hard"
            )
            raise ValueError(error_msg)
        return ""
    
    # CONFIGURATION & SECRETS DISCIPLINE: Validate secret strength (Principle #23)
    # Note: We log secret_length but NEVER log the actual secret value
    if len(secret) < 32:
        # OBSERVABILITY: Use structured logging instead of print (Principle #13)
        logger.warning(
            "hmac_secret_weak",
            message="VIVA_HMAC_SECRET should be at least 32 characters for security",
            secret_length=len(secret),  # Safe to log length
            action="warn_user"
        )
        # SECURITY: Never log the actual secret value
    
    return secret


__all__ = [
    "get_hmac_secret",
]

