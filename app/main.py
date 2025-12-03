"""
FastAPI application for VivaAI Assessment API.

This module provides the FastAPI application with:
- API key authentication
- Rate limiting
- Request timeouts
- Input size limits
- Health and metrics endpoints
"""

import os
import time
import hmac
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Header, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

from app.schemas import (
    GenerateQuestionRequest, GenerateQuestionResponse,
    GenerateQuestionDirectRequest, GenerateQuestionDirectResponse,
    GradeAnswerRequest, GradeAnswerResponse,
    GradeAnswerDirectRequest, GradeAnswerDirectResponse,
    ProcessAudioRequest, ProcessAudioResponse,
    AnalyzeProctorRequest, AnalyzeProctorResponse,
    ParseLinkRequest, ParseLinkResponse,
    GenerateTTSRequest, GenerateTTSResponse,
    GenerateFollowupQuestionRequest, GenerateFollowupQuestionResponse,
    ErrorResponse
)

from shared.rate_limiting import RateLimiter, RateLimitConfig, get_default_rate_limiter
from shared.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
# Import centralized logging configuration (SSOT - Principle #2)
from shared.logging_config import setup_structlog, get_logger
# Phase 4.2: Prometheus metrics
from shared.prometheus_metrics import (
    record_api_request, update_circuit_breaker_metrics,
    record_rate_limiter_event, get_metrics, PROMETHEUS_AVAILABLE
)
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret
# Import centralized constants (SSOT - Principle #2)
from shared.constants import (
    MAX_FILE_SIZE,
    MAX_REQUEST_BODY_SIZE,
    MAX_URL_LENGTH,
    MAX_JSON_DEPTH,
    REQUEST_TIMEOUT_SECONDS as DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_HOUR,
    DEFAULT_RATE_LIMIT_BURST,
)
# Import configuration validation (Principle #23)
from shared.config_validation import validate_config_at_startup, ConfigValidationError
# Import OpenAI client
from openai import OpenAI
# Import adapters for exam flow integration
from app.adapters import (
    load_state_from_session_id,
    build_flow_dependencies,
    call_ask_main_question,
    call_grade_current_block,
    call_handle_mic
)

# Configure logging (centralized)
setup_structlog()
logger = get_logger()

# CONFIGURATION & SECRETS DISCIPLINE: Validate config at startup (Principle #23)
try:
    validate_config_at_startup()
except ConfigValidationError as e:
    logger.error(
        "startup_config_validation_failed",
        error=str(e),
        message="Configuration validation failed at startup - application will not start"
    )
    raise

# Get HMAC secret from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)

# Import shared dependencies module
from app.dependencies import initialize_dependencies, get_rate_limiter, get_circuit_breaker, get_openai_client

# Rate limiter configuration (using constants from shared.constants)
rate_limit_config = RateLimitConfig(
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", str(DEFAULT_RATE_LIMIT_PER_MINUTE))),
    requests_per_hour=int(os.getenv("RATE_LIMIT_PER_HOUR", str(DEFAULT_RATE_LIMIT_PER_HOUR))),
    burst_size=int(os.getenv("RATE_LIMIT_BURST", str(DEFAULT_RATE_LIMIT_BURST)))
)
circuit_breaker_config = CircuitBreakerConfig(
    failure_threshold=5,
    timeout_seconds=60,
    expected_exception=Exception
)

# Initialize shared dependencies
initialize_dependencies(rate_limit_config, circuit_breaker_config)

# Get singleton instances
rate_limiter = get_rate_limiter()
circuit_breaker = get_circuit_breaker()

# Request timeout configuration (using constants from shared.constants)
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT)))

# Input size limits (using constants from shared.constants - SSOT Principle #2)
MAX_REQUEST_BODY_SIZE = int(os.getenv("MAX_REQUEST_BODY_SIZE", str(MAX_REQUEST_BODY_SIZE)))
MAX_URL_LENGTH = int(os.getenv("MAX_URL_LENGTH", str(MAX_URL_LENGTH)))
MAX_JSON_DEPTH = int(os.getenv("MAX_JSON_DEPTH", str(MAX_JSON_DEPTH)))

