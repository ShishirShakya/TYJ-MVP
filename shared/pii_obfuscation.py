"""
PII obfuscation utilities for receipt_core fields.

This module provides functions for obfuscating and deobfuscating PII fields
in receipt_core to comply with FERPA requirements. Uses VIVA_HMAC_SECRET
for encryption/decryption.

FERPA COMPLIANCE: Obfuscates PII in receipt_core JSON while maintaining
reversibility for authorized instructor access after decryption.
"""

import os
from typing import Dict, Any, Optional, List, Union
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# CONFIGURATION & SECRETS DISCIPLINE: Get HMAC_SECRET from environment (Principle #23)
from shared.security_config import get_hmac_secret

# Fields that should NOT be obfuscated (needed for signature verification and integrity checks)
NON_OBFUSCATABLE_FIELDS = {
    "device_pubkey",
    "transcript_sha256",
    "otet",
    "receipt_version",
    "app_version",
    "rubric_version",
    "models",
    "merkle_root",
    "continuity_mode",
    "context_strategy",
    "chunks_total",
    "textbook_sha256",
    "followups_min",
    "followups_max",
}

# Fields to obfuscate (PII and identifiable information)
PII_FIELDS = {
    "session_id",
    "student_id",
    "started_at",
    "completed_at",
    "course_id",
    "exam_id",
    "section_id",
    "start_date",
    "end_date",
}

# Nested paths to obfuscate (field.path format)
NESTED_PII_PATHS = [
    "security.ip_address",
    "proctor.global.vis_hash",
]


def _derive_pii_key() -> bytes:
    """
    Derive a Fernet-compatible key from HMAC_SECRET for PII obfuscation.
    
    Uses PBKDF2 with SHA256 to derive a 32-byte key suitable for Fernet.
    Uses a different salt than prompt encryption to ensure separation.
    
    Returns:
        32-byte key suitable for Fernet encryption
    """
    # Use a fixed salt derived from a constant string for consistency
    # Different from prompt encryption salt to ensure separation
    salt = b"viva_pii_obfuscation_salt_v1"
    
    hmac_secret = get_hmac_secret(required=True)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    
    # Derive key from HMAC_SECRET
    key_material = hmac_secret.encode('utf-8')
    key = kdf.derive(key_material)
    
    # Convert to base64 URL-safe format for Fernet
    import base64
    return base64.urlsafe_b64encode(key)


def _derive_receipt_core_key() -> bytes:
    """
    Derive a Fernet-compatible key from HMAC_SECRET for receipt_core encryption.
    
    Uses PBKDF2 with SHA256 to derive a 32-byte key suitable for Fernet.
    Uses a different salt than PII obfuscation and prompt encryption to ensure separation.
    
    Returns:
        32-byte key suitable for Fernet encryption
    """
    # Use a fixed salt derived from a constant string for consistency
    # Different from PII obfuscation and prompt encryption salts to ensure separation
    salt = b"viva_receipt_core_encryption_salt_v1"
    
    hmac_secret = get_hmac_secret(required=True)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    
    # Derive key from HMAC_SECRET
    key_material = hmac_secret.encode('utf-8')
    key = kdf.derive(key_material)
    
    # Convert to base64 URL-safe format for Fernet
    import base64
    return base64.urlsafe_b64encode(key)


# Cache the Fernet instance for performance
_fernet_instance: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """
    Get or create Fernet instance for PII obfuscation.
    
    Returns:
        Fernet instance for encryption/decryption
    """
    global _fernet_instance
    if _fernet_instance is None:
        key = _derive_pii_key()
        _fernet_instance = Fernet(key)
    return _fernet_instance


def obfuscate_value(value: str) -> str:
    """
    Obfuscate a single string value.
    
    Args:
        value: Plaintext string to obfuscate
        
    Returns:
        Base64-encoded obfuscated string (prefixed with "OBF:")
        
    Note:
        Empty strings are returned as-is (not obfuscated)
    """
    if not value or value == "":
        return value
    
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(value.encode('utf-8'))
        # Prefix with "OBF:" to identify obfuscated values
        return "OBF:" + encrypted.decode('utf-8')
    except Exception:
        # If obfuscation fails, return original value (fail-safe)
        return value


def deobfuscate_value(value: str) -> str:
    """
    Deobfuscate a single string value.
    
    Args:
        value: Obfuscated string (may be prefixed with "OBF:" or plaintext for backward compatibility)
        
    Returns:
        Plaintext string
        
    Note:
        If value doesn't start with "OBF:", returns as-is (backward compatibility)
    """
    if not value or value == "":
        return value
    
    # Check if value is obfuscated
    if not value.startswith("OBF:"):
        # Not obfuscated - backward compatibility with old files
        return value
    
    try:
        fernet = _get_fernet()
        encrypted = value[4:].encode('utf-8')  # Remove "OBF:" prefix
        decrypted = fernet.decrypt(encrypted)
        return decrypted.decode('utf-8')
    except InvalidToken:
        # Invalid token - might be corrupted or wrong key
        # Return original value (fail-safe)
        return value
    except Exception:
        # Other errors - return original value (fail-safe)
        return value


def obfuscate_nested_field(data: Dict[str, Any], path: str) -> None:
    """
    Obfuscate a nested field in a dictionary using dot notation path.
    
    Args:
        data: Dictionary to modify in-place
        path: Dot-separated path to field (e.g., "security.ip_address")
    """
    parts = path.split(".")
    current = data
    
    # Navigate to parent dict
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return  # Path doesn't exist
        current = current[part]
    
    # Obfuscate the final field
    final_key = parts[-1]
    if isinstance(current, dict) and final_key in current:
        if isinstance(current[final_key], str):
            current[final_key] = obfuscate_value(current[final_key])


