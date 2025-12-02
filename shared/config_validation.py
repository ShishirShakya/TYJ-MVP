"""
Configuration validation and startup checks.

This module provides functions to validate configuration at startup,
ensuring misconfiguration fails fast (Principle #23).

CONFIGURATION & SECRETS DISCIPLINE: Validates all configuration at startup (Principle #23).
"""

import os
from typing import List, Tuple, Optional, Dict, Any
from dotenv import load_dotenv
import structlog

# Load environment variables
load_dotenv()

# Get logger (assumes structlog is already configured)
logger = structlog.get_logger()


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails."""
    pass


def validate_required_env_vars(required_vars: List[str]) -> Tuple[bool, Optional[str]]:
    """
    Validate that required environment variables are set.
    
    CONFIGURATION & SECRETS DISCIPLINE: Ensures required config is present at startup (Principle #23).
    
    Args:
        required_vars: List of required environment variable names
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if all required vars are set, False otherwise
        - error_message: Error message if validation failed, None otherwise
        
    Example:
        ```python
        is_valid, error = validate_required_env_vars(["VIVA_HMAC_SECRET", "OPENAI_API_KEY"])
        if not is_valid:
            raise ConfigValidationError(error)
        ```
    """
    missing_vars = []
    for var_name in required_vars:
        value = os.getenv(var_name)
        if not value or value.strip() == "":
            missing_vars.append(var_name)
    
    if missing_vars:
        error_msg = (
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            f"Set them in your .env file or environment variables."
        )
        return False, error_msg
    
    return True, None


def validate_secret_strength(secret: str, min_length: int = 32, var_name: str = "SECRET") -> Tuple[bool, Optional[str]]:
    """
    Validate that a secret meets minimum strength requirements.
    
    CONFIGURATION & SECRETS DISCIPLINE: Ensures secrets are strong enough (Principle #23).
    
    Args:
        secret: Secret value to validate
        min_length: Minimum length required (default: 32)
        var_name: Name of the environment variable (for error messages)
        
    Returns:
        Tuple of (is_valid, warning_message)
        - is_valid: True if secret meets requirements, False otherwise
        - warning_message: Warning message if secret is weak, None otherwise
        
    Example:
        ```python
        secret = os.getenv("VIVA_HMAC_SECRET")
        is_valid, warning = validate_secret_strength(secret, min_length=32, var_name="VIVA_HMAC_SECRET")
        if not is_valid:
            logger.warning("weak_secret", message=warning)
        ```
    """
    if len(secret) < min_length:
        warning_msg = (
            f"{var_name} should be at least {min_length} characters for security. "
            f"Current length: {len(secret)}"
        )
        return False, warning_msg
    
    return True, None


def validate_config_at_startup() -> None:
    """
    Validate all configuration at startup.
    
    CONFIGURATION & SECRETS DISCIPLINE: Fails fast if misconfigured (Principle #23).
    
    This function validates:
    - Required environment variables are set
    - Secrets meet strength requirements
    - Configuration values are within valid ranges
    
    Raises:
        ConfigValidationError: If configuration is invalid
        
    Example:
        ```python
        # In app startup
        try:
            validate_config_at_startup()
        except ConfigValidationError as e:
            logger.error("config_validation_failed", error=str(e))
            raise
        ```
    """
    errors = []
    warnings = []
    
    # Check environment
    environment = os.getenv("ENVIRONMENT", "development").lower()
    is_production = environment == "production"
    
    # Required environment variables (always required)
    required_vars = []
    
    # Required in production only
    production_required_vars = ["VIVA_HMAC_SECRET"]
    
    if is_production:
        required_vars.extend(production_required_vars)
    
    # Validate required vars
    is_valid, error = validate_required_env_vars(required_vars)
    if not is_valid:
        errors.append(error)
    
    # Validate secret strength (if set)
    hmac_secret = os.getenv("VIVA_HMAC_SECRET")
    if hmac_secret:
        is_valid, warning = validate_secret_strength(hmac_secret, min_length=32, var_name="VIVA_HMAC_SECRET")
        if not is_valid:
            warnings.append(warning)
    
    # Validate optional configuration values
    # Rate limiting config
    try:
        rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        if rate_limit_per_minute < 1 or rate_limit_per_minute > 10000:
            errors.append(f"RATE_LIMIT_PER_MINUTE must be between 1 and 10000, got {rate_limit_per_minute}")
    except ValueError:
        errors.append("RATE_LIMIT_PER_MINUTE must be a valid integer")
    
    try:
        rate_limit_per_hour = int(os.getenv("RATE_LIMIT_PER_HOUR", "1000"))
        if rate_limit_per_hour < 1 or rate_limit_per_hour > 100000:
            errors.append(f"RATE_LIMIT_PER_HOUR must be between 1 and 100000, got {rate_limit_per_hour}")
    except ValueError:
        errors.append("RATE_LIMIT_PER_HOUR must be a valid integer")
    
    # Request timeout config
    try:
        request_timeout = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "300"))
        if request_timeout < 1 or request_timeout > 3600:
            errors.append(f"REQUEST_TIMEOUT_SECONDS must be between 1 and 3600, got {request_timeout}")
    except ValueError:
        errors.append("REQUEST_TIMEOUT_SECONDS must be a valid integer")
    
    # Rate limiter cleanup config
    try:
        cleanup_interval = int(os.getenv("RATE_LIMITER_CLEANUP_INTERVAL_SECONDS", "3600"))
        if cleanup_interval < 60 or cleanup_interval > 86400:
            errors.append(f"RATE_LIMITER_CLEANUP_INTERVAL_SECONDS must be between 60 and 86400, got {cleanup_interval}")
    except ValueError:
        errors.append("RATE_LIMITER_CLEANUP_INTERVAL_SECONDS must be a valid integer")
    
    try:
        max_age_seconds = int(os.getenv("RATE_LIMITER_MAX_AGE_SECONDS", "3600"))
        if max_age_seconds < 60 or max_age_seconds > 86400:
            errors.append(f"RATE_LIMITER_MAX_AGE_SECONDS must be between 60 and 86400, got {max_age_seconds}")
    except ValueError:
        errors.append("RATE_LIMITER_MAX_AGE_SECONDS must be a valid integer")
    
    # Log level config
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level not in valid_levels:
        warnings.append(f"LOG_LEVEL '{log_level}' is invalid. Valid levels: {', '.join(valid_levels)}. Defaulting to INFO.")
    
    # Log warnings (non-fatal)
    for warning in warnings:
        logger.warning(
            "config_validation_warning",
            message=warning,
            environment=environment
        )
    
    # Fail fast on errors (fatal)
    if errors:
        error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        logger.error(
            "config_validation_failed",
            errors=errors,
            environment=environment,
            message="Configuration validation failed at startup"
        )
        raise ConfigValidationError(error_msg)
    
    logger.info(
        "config_validation_passed",
        environment=environment,
        message="Configuration validation passed at startup"
    )


def sanitize_config_for_logging(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize configuration dictionary for logging (remove secrets).
    
    CONFIGURATION & SECRETS DISCIPLINE: Ensures secrets never appear in logs (Principle #23).
    
    Args:
        config_dict: Configuration dictionary to sanitize
        
    Returns:
        Sanitized configuration dictionary with secrets masked
        
    Example:
        ```python
        config = {"VIVA_HMAC_SECRET": "secret123", "RATE_LIMIT": 60}
        sanitized = sanitize_config_for_logging(config)
        # Returns: {"VIVA_HMAC_SECRET": "***", "RATE_LIMIT": 60}
        ```
    """
    # Secrets to mask
    secret_keys = [
        "VIVA_HMAC_SECRET",
        "HMAC_SECRET",
        "SECRET",
        "API_KEY",
        "PASSWORD",
        "TOKEN",
        "CREDENTIAL",
        "PASSPHRASE",
    ]
    
    sanitized = {}
    for key, value in config_dict.items():
        # Check if key contains any secret keywords
        key_upper = key.upper()
        is_secret = any(secret_key in key_upper for secret_key in secret_keys)
        
        if is_secret and isinstance(value, str) and value:
            # Mask secret (show first 4 chars and last 4 chars if long enough)
            if len(value) > 8:
                sanitized[key] = f"{value[:4]}...{value[-4:]}"
            else:
                sanitized[key] = "***"
        else:
            sanitized[key] = value
    
    return sanitized


def check_secrets_in_logs(log_message: str) -> bool:
    """
    Check if a log message contains potential secrets.
    
    CONFIGURATION & SECRETS DISCIPLINE: Detects secrets in log messages (Principle #23).
    
    Args:
        log_message: Log message to check
        
    Returns:
        True if potential secrets detected, False otherwise
        
    Example:
        ```python
        if check_secrets_in_logs(log_message):
            logger.warning("potential_secret_in_log", message="Secret detected in log message")
        ```
    """
    # Common secret patterns (simplified - not exhaustive)
    secret_patterns = [
        "api_key=",
        "password=",
        "secret=",
        "token=",
        "credential=",
        "hmac_secret=",
        "viva_hmac_secret",
    ]
    
    log_lower = log_message.lower()
    return any(pattern in log_lower for pattern in secret_patterns)


__all__ = [
    "ConfigValidationError",
    "validate_required_env_vars",
    "validate_secret_strength",
    "validate_config_at_startup",
    "sanitize_config_for_logging",
    "check_secrets_in_logs",
]

