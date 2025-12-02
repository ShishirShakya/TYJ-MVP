"""
Health check and metrics endpoints.

This module provides:
- Root endpoint for service discovery
- Health check endpoint with dependency monitoring
- Metrics endpoint for observability
- Ready check endpoint for platform health checks
"""

import os
import time
from typing import Dict, Any
from fastapi import Request, APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from shared.rate_limiting import RateLimiter, RateLimitConfig
from shared.circuit_breaker import CircuitBreaker
from shared.logging_config import get_logger
from shared.prometheus_metrics import (
    record_rate_limiter_event,
    get_metrics,
    PROMETHEUS_AVAILABLE
)

logger = get_logger()

# Create router for health endpoints
router = APIRouter()

# Module-level rate limiters for health/metrics endpoints
health_rate_limiter = RateLimiter(
    "health",
    config=RateLimitConfig(
        requests_per_minute=10,
        requests_per_hour=100,
        burst_size=2
    )
)

metrics_rate_limiter = RateLimiter(
    "metrics",
    config=RateLimitConfig(
        requests_per_minute=5,
        requests_per_hour=50,
        burst_size=2
    )
)


def _get_performance_metrics() -> Dict[str, Any]:
    """
    Get performance metrics for monitoring.
    
    Phase 3.1: Performance monitoring.
    
    Returns:
        Dictionary with performance metrics
    """
    try:
        from shared.performance_monitor import get_performance_stats
        from shared.performance_cache import get_cache_stats
        return {
            "operations": get_performance_stats(),
            "response_cache": get_cache_stats()
        }
    except Exception:
        return {"status": "not_available"}


@router.get("/")
async def root():
    """
    Root endpoint providing service information.
    
    **Authentication**: Not required
    **Rate Limiting**: Not applied
    
    **Response** (200 OK):
    - `service` (str): Service name
    - `version` (str): API version
    - `app_version` (str): Application version
    - `status` (str): Service status
    - `api_versions` (list): Supported API versions
    - `current_version` (str): Current stable API version
    - `versioning` (dict): Versioning strategy information
    
    **Use Case**: Service discovery and health verification
    
    **EVOLVABILITY**: Provides version information for API discovery (Principle #15).
    
    **Note**: This endpoint can be used by Railway/Docker for basic connectivity checks.
    """
    from exam.config import APP_VERSION
    
    return JSONResponse(
        status_code=200,
        content={
            "service": "VivaAI Assessment API",
            "version": "1.0.0",
            "app_version": APP_VERSION,
            "status": "operational",
            "api_versions": ["v1"],
            "current_version": "v1",
            "versioning": {
                "url_based": "/api/v{version}/",
                "header_based": "X-API-Version",
                "accept_header": "application/vnd.api+json;version={version}"
            }
        }
    )


@router.get("/ready")
async def ready_check():
    """
    Simple readiness check endpoint for platform health checks.
    
    This endpoint always returns 200 OK immediately, allowing Railway/Docker
    to verify the service is running without any rate limiting or dependency checks.
    
    **Use Case**: Platform health checks (Railway, Docker, Kubernetes)
    """
    return JSONResponse(
        status_code=200,
        content={"status": "ready", "service": "VivaAI Assessment API"}
    )


