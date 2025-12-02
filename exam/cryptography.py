"""
Cryptography utilities for exam.ipynb - encryption functions.

This module contains encryption functions used only by exam.ipynb.
Functions used by multiple apps are in shared/.
"""

import os
import hmac
import hashlib
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret

# Get HMAC_SECRET from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)

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


def encrypt_bytes(plaintext: bytes, passphrase: str, aad: bytes | None = None) -> bytes:
    """
    Encrypt bytes using AES-GCM with HMAC authentication.
    
    Format: MAGIC + HMAC + (SALT + NONCE + CIPHERTEXT)
    
    Args:
        plaintext: Bytes to encrypt
        passphrase: Passphrase for encryption
        aad: Optional additional authenticated data
        
    Returns:
        Encrypted bytes with format: MAGIC + HMAC + payload
    """
    salt, nonce = os.urandom(SALT_LEN), os.urandom(NONCE_LEN)
    key = _derive_key(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    payload = salt + nonce + ct
    mac = hmac.new(HMAC_SECRET.encode(), payload, hashlib.sha256).digest()
    return MAGIC + mac + payload

