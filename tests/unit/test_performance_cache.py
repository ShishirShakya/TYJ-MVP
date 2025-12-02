"""
Unit tests for performance caching module.

Phase 3.6: Test coverage for performance optimizations.
"""

import pytest
import time
from shared.performance_cache import (
    get_cached_response,
    set_cached_response,
    cache_response,
    get_cache_stats,
    reset_metrics
)


class TestPerformanceCache:
    """Test performance caching functionality."""
    
    def test_get_cached_response_miss(self):
        """Test cache miss returns None."""
        result = get_cached_response("test_operation", "arg1", key="value")
        assert result is None
    
    def test_set_and_get_cached_response(self):
        """Test setting and getting cached response."""
        operation = "test_operation"
        args = ("arg1",)
        kwargs = {"key": "value"}
        response = {"result": "test"}
        
        # Set cache
        set_cached_response(operation, response, ttl=3600, *args, **kwargs)
        
        # Get cache
        cached = get_cached_response(operation, *args, **kwargs)
        assert cached == response
    
    def test_cache_expiration(self):
        """Test cache entry expiration."""
        operation = "test_operation"
        response = {"result": "test"}
        
        # Set cache with short TTL
        set_cached_response(operation, response, "arg1", ttl=0.1)
        
        # Should be cached immediately
        cached = get_cached_response(operation, "arg1")
        assert cached == response
        
        # Wait for expiration
        time.sleep(0.2)
        
        # Should be expired
        cached = get_cached_response(operation, "arg1")
        assert cached is None
    
    def test_cache_response_decorator(self):
        """Test cache_response decorator."""
        call_count = [0]
        
        @cache_response("test_operation", ttl=3600)
        def test_function(x):
            call_count[0] += 1
            return x * 2
        
        # First call - should execute function
        result1 = test_function(5)
        assert result1 == 10
        assert call_count[0] == 1
        
        # Second call - should use cache
        result2 = test_function(5)
        assert result2 == 10
        assert call_count[0] == 1  # Function not called again
    
    def test_get_cache_stats(self):
        """Test cache statistics retrieval."""
        # Add some cache entries
        set_cached_response("op1", "result1", "arg1", ttl=3600)
        set_cached_response("op2", "result2", "arg2", ttl=3600)
        
        stats = get_cache_stats()
        assert "total_entries" in stats
        assert "valid_entries" in stats
        assert stats["total_entries"] >= 2

