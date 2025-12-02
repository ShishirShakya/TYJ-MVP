"""
OTET (One-Time Exam Token) utilities for exam.ipynb.

This module provides functions for generating OTET tokens used for
cheating-proof exam sessions.
"""

import os
import base64


def get_otet() -> str:
    """
    Generate a One-Time Exam Token (OTET).
    
    Returns:
        Base64-encoded URL-safe random token (16 bytes, padding stripped)
    """
    return base64.urlsafe_b64encode(os.urandom(16)).decode().rstrip("=")

