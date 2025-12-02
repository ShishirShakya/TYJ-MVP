"""
Merkle tree utilities for exam.ipynb.

This module provides functions for building Merkle trees from exam answers
for cryptographic integrity verification.
"""

import hashlib
from typing import List, Dict, Any


def leaf_hash(ts_iso: str, text: str) -> bytes:
    """
    Create a Merkle tree leaf hash from timestamp and text.
    
    Args:
        ts_iso: ISO format timestamp string
        text: Answer text
        
    Returns:
        SHA-256 hash digest (32 bytes)
    """
    return hashlib.sha256((ts_iso + "\n" + text).encode("utf-8")).digest()


def merkle_root_from_leaves(leaves: List[bytes]) -> bytes:
    """
    Calculate Merkle root from a list of leaf hashes.
    
    Args:
        leaves: List of leaf hash bytes (each 32 bytes)
        
    Returns:
        Merkle root hash (32 bytes)
    """
    if not leaves:
        return hashlib.sha256(b"").digest()
    
    layer = [hashlib.sha256(x).digest() for x in leaves]
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            a = layer[i]
            b = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(hashlib.sha256(a + b).digest())
        layer = nxt
    return layer[0]


def answers_to_merkle(answer_items: List[Dict[str, Any]]) -> bytes:
    """
    Convert a list of answer items to a Merkle root.
    
    Each answer item must have 'ts_iso' and 'text' keys.
    
    Args:
        answer_items: List of answer dictionaries with 'ts_iso' and 'text' keys
        
    Returns:
        Merkle root hash (32 bytes)
    """
    leaves = [leaf_hash(a["ts_iso"], a["text"]) for a in answer_items]
    return merkle_root_from_leaves(leaves)

