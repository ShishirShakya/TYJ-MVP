"""
Prometheus metrics for VivaAI Assessment System.

Phase 4.2: Monitoring & Alerting - Prometheus metrics integration.

This module provides Prometheus metrics for monitoring API performance,
error rates, circuit breaker states, and other key metrics.
"""

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create dummy classes if prometheus_client not available
    class Counter:
        def __init__(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
    class Histogram:
        def __init__(self, *args, **kwargs):
            pass
        def observe(self, *args, **kwargs):
            pass
    class Gauge:
        def __init__(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def dec(self, *args, **kwargs):
            pass
    def generate_latest():
        return b""
    CONTENT_TYPE_LATEST = "text/plain"

# API Request Metrics
api_requests_total = Counter(
    'vivaai_api_requests_total',
    'Total number of API requests',
    ['method', 'endpoint', 'status']
)

api_request_duration_seconds = Histogram(
    'vivaai_api_request_duration_seconds',
    'API request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    'vivaai_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=half-open, 2=open)',
    ['breaker']
)

circuit_breaker_failures = Counter(
    'vivaai_circuit_breaker_failures_total',
    'Total circuit breaker failures',
    ['breaker']
)

circuit_breaker_successes = Counter(
    'vivaai_circuit_breaker_successes_total',
    'Total circuit breaker successes',
    ['breaker']
)

# Rate Limiter Metrics
rate_limiter_requests_total = Counter(
    'vivaai_rate_limiter_requests_total',
    'Total rate limiter requests',
    ['key', 'allowed']
)

rate_limiter_rejected_total = Counter(
    'vivaai_rate_limiter_rejected_total',
    'Total rate limiter rejections',
    ['key']
)

# Performance Metrics
question_generation_duration = Histogram(
    'vivaai_question_generation_duration_seconds',
    'Question generation duration',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0]
)

answer_grading_duration = Histogram(
    'vivaai_answer_grading_duration_seconds',
    'Answer grading duration',
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0]
)

audio_processing_duration = Histogram(
    'vivaai_audio_processing_duration_seconds',
    'Audio processing duration',
    buckets=[1.0, 2.0, 5.0, 10.0, 30.0]
)

# Session Metrics
active_sessions = Gauge(
    'vivaai_active_sessions',
    'Number of active exam sessions'
)

completed_sessions_total = Counter(
    'vivaai_completed_sessions_total',
    'Total completed exam sessions'
)

# Cache Metrics
cache_hits_total = Counter(
    'vivaai_cache_hits_total',
    'Total cache hits',
    ['cache_type']
)

cache_misses_total = Counter(
    'vivaai_cache_misses_total',
    'Total cache misses',
    ['cache_type']
)

cache_size = Gauge(
    'vivaai_cache_size',
    'Current cache size',
    ['cache_type']
)


def update_circuit_breaker_metrics(breaker_name: str, state: str, success: bool = None):
    """
    Update circuit breaker metrics.
    
    Args:
        breaker_name: Name of the circuit breaker
        state: State string ('closed', 'half-open', 'open')
        success: Whether operation succeeded (for counters)
    """
    if not PROMETHEUS_AVAILABLE:
        return
    
    # Map state string to number
    state_map = {'closed': 0, 'half-open': 1, 'open': 2}
    state_num = state_map.get(state.lower(), 0)
    circuit_breaker_state.labels(breaker=breaker_name).set(state_num)
    
    if success is not None:
        if success:
            circuit_breaker_successes.labels(breaker=breaker_name).inc()
        else:
            circuit_breaker_failures.labels(breaker=breaker_name).inc()


def record_api_request(method: str, endpoint: str, status_code: int, duration: float):
    """
    Record API request metrics.
    
    Args:
        method: HTTP method
        endpoint: API endpoint
        status_code: HTTP status code
        duration: Request duration in seconds
    """
    if not PROMETHEUS_AVAILABLE:
        return
    
    # Record request count
    api_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status=str(status_code)
    ).inc()
    
    # Record duration
    api_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint
    ).observe(duration)


def record_rate_limiter_event(key: str, allowed: bool):
    """
    Record rate limiter event.
    
    Args:
        key: Rate limiter key
        allowed: Whether request was allowed
    """
    if not PROMETHEUS_AVAILABLE:
        return
    
    rate_limiter_requests_total.labels(key=key, allowed=str(allowed)).inc()
    
    if not allowed:
        rate_limiter_rejected_total.labels(key=key).inc()


def record_cache_event(cache_type: str, hit: bool):
    """
    Record cache hit/miss.
    
    Args:
        cache_type: Type of cache (e.g., 'response', 'pdf')
        hit: Whether it was a cache hit
    """
    if not PROMETHEUS_AVAILABLE:
        return
    
    if hit:
        cache_hits_total.labels(cache_type=cache_type).inc()
    else:
        cache_misses_total.labels(cache_type=cache_type).inc()


def update_cache_size(cache_type: str, size: int):
    """
    Update cache size metric.
    
    Args:
        cache_type: Type of cache
        size: Current cache size
    """
    if not PROMETHEUS_AVAILABLE:
        return
    
    cache_size.labels(cache_type=cache_type).set(size)


def get_metrics():
    """
    Get Prometheus metrics in text format.
    
    Returns:
        Tuple of (metrics_text, content_type)
    """
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus client not available\n", CONTENT_TYPE_LATEST
    
    return generate_latest(), CONTENT_TYPE_LATEST

