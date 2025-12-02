"""
Cryptography utilities for prof.ipynb - passphrase generation.

This module contains cryptography functions used only by prof.ipynb.
Functions used by multiple apps are in shared/.
"""

import base64
import secrets


def generate_secure_passphrase(length: int = 16) -> str:
    """
    Generate cryptographically secure random passphrase.
    Uses URL-safe base64 encoding for readability.
    Length parameter controls bytes, resulting passphrase may be slightly longer.
    
    Args:
        length: Number of random bytes to generate (default: 16)
        
    Returns:
        Secure random passphrase (URL-safe base64 encoded)
    """
    # Generate random bytes
    random_bytes = secrets.token_bytes(length)
    # Encode as URL-safe base64 (removes padding for cleaner passphrase)
    passphrase = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return passphrase

