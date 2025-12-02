"""
Secure configuration management - sensitive values from environment.

This module provides secure access to sensitive configuration values
that should not be hardcoded in source code.
"""

import os
from typing import Optional, Dict, Any


def get_config_value(
    config_name: str,
    default: Optional[Any] = None,
    required_in_production: bool = False,
    value_type: type = str
) -> Any:
    """
    Get configuration value from environment variable.
    
    Args:
        config_name: Name of configuration (e.g., "MIN_WORDS")
        default: Default value if not set (for development)
        required_in_production: If True, raise error if missing in production
        value_type: Type to convert value to (int, float, bool, str)
        
    Returns:
        Configuration value (converted to specified type)
        
    Raises:
        ValueError: If required_in_production=True and value missing in production
    """
    env_var_name = f"CONFIG_{config_name}"
    value = os.getenv(env_var_name)
    
    if value is None:
        environment = os.getenv("ENVIRONMENT", "development").lower()
        if required_in_production and environment == "production":
            raise ValueError(
                f"{env_var_name} must be set in production. "
                f"Set {env_var_name} environment variable."
            )
        return default
    
    # Convert to specified type
    if value_type == bool:
        return value.lower() in ("true", "1", "yes", "on")
    elif value_type == int:
        try:
            return int(value)
        except ValueError:
            return default
    elif value_type == float:
        try:
            return float(value)
        except ValueError:
            return default
    else:
        return value


def get_proctor_config() -> Dict[str, Any]:
    """
    Get proctoring configuration from environment variables.
    
    Returns:
        Dictionary with proctoring configuration values (includes both PROCTOR_RULES,
        PROCTOR_CONFIG, and PROCTOR_FLAG_RULES values)
    """
    return {
        # PROCTOR_RULES values
        "yaw_max_deg": get_config_value("PROCTOR_YAW_MAX_DEG", default=35, value_type=int),
        "pitch_max_deg": get_config_value("PROCTOR_PITCH_MAX_DEG", default=25, value_type=int),
        "away_min_consec_frames": get_config_value("PROCTOR_AWAY_MIN_CONSEC_FRAMES", default=10, value_type=int),
        "allow_multi_face": get_config_value("PROCTOR_ALLOW_MULTI_FACE", default=False, value_type=bool),
        # PROCTOR_CONFIG values
        "away_ratio_threshold": get_config_value("PROCTOR_AWAY_RATIO_THRESHOLD", default=0.5, value_type=float),
        "calibration_frames": get_config_value("PROCTOR_CALIBRATION_FRAMES", default=30, value_type=int),
        "allow_break_duration": get_config_value("PROCTOR_ALLOW_BREAK_DURATION", default=5, value_type=int),
        # PROCTOR_FLAG_RULES values
        "away_flag_consec_frames": get_config_value("PROCTOR_AWAY_FLAG_CONSEC_FRAMES", default=20, value_type=int),
        "multi_face_flag_consec_frames": get_config_value("PROCTOR_MULTI_FACE_FLAG_CONSEC_FRAMES", default=8, value_type=int),
        "no_face_flag_consec_frames": get_config_value("PROCTOR_NO_FACE_FLAG_CONSEC_FRAMES", default=12, value_type=int),
        "extreme_gaze_consec_frames": get_config_value("PROCTOR_EXTREME_GAZE_CONSEC_FRAMES", default=8, value_type=int),
    }


def get_validation_config() -> Dict[str, Any]:
    """
    Get validation configuration from environment variables.
    
    Returns:
        Dictionary with validation configuration values
    """
    return {
        "min_words": get_config_value("VALIDATION_MIN_WORDS", default=15, value_type=int),
        "max_short_attempts": get_config_value("VALIDATION_MAX_SHORT_ATTEMPTS", default=2, value_type=int),
    }

