"""
Device key management utilities for exam.ipynb.

This module provides functions for managing Ed25519 device keys used for
cryptographic proof of exam origin.
"""

import os
from typing import Dict, Any

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from exam.file_utils import _paths_for_session


def get_or_create_device_key(s: Dict[str, Any]) -> ed25519.Ed25519PrivateKey:
    """
    Get or create a device key for the session.
    
    The device key is stored per-session and used to sign exam data
    for cryptographic proof of origin.
    
    Args:
        s: Session state dictionary (must contain 'session_id' or will generate one)
        
    Returns:
        Ed25519 private key for the session
    """
    p = _paths_for_session(s)
    path = p["DEVICE_KEY_PATH"]
    
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                priv = serialization.load_pem_private_key(f.read(), password=None)
            if isinstance(priv, ed25519.Ed25519PrivateKey):
                return priv
        except Exception:
            pass
    
    # Generate new key
    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(path, "wb") as f:
        f.write(pem)
    return priv


def pubkey_bytes(priv: ed25519.Ed25519PrivateKey) -> bytes:
    """
    Extract public key bytes from a private key.
    
    Args:
        priv: Ed25519 private key
        
    Returns:
        Raw public key bytes (32 bytes)
    """
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )

