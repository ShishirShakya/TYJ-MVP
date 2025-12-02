"""
Deterministic UUID generation utilities.

This module provides deterministic UUID generation for testing and reproducible behavior,
while maintaining security for production use.

DETERMINISTIC: Same inputs → same outputs everywhere (Principle #5).
When randomness is necessary, make it seedable and injected, not global.
"""

import uuid
import os
from typing import Optional


def generate_deterministic_uuid(seed: Optional[str] = None, namespace: Optional[uuid.UUID] = None) -> str:
    """
    Generate a deterministic UUID from a seed.
    
    DETERMINISTIC: Same seed → same UUID (Principle #5).
    Useful for testing and reproducible behavior.
    
    Args:
        seed: Optional seed string (if None, generates random UUID)
        namespace: Optional UUID namespace (defaults to DNS namespace)
        
    Returns:
        UUID string (deterministic if seed provided, random otherwise)
        
    Example:
        # Deterministic (for testing)
        uuid1 = generate_deterministic_uuid("test_seed_123")
        uuid2 = generate_deterministic_uuid("test_seed_123")
        assert uuid1 == uuid2  # Same seed → same UUID
        
        # Random (for production)
        uuid3 = generate_deterministic_uuid()  # Random UUID
    """
    if seed is None:
        # Production: Generate random UUID (secure)
        return str(uuid.uuid4())
    
    # Testing: Generate deterministic UUID from seed
    if namespace is None:
        namespace = uuid.NAMESPACE_DNS
    
    # Create deterministic UUID from seed
    return str(uuid.uuid5(namespace, seed))


def generate_session_id(seed: Optional[str] = None, test_mode: bool = False) -> str:
    """
    Generate a session ID with optional determinism for testing.
    
    DETERMINISTIC: In test mode, same seed → same session ID (Principle #5).
    In production, generates random UUID for security.
    
    Args:
        seed: Optional seed string (only used in test_mode)
        test_mode: If True, generates deterministic UUID from seed
        
    Returns:
        Session ID string
        
    Example:
        # Production (random)
        session_id = generate_session_id()
        
        # Testing (deterministic)
        session_id = generate_session_id("test_session_1", test_mode=True)
    """
    if test_mode and seed:
        return generate_deterministic_uuid(seed)
    return str(uuid.uuid4())


def generate_request_id(seed: Optional[str] = None, test_mode: bool = False) -> str:
    """
    Generate a request ID with optional determinism for testing.
    
    DETERMINISTIC: In test mode, same seed → same request ID (Principle #5).
    In production, generates random UUID for security.
    
    Args:
        seed: Optional seed string (only used in test_mode)
        test_mode: If True, generates deterministic UUID from seed
        
    Returns:
        Request ID string
    """
    if test_mode and seed:
        return generate_deterministic_uuid(seed)
    return str(uuid.uuid4())


__all__ = [
    "generate_deterministic_uuid",
    "generate_session_id",
    "generate_request_id",
]