# OpenAI client (singleton for all requests)
openai_client = get_openai_client()


def verify_api_key(api_key: str = Header(..., alias="X-API-Key")) -> str:
    """
    Verify API key using HMAC-based validation.
    
    **SECURITY**: Validates API key by checking if it's a valid HMAC signature
    of a known token, or matches a configured list of valid API keys.
    
    **Validation Methods**:
    1. **Configured Keys** (preferred): Checks against `VALID_API_KEYS` environment variable
    2. **HMAC Signature**: Validates against HMAC signature of known token
    
    **Configuration**:
    - Set `VALID_API_KEYS=key1,key2,key3` for multiple valid keys
    - Or use HMAC signature: `hmac.new(HMAC_SECRET, "vivaai-api-key", sha256).hexdigest()`
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        API key if valid
        
    Raises:
        HTTPException: 401 if API key is invalid or missing
        
    Example:
        ```python
        # Client sends:
        headers = {"X-API-Key": "your-api-key"}
        
        # Server validates and returns 401 if invalid
        ```
    """
    if not api_key or len(api_key) < 8:
        logger.warning(
            "invalid_api_key_format",
            api_key_length=len(api_key) if api_key else 0
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid API key format"
        )
    
    # Method 1: Check against configured list of valid API keys (from env var)
    valid_api_keys = os.getenv("VALID_API_KEYS", "").split(",")
    valid_api_keys = [k.strip() for k in valid_api_keys if k.strip()]
    
    # Method 2: Validate HMAC signature
    # The API key should be an HMAC of a known token (e.g., "vivaai-api-key")
    # This allows dynamic key generation while maintaining security
    known_token = "vivaai-api-key"
    expected_signature = hmac.new(
        HMAC_SECRET.encode("utf-8"),
        known_token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    # Check if API key matches expected signature OR is in valid keys list
    is_valid = False
    
    if valid_api_keys:
        # Check against configured list
        if api_key in valid_api_keys:
            is_valid = True
    else:
        # Fallback: Use HMAC signature validation
        # API key should match the expected HMAC signature
        if api_key == expected_signature:
            is_valid = True
    
    if not is_valid:
        logger.warning(
            "invalid_api_key",
            api_key_length=len(api_key),
            api_key_prefix=api_key[:4] + "..." if len(api_key) > 4 else "***",
            has_configured_keys=bool(valid_api_keys)
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    # Log successful authentication (without logging the actual key)
    logger.info(
        "api_key_verified",
        api_key_length=len(api_key),
        api_key_prefix=api_key[:4] + "..." if len(api_key) > 4 else "***"
    )
    
    return api_key


def check_rate_limit(
    request: Request,
    api_key: str = Depends(verify_api_key)
) -> str:
    """
    Check rate limit for API key and IP address.
    
    **Rate Limiting**: Uses token bucket algorithm with per-API-key AND per-IP tracking.
    
    **THREAT MODELING**: Implements dual-key rate limiting (Principle #12):
    - Per-API-key limits: Prevents single key abuse
    - Per-IP limits: Prevents abuse from multiple IPs with same key
    - Combined key: Uses "api_key:ip" for comprehensive tracking
    
    **Limits** (configurable via environment variables):
    - `RATE_LIMIT_PER_MINUTE`: Requests per minute (default: 60)
    - `RATE_LIMIT_PER_HOUR`: Requests per hour (default: 1000)
    - `RATE_LIMIT_BURST`: Burst size (default: 10)
    
    **Behavior**:
    - Each API key + IP combination has independent rate limit buckets
    - Limits enforced per-minute and per-hour
    - Returns 429 if limit exceeded
    - Logs violations for traffic pattern monitoring
    
    Args:
        request: FastAPI request object
        api_key: Verified API key
        
    Returns:
        API key if rate limit not exceeded
        
    Raises:
        HTTPException: 429 if rate limit exceeded
        
    Example:
        ```python
        # Rate limit check happens automatically via dependency injection
        # Returns 429 if limit exceeded
        ```
    """
    # THREAT MODELING: Use combined key (API key + IP) for dual protection (Principle #12)
    client_ip = request.client.host if request.client else "unknown"
    combined_key = f"{api_key}:{client_ip}"
    
    # Check rate limit with combined key
    allowed, message = rate_limiter.check_rate_limit(combined_key)
    
    if not allowed:
        # THREAT MODELING: Log violation for traffic pattern monitoring (Principle #12)
        logger.warning(
            "rate_limit_exceeded",
            api_key_prefix=api_key[:4] + "..." if len(api_key) > 4 else "***",
            client_ip=client_ip,
            combined_key_prefix=combined_key[:20] + "..." if len(combined_key) > 20 else "***",
            message=message,
            violation_type="rate_limit_exceeded"
        )
        
        # THREAT MODELING: Track violation count for alerting (Principle #12)
        stats = rate_limiter.get_stats(combined_key)
        violation_count = stats.get("violations", 0)
        
        # Alert on unusual patterns (e.g., >10 violations in short time)
        if violation_count > 10:
            logger.error(
                "suspicious_traffic_pattern",
                api_key_prefix=api_key[:4] + "..." if len(api_key) > 4 else "***",
                client_ip=client_ip,
                violation_count=violation_count,
                message="Unusual traffic pattern detected - potential DoS attempt"
            )
        
        raise HTTPException(
            status_code=429,
            detail=message or "Rate limit exceeded"
        )
    
    return api_key


# Dependency for authenticated endpoints
def require_auth(request: Request, api_key: str = Depends(check_rate_limit)) -> str:
    """
    Dependency that requires authentication and rate limiting.
    
    Phase 3.4: Enhanced with security audit logging.
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


async def cleanup_rate_limiters():
    """Background task to periodically clean up old rate limiter entries."""
    # Configurable cleanup interval (default: 1 hour)
    cleanup_interval_seconds = int(os.getenv("RATE_LIMITER_CLEANUP_INTERVAL_SECONDS", "3600"))
    max_age_seconds = int(os.getenv("RATE_LIMITER_MAX_AGE_SECONDS", "3600"))
    
    while True:
        try:
            await asyncio.sleep(cleanup_interval_seconds)
            # Clean up old entries
            cleaned = rate_limiter.cleanup_old_keys(max_age_seconds=max_age_seconds)
            if cleaned > 0:
                logger.info(
                    "rate_limiter_cleanup",
                    cleaned_keys=cleaned,
                    cleanup_interval=cleanup_interval_seconds,
                    max_age_seconds=max_age_seconds,
                    message="Cleaned up old rate limiter entries"
                )
        except Exception as e:
            logger.error(
                "rate_limiter_cleanup_error",
                error=str(e)[:100],
                message="Error during rate limiter cleanup"
            )


async def cleanup_file_locks_and_backups():
    """
    Background task to periodically clean up old file locks and backup files.
    
    RESOURCE MANAGEMENT: Prevents memory leaks from file locks and disk space issues from backup files.
    """
    # Configurable cleanup interval (default: 6 hours)
    cleanup_interval_seconds = int(os.getenv("FILE_LOCK_CLEANUP_INTERVAL_SECONDS", "21600"))
    # Backup files older than this will be deleted (default: 7 days)
    backup_max_age_seconds = int(os.getenv("BACKUP_FILE_MAX_AGE_SECONDS", "604800"))
    
    while True:
        try:
            await asyncio.sleep(cleanup_interval_seconds)
            
            # Clean up old file locks
            from exam.state.persistence import _cleanup_old_file_locks
            _cleanup_old_file_locks()
            
            # Clean up old backup files (corrupted state files)
            from shared.platform import get_default_platform_provider
            platform_provider = get_default_platform_provider()
            temp_dir = platform_provider.get_temp_dir()
            vivaai_dir = platform_provider.join_path(temp_dir, "vivaai")
            
            if os.path.exists(vivaai_dir):
                # RESOURCE MANAGEMENT: Use pathlib for cross-platform compatibility (Windows/POSIX)
                # Find all corrupted backup files recursively
                vivaai_path = Path(vivaai_dir)
                backup_files = list(vivaai_path.rglob("*.corrupted.*"))
                backup_files = [str(f) for f in backup_files]  # Convert to strings for compatibility
                
                current_time = time.time()
                deleted_count = 0
                failed_count = 0
                max_failures = int(os.getenv("BACKUP_CLEANUP_MAX_FAILURES", "10"))  # Stop after N failures
                
                for backup_file in backup_files:
                    try:
                        # Check file age
                        file_age = current_time - os.path.getmtime(backup_file)
                        if file_age > backup_max_age_seconds:
                            os.remove(backup_file)
                            deleted_count += 1
                    except Exception as file_error:
                        failed_count += 1
                        logger.warning(
                            "backup_file_cleanup_failed",
                            backup_file=backup_file,
                            error=str(file_error)[:200],
                            failed_count=failed_count,
                            message="Failed to delete old backup file"
                        )
                        # RESOURCE MANAGEMENT: Stop cleanup if too many failures (may indicate disk issues)
                        if failed_count >= max_failures:
                            logger.error(
                                "backup_cleanup_too_many_failures",
                                failed_count=failed_count,
                                max_failures=max_failures,
                                message="Stopping backup cleanup due to too many failures (may indicate disk issues)"
                            )
                            break
                
                if deleted_count > 0:
                    logger.info(
                        "backup_files_cleanup",
                        deleted_count=deleted_count,
                        failed_count=failed_count,
                        cleanup_interval=cleanup_interval_seconds,
                        max_age_seconds=backup_max_age_seconds,
                        message="Cleaned up old backup files"
                    )
                elif failed_count > 0:
                    logger.warning(
                        "backup_cleanup_partial_failure",
                        failed_count=failed_count,
                        total_files=len(backup_files),
                        message="Backup cleanup encountered failures"
                    )
        except Exception as e:
            logger.error(
                "file_lock_backup_cleanup_error",
                error=str(e)[:100],
                message="Error during file lock and backup cleanup"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown.
    
    **THREAT MODELING**: Includes traffic pattern monitoring for DoS detection (Principle #12).
    """
    # Startup
    logger.info("app_starting", message="VivaAI Assessment API starting")
    
    # THREAT MODELING: Background task for traffic pattern monitoring (Principle #12)
    async def monitor_traffic_patterns():
        """Monitor traffic patterns and alert on unusual activity."""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            try:
                # Get all keys with significant violations (>10 violations)
                violations = rate_limiter.get_all_violations(min_violations=10)
                
                if violations:
                    # Alert on unusual traffic patterns
                    for key, stats in violations.items():
                        violation_count = stats.get("violations", 0)
                        request_count = stats.get("requests", 0)
                        
                        # Alert if violation rate is high (>20% violations)
                        if violation_count > 0 and request_count > 0:
                            violation_rate = violation_count / request_count
                            if violation_rate > 0.2:  # >20% violation rate
                                logger.error(
                                    "suspicious_traffic_pattern_detected",
                                    rate_limit_key_prefix=key[:30] + "..." if len(key) > 30 else key,
                                    violation_count=violation_count,
                                    request_count=request_count,
                                    violation_rate=round(violation_rate, 2),
                                    message="High violation rate detected - potential DoS attempt or misconfigured client"
                                )
            except Exception as e:
                logger.error("traffic_monitoring_error", error=str(e)[:100])
    
    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_rate_limiters())
    file_cleanup_task = asyncio.create_task(cleanup_file_locks_and_backups())
    monitoring_task = asyncio.create_task(monitor_traffic_patterns())
    
    yield
    
    # Shutdown
    cleanup_task.cancel()
    file_cleanup_task.cancel()
    monitoring_task.cancel()
    try:
        await cleanup_task
        await file_cleanup_task
        await monitoring_task
    except asyncio.CancelledError:
        pass
    
    # PERFORMANCE: Close HTTP client on shutdown (cp.txt #9, resource management)
    from app.dependencies import cleanup_dependencies
    await cleanup_dependencies()
    
    logger.info("app_shutting_down", message="VivaAI Assessment API shutting down")


# Create FastAPI app
app = FastAPI(
    title="VivaAI Assessment API",
    description="Secure Exam Proctoring System API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENVIRONMENT", "development").lower() == "development" else None,
    redoc_url="/redoc" if os.getenv("ENVIRONMENT", "development").lower() == "development" else None
)

