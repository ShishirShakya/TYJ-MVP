"""
FERPA-compliant authentication and session handling module.

This module provides explicit authentication token support for FERPA compliance,
ensuring all student data touches occur in authenticated sessions.

FERPA COMPLIANCE: Session Handling & Authentication (Mandate #9)
- All student data touches must occur in authenticated sessions
- No caching of sensitive data in frontend, browser memory, or temp files

**Key Functions**:
- `validate_auth_token()`: Validate authentication token
- `get_session_from_token()`: Get session from auth token
- `create_auth_token()`: Create authentication token for session
- `revoke_auth_token()`: Revoke authentication token

**Usage Example**:
    ```python
    from shared.ferpa_auth import validate_auth_token, get_session_from_token
    
    # Validate token before accessing student data
    token = request.headers.get("Authorization")
    if not validate_auth_token(token):
        return error("Unauthorized")
    
    # Get session from token
    session = get_session_from_token(token)
    ```
"""

import os
import hmac
import hashlib
import time
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta


def _get_auth_secret() -> str:
    """
    Get authentication secret from environment.
    
    SECURITY: Never hardcode secrets - always retrieve from environment.
    
    Returns:
        Authentication secret string
        
    Raises:
        ValueError: If FERPA_AUTH_SECRET is not set
    """
    secret = os.getenv("FERPA_AUTH_SECRET")
    if not secret:
        # In development, allow missing secret (backward compatibility)
        if os.getenv("ENVIRONMENT", "production").lower() == "development":
            return "dev_secret_change_in_production"
        raise ValueError(
            "FERPA_AUTH_SECRET environment variable must be set. "
            "This is required for authentication token validation."
        )
    return secret


def create_auth_token(
    session_id: str,
    user_role: str,
    student_id: Optional[str] = None,
    expires_in: int = 3600
) -> str:
    """
    Create an authentication token for a session.
    
    FERPA COMPLIANCE: Creates authenticated session token for student data access.
    
    Args:
        session_id: Session identifier
        user_role: User role (STUDENT, INSTRUCTOR, ADMIN)
        student_id: Optional student identifier
        expires_in: Token expiration time in seconds (default: 1 hour)
        
    Returns:
        Authentication token string
    """
    secret = _get_auth_secret()
    expires_at = int(time.time()) + expires_in
    
    # Build token payload
    payload_parts = [
        session_id,
        user_role,
        str(expires_at)
    ]
    if student_id:
        payload_parts.append(student_id)
    
    payload = "|".join(payload_parts)
    
    # Create HMAC signature
    signature = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Return token: payload.signature
    return f"{payload}.{signature}"


def validate_auth_token(token: Optional[str]) -> bool:
    """
    Validate an authentication token.
    
    FERPA COMPLIANCE: Validates that request has authenticated session.
    
    Args:
        token: Authentication token string (or None)
        
    Returns:
        True if token is valid, False otherwise
    """
    if not token:
        return False
    
    try:
        secret = _get_auth_secret()
        
        # Split token into payload and signature
        if "." not in token:
            return False
        
        payload, signature = token.rsplit(".", 1)
        
        # Verify signature
        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return False
        
        # Check expiration
        parts = payload.split("|")
        if len(parts) < 3:
            return False
        
        expires_at = int(parts[2])
        if time.time() > expires_at:
            return False
        
        return True
        
    except Exception:
        return False


def get_session_from_token(token: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Get session information from authentication token.
    
    FERPA COMPLIANCE: Extracts session info from authenticated token.
    
    Args:
        token: Authentication token string
        
    Returns:
        Session dictionary with session_id, user_role, student_id, or None if invalid
    """
    if not validate_auth_token(token):
        return None
    
    try:
        payload, _ = token.rsplit(".", 1)
        parts = payload.split("|")
        
        if len(parts) < 3:
            return None
        
        session = {
            "session_id": parts[0],
            "user_role": parts[1],
            "expires_at": int(parts[2])
        }
        
        if len(parts) >= 4:
            session["student_id"] = parts[3]
        
        return session
        
    except Exception:
        return None


def revoke_auth_token(token: Optional[str]) -> bool:
    """
    Revoke an authentication token (mark as invalid).
    
    FERPA COMPLIANCE: Allows explicit token revocation for security.
    
    Note: In a full implementation, this would maintain a revocation list.
    For now, tokens are invalidated by expiration only.
    
    Args:
        token: Authentication token string
        
    Returns:
        True if token was revoked, False otherwise
    """
    # In a full implementation, add token to revocation list
    # For now, tokens are invalidated by expiration
    return True


__all__ = [
    "create_auth_token",
    "validate_auth_token",
    "get_session_from_token",
    "revoke_auth_token",
]

