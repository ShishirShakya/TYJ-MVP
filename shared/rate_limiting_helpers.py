"""
Rate limiting helper functions for use in handlers.

These functions are designed to be injected via dependency injection
and preserve the existing wiring pattern.
"""

from typing import Dict, Any, Optional, Tuple
from shared.rate_limiting import RateLimiter, get_default_rate_limiter


def check_rate_limit_for_state(
    state: Dict[str, Any],
    rate_limiter: Optional[RateLimiter] = None,
    key_type: str = "session"
) -> Tuple[bool, Optional[str]]:
    """
    Check rate limit for a request based on state.
    
    This function extracts a rate limit key from state and checks it.
    Designed to be injected via dependencies dict.
    
    Args:
        state: State dictionary (must have session_id or ip_address)
        rate_limiter: RateLimiter instance (defaults to global instance)
        key_type: Type of key to use ("session", "ip", or "user")
        
    Returns:
        Tuple of (allowed: bool, error_message: Optional[str])
    """
    if rate_limiter is None:
        rate_limiter = get_default_rate_limiter()
    
    # Extract key from state based on key_type
    if key_type == "session":
        key = state.get("session_id", "unknown")
    elif key_type == "ip":
        key = state.get("ip_address", "unknown")
    elif key_type == "user":
        key = state.get("student_id", state.get("session_id", "unknown"))
    else:
        key = state.get("session_id", "unknown")
    
    return rate_limiter.check_rate_limit(key)


def create_rate_limit_middleware(
    rate_limiter: Optional[RateLimiter] = None,
    key_type: str = "session"
):
    """
    Create a rate limit middleware function.
    
    This can be used as a decorator or called explicitly in handlers.
    
    Args:
        rate_limiter: RateLimiter instance (defaults to global instance)
        key_type: Type of key to use ("session", "ip", or "user")
        
    Returns:
        Middleware function that checks rate limits
    """
    if rate_limiter is None:
        rate_limiter = get_default_rate_limiter()
    
    def middleware(state: Dict[str, Any], *args, **kwargs) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Rate limit middleware.
        
        Args:
            state: State dictionary
            *args: Additional arguments (passed through)
            **kwargs: Additional keyword arguments (passed through)
            
        Returns:
            Tuple of (allowed: bool, error_message: Optional[str], state: Dict)
        """
        allowed, error_msg = check_rate_limit_for_state(state, rate_limiter, key_type)
        
        if not allowed:
            # Add rate limit violation to security events
            if "security_events" in state:
                state["security_events"].append({
                    "ts_iso": None,  # Will be set by log_security_event if used
                    "type": "RATE_LIMIT_EXCEEDED",
                    "detail": {"key_type": key_type, "error": error_msg}
                })
        
        return allowed, error_msg, state
    
    return middleware

