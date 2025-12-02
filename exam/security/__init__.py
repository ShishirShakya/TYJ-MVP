"""
Security and cryptography utilities for exam.ipynb - OTET, device keys, Merkle trees, and security logging.

This module contains security functions used only by exam.ipynb.
Functions used by multiple apps are in shared/.
"""

from exam.security.otet import get_otet
from exam.security.device_key import get_or_create_device_key, pubkey_bytes
from exam.security.merkle import leaf_hash, merkle_root_from_leaves, answers_to_merkle
from exam.security.logging import log_security_event

__all__ = [
    "get_otet",
    "get_or_create_device_key",
    "pubkey_bytes",
    "leaf_hash",
    "merkle_root_from_leaves",
    "answers_to_merkle",
    "log_security_event",
]