def deobfuscate_nested_field(data: Dict[str, Any], path: str) -> None:
    """
    Deobfuscate a nested field in a dictionary using dot notation path.
    
    Args:
        data: Dictionary to modify in-place
        path: Dot-separated path to field (e.g., "security.ip_address")
    """
    parts = path.split(".")
    current = data
    
    # Navigate to parent dict
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return  # Path doesn't exist
        current = current[part]
    
    # Deobfuscate the final field
    final_key = parts[-1]
    if isinstance(current, dict) and final_key in current:
        if isinstance(current[final_key], str):
            current[final_key] = deobfuscate_value(current[final_key])


def obfuscate_receipt_core(receipt_core: Dict[str, Any]) -> Dict[str, Any]:
    """
    Obfuscate PII fields in receipt_core.
    
    FERPA COMPLIANCE: Obfuscates identifiable information while preserving
    fields needed for signature verification and integrity checks.
    
    Args:
        receipt_core: Receipt core dictionary to obfuscate (modified in-place)
        
    Returns:
        Same dictionary (modified in-place) with PII fields obfuscated
    """
    # Create a copy to avoid modifying original
    core = dict(receipt_core)
    
    # Obfuscate top-level PII fields
    for field in PII_FIELDS:
        if field in core and isinstance(core[field], str):
            core[field] = obfuscate_value(core[field])
    
    # Obfuscate nested PII fields
    for path in NESTED_PII_PATHS:
        obfuscate_nested_field(core, path)
    
    # Obfuscate question_text in questions_provenance array
    if "questions_provenance" in core and isinstance(core["questions_provenance"], list):
        for item in core["questions_provenance"]:
            if isinstance(item, dict) and "question_text" in item:
                if isinstance(item["question_text"], str):
                    item["question_text"] = obfuscate_value(item["question_text"])
    
    return core


def deobfuscate_receipt_core(receipt_core: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deobfuscate PII fields in receipt_core.
    
    FERPA COMPLIANCE: Deobfuscates PII for authorized instructor access.
    Handles backward compatibility with old files that don't have obfuscated data.
    
    Args:
        receipt_core: Receipt core dictionary to deobfuscate (modified in-place)
        
    Returns:
        Same dictionary (modified in-place) with PII fields deobfuscated
    """
    # Create a copy to avoid modifying original
    core = dict(receipt_core)
    
    # Deobfuscate top-level PII fields
    for field in PII_FIELDS:
        if field in core and isinstance(core[field], str):
            core[field] = deobfuscate_value(core[field])
    
    # Deobfuscate nested PII fields
    for path in NESTED_PII_PATHS:
        deobfuscate_nested_field(core, path)
    
    # Deobfuscate question_text in questions_provenance array
    if "questions_provenance" in core and isinstance(core["questions_provenance"], list):
        for item in core["questions_provenance"]:
            if isinstance(item, dict) and "question_text" in item:
                if isinstance(item["question_text"], str):
                    item["question_text"] = deobfuscate_value(item["question_text"])
    
    return core


# =========================
# Full receipt_core encryption (new approach)
# =========================

def encrypt_receipt_core(receipt_core: Dict[str, Any]) -> str:
    """
    Encrypt the entire receipt_core JSON blob.
    
    FERPA COMPLIANCE: Encrypts the entire receipt_core (including field names)
    to protect all PII. The encrypted blob is stored as a base64 string.
    
    Args:
        receipt_core: Receipt core dictionary to encrypt
        
    Returns:
        Base64-encoded encrypted receipt_core JSON blob
    """
    import json
    
    # Serialize receipt_core to JSON bytes
    core_bytes = json.dumps(receipt_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    
    # Encrypt using Fernet
    key = _derive_receipt_core_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(core_bytes)
    
    # Return as base64 string
    return encrypted.decode('utf-8')


def decrypt_receipt_core(encrypted_core: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Decrypt the entire receipt_core JSON blob.
    
    FERPA COMPLIANCE: Decrypts receipt_core for authorized instructor access.
    Handles backward compatibility with old files that have plaintext dict.
    
    Args:
        encrypted_core: Either encrypted base64 string (new format) or dict (old format)
        
    Returns:
        Decrypted receipt_core dictionary
        
    Raises:
        ValueError: If decryption fails (corrupted data or wrong key)
    """
    import json
    
    # Backward compatibility: if it's already a dict, return as-is
    if isinstance(encrypted_core, dict):
        return encrypted_core
    
    # New format: encrypted string
    if not isinstance(encrypted_core, str):
        raise ValueError(f"receipt_core must be either dict (old format) or str (encrypted), got {type(encrypted_core)}")
    
    try:
        # Decrypt using Fernet
        key = _derive_receipt_core_key()
        fernet = Fernet(key)
        decrypted_bytes = fernet.decrypt(encrypted_core.encode('utf-8'))
        
        # Deserialize JSON
        core = json.loads(decrypted_bytes.decode('utf-8'))
        return core
    except InvalidToken:
        raise ValueError("Failed to decrypt receipt_core: invalid token (wrong key or corrupted data)")
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse decrypted receipt_core JSON: {e}")
    except Exception as e:
        raise ValueError(f"Failed to decrypt receipt_core: {e}")


__all__ = [
    "obfuscate_receipt_core",
    "deobfuscate_receipt_core",
    "obfuscate_value",
    "deobfuscate_value",
    "encrypt_receipt_core",
    "decrypt_receipt_core",
]