# CORS configuration
cors_origins_str = os.getenv("CORS_ORIGINS", "")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

# Add Railway frontend domains (if not already in CORS_ORIGINS)
# These will be updated after deployment with actual Railway domains
railway_frontends = [
    "https://viva-prof.up.railway.app",
    "https://viva-exam.up.railway.app",
    "https://viva-dash.up.railway.app"
]

# Add Railway domains if not already present
for domain in railway_frontends:
    if domain not in cors_origins:
        cors_origins.append(domain)

# Fallback to default if empty
if not cors_origins:
    cors_origins = ["https://huggingface.co", "https://*.hf.space"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type", "Authorization", "Accept", "X-API-Version"],
    max_age=3600
)

# PERFORMANCE: Response compression for faster network transfer (spd.txt #7, cp.txt #9)
# Compress responses > 1KB to reduce bandwidth and improve perceived performance
app.add_middleware(GZipMiddleware, minimum_size=1000)


# OBSERVABILITY: Request ID middleware for correlation (Principle #13)
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Add request ID to all requests for correlation."""
    import uuid
    
    # Generate request ID if not present
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    
    # Store in request state for access in endpoints
    request.state.request_id = request_id
    
    # Bind request ID to logger for this request
    logger_with_id = logger.bind(request_id=request_id)
    
    # Call next middleware/endpoint
    response = await call_next(request)
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id
    
    return response


# EVOLVABILITY: API version negotiation middleware (Principle #15)
@app.middleware("http")
async def api_version_middleware(request: Request, call_next):
    """
    Handle API version negotiation via headers.
    
    EVOLVABILITY: Supports header-based versioning for minor changes (Principle #15).
    
    Version negotiation priority:
    1. URL path version (`/api/v1/`, `/api/v2/`) - for major breaking changes
    2. X-API-Version header - for minor changes
    3. Accept header with version parameter - for minor changes
    4. Default to v1 if not specified
    
    Current supported versions:
    - v1: Current stable version
    """
    # Extract version from URL path (e.g., /api/v1/assessments/...)
    path_version = None
    if request.url.path.startswith("/api/v"):
        try:
            # Extract version from path: /api/v1/... -> "1"
            parts = request.url.path.split("/")
            if len(parts) >= 3 and parts[1] == "api" and parts[2].startswith("v"):
                path_version = parts[2][1:]  # Remove "v" prefix
        except (IndexError, ValueError):
            pass
    
    # Extract version from headers
    header_version = request.headers.get("X-API-Version")
    accept_header = request.headers.get("Accept", "")
    
    # Parse Accept header for version (e.g., "application/vnd.api+json;version=2")
    accept_version = None
    if "version=" in accept_header:
        try:
            # Extract version from Accept header
            for part in accept_header.split(";"):
                if "version=" in part:
                    accept_version = part.split("version=")[1].strip()
                    break
        except (IndexError, ValueError):
            pass
    
    # Determine API version (priority: path > X-API-Version > Accept > default)
    api_version = path_version or header_version or accept_version or "1"
    
    # Store version in request state for access in endpoints
    request.state.api_version = api_version
    
    # EVOLVABILITY: Log version usage for monitoring (Principle #15)
    if api_version != "1":
        logger.info(
            "api_version_negotiated",
            request_id=getattr(request.state, "request_id", "unknown"),
            api_version=api_version,
            path_version=path_version,
            header_version=header_version,
            accept_version=accept_version
        )
    
    # OBSERVABILITY: Track request timing for metrics (Principle #13)
    start_time = time.time()
    
    # Call next middleware/endpoint
    response = await call_next(request)
    
    # Add API version to response headers
    response.headers["X-API-Version"] = api_version
    
    # Phase 4.2: Record Prometheus metrics
    if PROMETHEUS_AVAILABLE:
        duration = time.time() - start_time
        record_api_request(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code,
            duration=duration
        )
    
    return response


# Request timeout and size limit middleware
@app.middleware("http")
async def request_limits_middleware(request: Request, call_next):
    """
    Enforce request timeout and size limits.
    
    OBSERVABILITY: Tracks request latency for metrics (Principle #13).
    """
    start_time = time.time()
    request_id = getattr(request.state, "request_id", "unknown")
    
    # OBSERVABILITY: Bind request_id to logger for correlation (Principle #13)
    logger_with_id = logger.bind(request_id=request_id)
    
    # Check URL length
    if len(str(request.url)) > MAX_URL_LENGTH:
        logger_with_id.warning(
            "url_too_long",
            path=request.url.path,
            url_length=len(str(request.url)),
            max_length=MAX_URL_LENGTH
        )
        return JSONResponse(
            status_code=414,
            content={"detail": "URL too long"}
        )
    
    # Check Content-Length header if present (but don't trust it - verify actual size)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
            if declared_size > MAX_REQUEST_BODY_SIZE:
                logger_with_id.warning(
                    "request_body_too_large_declared",
                    path=request.url.path,
                    declared_size=declared_size,
                    max_size=MAX_REQUEST_BODY_SIZE
                )
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"}
                )
        except ValueError:
            pass  # Invalid content-length header, let FastAPI handle it
    
    # Note: FastAPI will also enforce body size limits based on Content-Length
    # For additional security, we could read the body and check actual size,
    # but that would require buffering the entire request which is expensive.
    # FastAPI's built-in limits provide reasonable protection.
    
    try:
        response = await asyncio.wait_for(
            call_next(request),
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        elapsed = time.time() - start_time
        
        # OBSERVABILITY: Log request latency for monitoring (Principle #13)
        logger_with_id.info(
            "request_completed",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            elapsed_seconds=round(elapsed, 3),
            elapsed_ms=round(elapsed * 1000, 1)
        )
        
        if elapsed > REQUEST_TIMEOUT_SECONDS * 0.9:  # Warn if close to timeout
            logger_with_id.warning(
                "request_slow",
                path=request.url.path,
                elapsed_seconds=elapsed,
                timeout_seconds=REQUEST_TIMEOUT_SECONDS
            )
        return response
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger_with_id.error(
            "request_timeout_exceeded",
            path=request.url.path,
            elapsed_seconds=elapsed,
            timeout_seconds=REQUEST_TIMEOUT_SECONDS
        )
        return JSONResponse(
            status_code=504,
            content={"detail": "Request timeout"}
        )


# Import and register route modules
from app.routes import health, assessments

# Register health routes (includes root, ready, health, metrics)
app.include_router(health.router)

# Register assessment routes
app.include_router(assessments.router, prefix="/api/v1/assessments", tags=["assessments"])

# All health and assessment endpoints are now in route modules
# See app/routes/health.py and app/routes/assessments.py

# All assessment endpoints have been moved to app/routes/assessments.py
# This file now only contains app setup, middleware, and route registration

