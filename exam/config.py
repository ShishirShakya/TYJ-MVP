"""
Centralized configuration for exam.ipynb.

This module centralizes all configuration constants, making them easier to
maintain and modify. Parameters are organized by category.
"""

# Import centralized prompts (supports encrypted prompts in production)
from shared.config.prompts import SHORT_PROMPT_TTS
# Import centralized logging configuration (SSOT - Principle #2)
from shared.logging_config import setup_structlog, get_logger
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret
# Import centralized constants (SSOT - Principle #2)
from shared.constants import MAX_PDF_SIZE
# Import secure configuration management (SSOT - Principle #2)
from shared.config.secure_config import get_validation_config

# Configure structured logging (centralized)
setup_structlog()

# Get logger instance
logger = get_logger()

# =========================
# Model Configuration
# =========================
CHAT_MODEL = "gpt-4o-mini"
TTS_MODEL = "gpt-4o-mini-tts"
TTS_VOICE = "alloy"
STT_MODEL = "whisper-1"

# =========================
# Version Information
# =========================
APP_VERSION = "1.1.0"
RECEIPT_VERSION = "2.0"
RUBRIC_VERSION = "v1"

# =========================
# Exam Configuration (Defaults)
# =========================
# Note: These are defaults. Actual values are set from URL via context variables.
N_QUESTIONS_DEFAULT = 1
FOLLOWUPS_MIN_DEFAULT = 0
FOLLOWUPS_MAX_DEFAULT = 1

# =========================
# Guardrails/Validation
# =========================
# Get validation config from environment variables (with defaults)
_validation_config = get_validation_config()
MIN_WORDS = _validation_config["min_words"]
MAX_SHORT_ATTEMPTS = _validation_config["max_short_attempts"]
# SHORT_PROMPT_TTS is imported from shared.config.prompts (supports encryption)

# =========================
# Timeout Configuration
# =========================
# MAX_ANSWER_TIMEOUT_SEC is set dynamically from URL (time_per_question parameter)
# Default value: 60 seconds (will be overridden when professor's link is parsed)
MAX_ANSWER_TIMEOUT_SEC_DEFAULT = 60

# Processing and session buffers
PROCESSING_BUFFER_SEC = 30
SESSION_BUFFER_SEC = 10

# MAX_SESSION_DURATION_SEC is calculated dynamically using context variables
# Formula: (MAX_ANSWER_TIMEOUT_SEC + PROCESSING_BUFFER_SEC + SESSION_BUFFER_SEC) * 
#          (N_QUESTIONS + (N_QUESTIONS * FOLLOWUPS_MAX))

# =========================
# PDF Configuration
# =========================
# MAX_PDF_SIZE imported from shared.constants (SSOT - Principle #2)
MAX_PAGES = 50  # Prevent processing of extremely long PDFs

# =========================
# Security Configuration
# =========================
# HMAC_SECRET retrieved from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)

# =========================
# Exam Termination Configuration
# =========================
# Violation thresholds for exam termination (configurable via environment variables)
import os
VIOLATION_THRESHOLDS = {
    "TAB_BLUR": int(os.getenv("EXAM_TAB_BLUR_THRESHOLD", "3")),  # Terminate after 3 tab switches
    "CLIPBOARD_PASTE": int(os.getenv("EXAM_CLIPBOARD_PASTE_THRESHOLD", "2")),  # Terminate after 2 paste events
    "CLIPBOARD_COPY": int(os.getenv("EXAM_CLIPBOARD_COPY_THRESHOLD", "5")),  # More lenient for copy
    "VOICEPRINT_MISMATCH": int(os.getenv("EXAM_VOICEPRINT_MISMATCH_THRESHOLD", "1")),  # Immediate termination
    "ANSWER_REUSE_DETECTED": int(os.getenv("EXAM_ANSWER_REUSE_THRESHOLD", "2")),  # Terminate after 2 reuse detections
    "MULTI_FACE": int(os.getenv("EXAM_MULTI_FACE_THRESHOLD", "1")),  # Immediate termination
}

# Critical violations that should terminate immediately (regardless of threshold)
CRITICAL_VIOLATIONS = [
    "VOICEPRINT_MISMATCH",  # Different person speaking
    "MULTI_FACE",  # Multiple people detected
    "PROFANITY_DETECTED",  # Already implemented
]

# =========================
# Persistence Configuration
# =========================
# Persistence Gate (sealed after export)
# Note: This is a mutable state variable, not a constant
# It's initialized here but can be modified at runtime
PERSIST_OK = True

# =========================
# Helper Functions
# =========================

def continuity_mode() -> str:
    """
    Return continuity mode string.
    
    Returns:
        Continuity mode string ("ephemeral")
    """
    return "ephemeral"


def model_versions() -> dict:
    """
    Return dictionary of model versions.
    
    Returns:
        Dictionary with chat, tts, and stt model names
    """
    return {"chat": CHAT_MODEL, "tts": TTS_MODEL, "stt": STT_MODEL}


# =========================
# Exports
# =========================
__all__ = [
    # Model Configuration
    "CHAT_MODEL",
    "TTS_MODEL",
    "TTS_VOICE",
    "STT_MODEL",
    # Version Information
    "APP_VERSION",
    "RECEIPT_VERSION",
    "RUBRIC_VERSION",
    # Exam Configuration
    "N_QUESTIONS_DEFAULT",
    "FOLLOWUPS_MIN_DEFAULT",
    "FOLLOWUPS_MAX_DEFAULT",
    # Guardrails
    "MIN_WORDS",
    "MAX_SHORT_ATTEMPTS",
    "SHORT_PROMPT_TTS",
    # Timeout Configuration
    "MAX_ANSWER_TIMEOUT_SEC_DEFAULT",
    "PROCESSING_BUFFER_SEC",
    "SESSION_BUFFER_SEC",
    # PDF Configuration
    "MAX_PDF_SIZE",
    "MAX_PAGES",
    # Security Configuration
    "HMAC_SECRET",
    # Exam Termination Configuration
    "VIOLATION_THRESHOLDS",
    "CRITICAL_VIOLATIONS",
    # Persistence Configuration
    "PERSIST_OK",
    # Helper Functions
    "continuity_mode",
    "model_versions",
    # Logger
    "logger",
]

