"""
Cryptography utilities for encryption and decryption.

This module provides AES-GCM encryption with HMAC authentication for secure
data encryption and decryption.
"""

import os
import hmac
import hashlib
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _get_hmac_secret() -> str:
    """
    Get HMAC secret from environment with lazy initialization.
    
    CONFIGURATION & SECRETS DISCIPLINE: Lazy initialization ensures secret is
    validated when actually needed, not at module import time (Principle #23).
    
    SECURITY: Never hardcode secrets - always retrieve from environment.
    Never log the actual secret value - only log that it's set.
    
    Returns:
        HMAC secret string
        
    Raises:
        ValueError: If VIVA_HMAC_SECRET is not set
    """
    secret = os.getenv("VIVA_HMAC_SECRET")
    if not secret:
        raise ValueError(
            "VIVA_HMAC_SECRET environment variable must be set. "
            "This is required for encryption/decryption. Set it in your .env file or environment variables."
        )
    return secret

# Constants
MAGIC = b"VIVA1"
HMAC_LEN = 32
SALT_LEN = 16
NONCE_LEN = 12


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive encryption key from passphrase using PBKDF2.
    
    Args:
        passphrase: The passphrase to derive the key from
        salt: Random salt bytes
        
    Returns:
        32-byte encryption key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=200000,
        backend=default_backend()
    )
    return kdf.derive(passphrase.encode("utf-8"))


def decrypt_bytes(enc_bytes: bytes, passphrase: str, aad: bytes | None = None) -> bytes:
    """
    Decrypt bytes using AES-GCM with HMAC verification.
    
    Args:
        enc_bytes: Encrypted bytes with format: MAGIC + HMAC + payload
        passphrase: Passphrase for decryption
        aad: Optional additional authenticated data (must match encryption)
        
    Returns:
        Decrypted plaintext bytes
        
    Raises:
        TypeError: If enc_bytes is not bytes
        ValueError: If ciphertext is too short, missing MAGIC, HMAC verification fails, or payload is malformed
    """
    if not isinstance(enc_bytes, (bytes, bytearray)):
        raise TypeError("Encrypted payload must be bytes")
    if len(enc_bytes) < len(MAGIC) + HMAC_LEN + SALT_LEN + NONCE_LEN + 1:
        raise ValueError("Ciphertext too short")
    if not enc_bytes.startswith(MAGIC):
        raise ValueError("Bad header: missing MAGIC")
    off = len(MAGIC)
    mac = enc_bytes[off:off + HMAC_LEN]
    payload = enc_bytes[off + HMAC_LEN:]
    expected = hmac.new(_get_hmac_secret().encode(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("HMAC verification failed")
    if len(payload) < SALT_LEN + NONCE_LEN + 1:
        raise ValueError("Malformed payload")
    salt = payload[:SALT_LEN]
    nonce = payload[SALT_LEN:SALT_LEN + NONCE_LEN]
    ct = payload[SALT_LEN + NONCE_LEN:]
    key = _derive_key(passphrase, salt)
    return AESGCM(key).decrypt(nonce, ct, aad)