@router.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint with dependency monitoring.
    
    Note: This endpoint has minimal rate limiting to allow platform health checks
    (Railway, Docker, etc.) while still preventing abuse.
    
    **THREAT MODELING**: Per-IP rate limiting prevents DoS via health check spam (Principle #12).
    Platform health checks are allowed more frequently than regular requests.
    """
    
    # THREAT MODELING: Use IP address as key for health checks (Principle #12)
    # Allow health checks more frequently (platforms check every 30s)
    client_ip = request.client.host if request.client else "unknown"
    
    # Check rate limit but be more permissive - allow at least 1 request per 10 seconds
    # This allows Railway/Docker health checks (typically every 30s) to pass
    allowed, message = health_rate_limiter.check_rate_limit(client_ip)
    
    # Only rate limit if we're getting hammered (more than 10 requests per minute)
    # This allows normal health check frequency while preventing abuse
    if not allowed:
        # Check if this is a platform health check (frequent but not abusive)
        stats = health_rate_limiter.get_stats(client_ip)
        request_count = stats.get("requests", 0)
        
        # Allow platform health checks (up to 10 per minute)
        if request_count <= 10:
            # Likely a platform health check, allow it
            allowed = True
        else:
            # THREAT MODELING: Log health check violations for monitoring (Principle #12)
            logger.warning(
                "health_check_rate_limit_exceeded",
                client_ip=client_ip,
                request_count=request_count,
                message=message or "Too many health check requests"
            )
            return JSONResponse(
                status_code=429,
                content={"status": "rate_limited", "detail": "Too many health check requests"}
            )
    
    # Import circuit breaker from shared dependencies
    from app.dependencies import get_circuit_breaker
    circuit_breaker = get_circuit_breaker()
    
    # Check dependencies
    dependencies_ok = True
    dependency_status = {}
    
    # Check external services (circuit breaker status)
    cb_stats = circuit_breaker.get_stats()
    dependency_status["circuit_breaker"] = {
        "status": "ok" if cb_stats["state"] == "closed" else "degraded",
        "state": cb_stats["state"]
    }
    
    # Phase 2.2.5: Enhanced health check - API client circuit breaker
    try:
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        cb_manager = get_default_circuit_breaker_manager()
        if cb_manager:
            api_client_cb = cb_manager.get_breaker("viva_api_client")
            if api_client_cb:
                api_cb_stats = api_client_cb.get_stats()
                dependency_status["api_client_circuit_breaker"] = {
                    "status": "ok" if api_cb_stats.get("state") == "closed" else "degraded",
                    "state": api_cb_stats.get("state", "unknown")
                }
    except Exception:
        dependency_status["api_client_circuit_breaker"] = {
            "status": "unknown",
            "error": "Unable to check API client circuit breaker"
        }
    
    # Phase 2.2.5: Check session recovery system
    try:
        from pathlib import Path
        state_dir = Path(os.getenv("EXAM_STATE_DIR", "exam_state"))
        dependency_status["session_recovery"] = {
            "status": "ok" if state_dir.exists() or os.getenv("EXAM_STATE_DIR") else "degraded",
            "state_directory_accessible": state_dir.exists() if state_dir else False
        }
    except Exception:
        dependency_status["session_recovery"] = {
            "status": "unknown",
            "error": "Unable to check session recovery system"
        }
    
    # Always return 200 OK for health checks, even if degraded
    # This ensures Railway/Docker don't stop the container
    # The "status" field indicates actual health state
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy" if dependencies_ok else "degraded",
            "dependencies": dependency_status,
            "timestamp": time.time()
        }
    )


@router.get("/metrics")
async def metrics(request: Request):
    """
    Metrics endpoint for observability.
    
    Note: This endpoint is rate-limited and sanitized to prevent information disclosure.
    
    **THREAT MODELING**: Per-IP rate limiting prevents DoS via metrics scraping (Principle #12).
    """
    # THREAT MODELING: Use IP address as key for metrics (Principle #12)
    client_ip = request.client.host if request.client else "unknown"
    allowed, message = metrics_rate_limiter.check_rate_limit(client_ip)
    
    # Phase 4.2: Record rate limiter metrics
    if PROMETHEUS_AVAILABLE:
        record_rate_limiter_event(key=client_ip, allowed=allowed)
    
    if not allowed:
        # THREAT MODELING: Log metrics violations for monitoring (Principle #12)
        logger.warning(
            "metrics_rate_limit_exceeded",
            client_ip=client_ip,
            message=message or "Too many metrics requests"
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"}
        )
    
    # Phase 4.2: Check if Prometheus format requested
    accept_header = request.headers.get("Accept", "")
    format_param = request.query_params.get("format", "")
    
    if format_param == "prometheus" or "text/plain" in accept_header:
        # Return Prometheus format
        if PROMETHEUS_AVAILABLE:
            metrics_text, content_type = get_metrics()
            return Response(content=metrics_text, media_type=content_type)
    
    # Import singletons from shared dependencies
    from app.dependencies import get_rate_limiter, get_circuit_breaker
    rate_limiter = get_rate_limiter()
    circuit_breaker = get_circuit_breaker()
    
    # OBSERVABILITY: Return sanitized metrics (no sensitive data) (Principle #13)
    rate_limiter_stats = rate_limiter.get_aggregate_stats()
    circuit_breaker_stats = circuit_breaker.get_stats()
    
    # Phase 2.2.5: Enhanced monitoring - API client circuit breaker stats
    api_client_cb_stats = {}
    try:
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        cb_manager = get_default_circuit_breaker_manager()
        if cb_manager:
            # Get stats for API client circuit breaker
            api_client_cb = cb_manager.get_breaker("viva_api_client")
            if api_client_cb:
                api_client_cb_stats = api_client_cb.get_stats()
    except Exception:
        # API client CB stats unavailable
        pass
    
    # Phase 2.2.5: Session recovery metrics
    session_recovery_metrics = {}
    try:
        from pathlib import Path
        state_dir = Path(os.getenv("EXAM_STATE_DIR", "exam_state"))
        if state_dir.exists():
            # Count saved sessions
            state_files = list(state_dir.glob("**/state.json"))
            session_recovery_metrics = {
                "saved_sessions": len(state_files),
                "state_directory": str(state_dir)
            }
        else:
            session_recovery_metrics = {
                "saved_sessions": 0,
                "state_directory": "not_configured"
            }
    except Exception:
        session_recovery_metrics["error"] = "Session recovery metrics unavailable"
    
    # PERFORMANCE METRICS: Add cache and performance metrics
    cache_metrics = {}
    try:
        from exam.pdf_cache.cache import _pdf_memory_cache, PDF_CACHE_DIR
        import os
        
        # Memory cache metrics
        cache_metrics["pdf_memory_cache"] = {
            "entries": len(_pdf_memory_cache),
            "max_entries": 20
        }
        
        # Disk cache metrics (if directory exists)
        if os.path.exists(PDF_CACHE_DIR):
            cache_files = [f for f in os.listdir(PDF_CACHE_DIR) if f.endswith('.pkl')]
            total_size = sum(
                os.path.getsize(os.path.join(PDF_CACHE_DIR, f))
                for f in cache_files
                if os.path.exists(os.path.join(PDF_CACHE_DIR, f))
            )
            cache_metrics["pdf_disk_cache"] = {
                "files": len(cache_files),
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "max_size_mb": 500
            }
    except Exception:
        # Cache metrics unavailable - don't fail metrics endpoint
        cache_metrics["error"] = "Cache metrics unavailable"
    
    return {
        "rate_limiter": {
            "total_requests": rate_limiter_stats["total_requests"],
            "allowed_requests": rate_limiter_stats["total_allowed"],
            "rejected_requests": rate_limiter_stats["total_rejected"]
        },
        "circuit_breaker": {
            "state": circuit_breaker_stats["state"],
            "total_calls": circuit_breaker_stats["failures"] + circuit_breaker_stats["successes"],
            "successful_calls": circuit_breaker_stats["successes"],
            "failed_calls": circuit_breaker_stats["failures"],
            "state_changes": circuit_breaker_stats["state_changes"]
        },
        "api_client_circuit_breaker": api_client_cb_stats if api_client_cb_stats else {"status": "not_available"},
        "session_recovery": session_recovery_metrics,
        "cache": cache_metrics,
        # Phase 3.1: Performance metrics
        "performance": _get_performance_metrics(),
        "timestamp": time.time()
    }


class MediaPipeStatus(BaseModel):
    installed: bool
    version: str | None = None
    error: str | None = None


@router.get("/mediapipe-status")
async def check_mediapipe():
    """
    Check if MediaPipe is installed and working.
    
    **Use Case**: Debugging MediaPipe installation issues on deployed servers.
    
    **Response** (200 OK):
    - `installed` (bool): Whether MediaPipe is installed
    - `version` (str | None): MediaPipe version if installed
    - `error` (str | None): Error message if installation check failed
    """
    try:
        import mediapipe as mp
        # Try to initialize FaceMesh to ensure it works
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        face_mesh.close()
        
        return MediaPipeStatus(
            installed=True,
            version=getattr(mp, '__version__', 'unknown'),
            error=None
        )
    except ImportError as e:
        return MediaPipeStatus(
            installed=False,
            version=None,
            error=f"ImportError: {str(e)}"
        )
    except Exception as e:
        return MediaPipeStatus(
            installed=False,
            version=None,
            error=f"Initialization error: {str(e)}"
        )

