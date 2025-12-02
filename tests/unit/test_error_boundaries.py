"""
Unit tests for shared/error_boundaries.py.

Tests error boundary decorator and component isolation context manager.
"""

import pytest
from shared.error_boundaries import error_boundary, isolate_component
from shared.logging_config import get_logger


class TestErrorBoundary:
    """Tests for error_boundary decorator."""
    
    def test_error_boundary_with_fallback_value(self):
        """Test error boundary returns fallback value on exception."""
        @error_boundary("test_component", fallback_value="fallback_result")
        def failing_function():
            raise ValueError("Test error")
        
        result = failing_function()
        assert result == "fallback_result"
    
    def test_error_boundary_with_fallback_func(self):
        """Test error boundary calls fallback function on exception."""
        def fallback_func(*args, **kwargs):
            return "fallback_from_func"
        
        @error_boundary("test_component", fallback_func=fallback_func)
        def failing_function():
            raise ValueError("Test error")
        
        result = failing_function()
        assert result == "fallback_from_func"
    
    def test_error_boundary_no_fallback_raises(self):
        """Test error boundary re-raises exception when no fallback."""
        @error_boundary("test_component")
        def failing_function():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError, match="Test error"):
            failing_function()
    
    def test_error_boundary_success_no_error(self):
        """Test error boundary passes through successful result."""
        @error_boundary("test_component", fallback_value="fallback")
        def successful_function():
            return "success"
        
        result = successful_function()
        assert result == "success"
    
    def test_error_boundary_fallback_func_fails(self):
        """Test error boundary handles fallback function failure."""
        def failing_fallback(*args, **kwargs):
            raise RuntimeError("Fallback failed")
        
        @error_boundary("test_component", fallback_value="final_fallback", fallback_func=failing_fallback)
        def failing_function():
            raise ValueError("Test error")
        
        result = failing_function()
        assert result == "final_fallback"
    
    def test_error_boundary_log_error_false(self):
        """Test error boundary can disable error logging."""
        @error_boundary("test_component", fallback_value="fallback", log_error=False)
        def failing_function():
            raise ValueError("Test error")
        
        result = failing_function()
        assert result == "fallback"


class TestIsolateComponent:
    """Tests for isolate_component context manager."""
    
    def test_isolate_component_suppresses_exception_with_fallback(self):
        """Test component isolation suppresses exception with fallback."""
        with isolate_component("test_component", fallback_value="fallback") as isolator:
            raise ValueError("Test error")
        
        assert isolator.result == "fallback"
        assert isolator.error is not None
        assert isinstance(isolator.error, ValueError)
    
    def test_isolate_component_no_fallback_propagates_exception(self):
        """Test component isolation propagates exception without fallback."""
        with pytest.raises(ValueError, match="Test error"):
            with isolate_component("test_component") as isolator:
                raise ValueError("Test error")
    
    def test_isolate_component_success_no_error(self):
        """Test component isolation allows successful execution."""
        with isolate_component("test_component", fallback_value="fallback") as isolator:
            result = "success"
        
        assert isolator.error is None
        assert isolator.result is None
    
    def test_isolate_component_can_access_result(self):
        """Test component isolation allows accessing result after execution."""
        with isolate_component("test_component", fallback_value="fallback") as isolator:
            isolator.result = "custom_result"
        
        assert isolator.result == "custom_result"

