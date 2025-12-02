"""
Authentication dependencies for FastAPI endpoints.

This module provides authentication and rate limiting dependencies
to avoid circular imports between main.py and route modules.
"""

from fastapi import Request, Depends, HTTPException
from app.main import check_rate_limit


def require_auth(request: Request, api_key: str = Depends(check_rate_limit)) -> str:
    """
    Dependency that requires authentication and rate limiting.
    
    Phase 3.4: Enhanced with security audit logging.
    
    Args:
        request: FastAPI request object
        api_key: API key from check_rate_limit dependency
        
    Returns:
        The authenticated API key
        
    Raises:
        HTTPException: If rate limit exceeded (from check_rate_limit)
    """
    # Phase 3.4: Log authentication success
    try:
        from shared.security_audit import log_authentication_event
        client_ip = request.client.host if request.client else "unknown"
        log_authentication_event(
            user_id=f"api_key:{api_key[:8]}...",
            event_type="API_AUTH_SUCCESS",
            success=True,
            ip_address=client_ip
        )
    except Exception:
        pass  # Don't fail auth if audit logging fails
    
    return api_key

