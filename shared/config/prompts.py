"""
Centralized prompt management with encryption support.

This module provides secure loading and decryption of business logic prompts.
Prompts can be stored encrypted in environment variables for production use,
with fallback to default values for development.

Business Logic Protection:
- Prompts are encrypted at rest in production
- Decryption happens at runtime using a derived key
- Default prompts available for development/testing
- Single source of truth for all prompt definitions
"""

import os
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# CONFIGURATION & SECRETS DISCIPLINE: Get HMAC_SECRET from environment (Principle #23)
# Note: Fallback only for development - production should fail hard if not set
HMAC_SECRET = os.getenv("VIVA_HMAC_SECRET")
if not HMAC_SECRET:
    environment = os.getenv("ENVIRONMENT", "development").lower()
    if environment == "production":
        raise ValueError(
            "VIVA_HMAC_SECRET environment variable must be set in production. "
            "Set it in your .env file or environment variables."
        )
    # Development fallback (not for production)
    HMAC_SECRET = "DEVELOPMENT-ONLY-CHANGE-ME"


def _derive_prompt_key() -> bytes:
    """
    Derive a Fernet-compatible key from HMAC_SECRET for prompt encryption.
    
    Uses PBKDF2 with SHA256 to derive a 32-byte key suitable for Fernet.
    The salt is derived from a fixed string to ensure consistency.
    
    Returns:
        32-byte key suitable for Fernet encryption
    """
    # Use a fixed salt derived from a constant string for consistency
    # This ensures the same HMAC_SECRET always produces the same key
    salt = b"viva_prompt_encryption_salt_v1"
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,  # Lower than main encryption (prompts are smaller)
        backend=default_backend()
    )
    
    # Derive key from HMAC_SECRET
    key_material = HMAC_SECRET.encode('utf-8')
    key = kdf.derive(key_material)
    
    # Convert to base64 URL-safe format for Fernet
    import base64
    return base64.urlsafe_b64encode(key)


def _decrypt_prompt(encrypted_prompt: str) -> str:
    """
    Decrypt an encrypted prompt string.
    
    Args:
        encrypted_prompt: Base64-encoded encrypted prompt
        
    Returns:
        Decrypted plain text prompt
        
    Raises:
        ValueError: If decryption fails
    """
    try:
        key = _derive_prompt_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_prompt.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception as e:
        raise ValueError(f"Failed to decrypt prompt: {str(e)}") from e


def _load_prompt(prompt_name: str, default_value: str) -> str:
    """
    Load a prompt from environment variable or use default.
    
    Checks for PROMPT_{NAME}_ENCRYPTED environment variable first.
    If found and valid, decrypts it. Otherwise, uses default_value.
    
    Args:
        prompt_name: Name of the prompt (e.g., "SYSTEM_PROMPT")
        default_value: Default prompt text to use if not encrypted
        
    Returns:
        Decrypted prompt or default value
    """
    env_var_name = f"PROMPT_{prompt_name}_ENCRYPTED"
    encrypted_value = os.getenv(env_var_name)
    
    if encrypted_value:
        try:
            return _decrypt_prompt(encrypted_value)
        except Exception:
            # If decryption fails, fall back to default
            # This allows development to work without encryption
            import warnings
            warnings.warn(
                f"Failed to decrypt {env_var_name}, using default value. "
                "This is normal in development but should be fixed in production.",
                UserWarning
            )
            return default_value
    
    return default_value


# =========================
# Business Logic Prompts
# =========================
# These are the core business logic prompts used throughout the application.
# In production, these should be encrypted and stored as environment variables.

# Default prompt values (used when encryption is not configured)
_DEFAULT_SYSTEM_PROMPT = (
    "Viva voce examiner. Assess understanding with clear, focused questions. "
    "Use ONLY the provided context excerpt. No hints or answers. "
    "Questions must be answerable from context only."
)

_DEFAULT_MAIN_QUESTION_INSTR = (
    "Generate ONE question (1-2 sentences) from the context. "
    "No hints. Output question only."
)

_DEFAULT_FOLLOWUP_QUESTION_INSTR = (
    "Generate ONE clarifying question (1 sentence) based on the student's answer. "
    "No hints. Output question only."
)

_DEFAULT_FEEDBACK_BLOCK_INSTR = (
    "Format:\n"
    "Feedback: <1-2 sentences>\n"
    "Conceptual: <0-100>\n"
    "Analytical: <0-100>\n"
    "Application: <0-100>\n"
    "Reflection: <0-100>\n"
    "Overall: <0-100>"
)

_DEFAULT_SHORT_PROMPT_TTS = (
    "Your answer seems brief. Please elaborate with reasoning or an example."
)


# Public prompt constants (loaded from encrypted env vars or defaults)
SYSTEM_PROMPT = _load_prompt("SYSTEM_PROMPT", _DEFAULT_SYSTEM_PROMPT)
MAIN_QUESTION_INSTR = _load_prompt("MAIN_QUESTION_INSTR", _DEFAULT_MAIN_QUESTION_INSTR)
FOLLOWUP_QUESTION_INSTR = _load_prompt("FOLLOWUP_QUESTION_INSTR", _DEFAULT_FOLLOWUP_QUESTION_INSTR)
FEEDBACK_BLOCK_INSTR = _load_prompt("FEEDBACK_BLOCK_INSTR", _DEFAULT_FEEDBACK_BLOCK_INSTR)
SHORT_PROMPT_TTS = _load_prompt("SHORT_PROMPT_TTS", _DEFAULT_SHORT_PROMPT_TTS)


# Export all prompts for easy importing
__all__ = [
    "SYSTEM_PROMPT",
    "MAIN_QUESTION_INSTR",
    "FOLLOWUP_QUESTION_INSTR",
    "FEEDBACK_BLOCK_INSTR",
    "SHORT_PROMPT_TTS",
    "_derive_prompt_key",  # Exported for encrypt_prompts.py
    # Default prompts exported for encryption script
    "_DEFAULT_SYSTEM_PROMPT",
    "_DEFAULT_MAIN_QUESTION_INSTR",
    "_DEFAULT_FOLLOWUP_QUESTION_INSTR",
    "_DEFAULT_FEEDBACK_BLOCK_INSTR",
    "_DEFAULT_SHORT_PROMPT_TTS",
]

