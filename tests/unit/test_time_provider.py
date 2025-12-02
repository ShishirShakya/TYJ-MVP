"""
Unit tests for shared.time_provider module.

These tests verify time provider functionality and deterministic behavior.
"""

import pytest
from shared.time_provider import (
    RealTimeProvider,
    MockTimeProvider,
    get_default_time_provider,
    set_default_time_provider,
    create_time_provider
)


class TestRealTimeProvider:
    """Tests for RealTimeProvider class."""
    
    def test_real_time_provider_time(self):
        """Test that RealTimeProvider returns current time."""
        provider = RealTimeProvider()
        time1 = provider.time()
        time2 = provider.time()
        
        assert isinstance(time1, float)
        assert isinstance(time2, float)
        assert time2 >= time1  # Time should advance
    
    def test_real_time_provider_now(self):
        """Test that RealTimeProvider returns current datetime."""
        from datetime import datetime
        provider = RealTimeProvider()
        dt = provider.now()
        
        assert isinstance(dt, datetime)  # datetime instance
        assert dt is not None
    
    def test_real_time_provider_utcnow(self):
        """Test that RealTimeProvider returns UTC datetime."""
        provider = RealTimeProvider()
        dt = provider.utcnow()
        
        assert dt.tzinfo is not None  # Should have timezone info
        assert dt is not None


class TestMockTimeProvider:
    """Tests for MockTimeProvider class."""
    
    def test_mock_time_provider_initialization(self):
        """Test MockTimeProvider initialization."""
        provider = MockTimeProvider(initial_time=1000.0)
        assert provider.time() == 1000.0
    
    def test_mock_time_provider_set_time(self):
        """Test setting time on MockTimeProvider."""
        provider = MockTimeProvider(initial_time=1000.0)
        provider.set_time(2000.0)
        assert provider.time() == 2000.0
    
    def test_mock_time_provider_advance(self):
        """Test advancing time on MockTimeProvider."""
        provider = MockTimeProvider(initial_time=1000.0)
        provider.advance(100.0)
        assert provider.time() == 1100.0
    
    def test_mock_time_provider_reset(self):
        """Test resetting time on MockTimeProvider."""
        provider = MockTimeProvider(initial_time=1000.0)
        provider.advance(100.0)
        provider.reset()
        assert provider.time() == 1000.0
    
    def test_mock_time_provider_deterministic(self):
        """Test that MockTimeProvider is deterministic."""
        provider = MockTimeProvider(initial_time=1000.0)
        time1 = provider.time()
        time2 = provider.time()
        
        assert time1 == time2  # Should be same without advancing
    
    def test_mock_time_provider_now(self):
        """Test that MockTimeProvider returns datetime from timestamp."""
        from datetime import datetime, timezone
        provider = MockTimeProvider(initial_time=1000.0)
        dt = provider.now()
        
        assert dt is not None
        assert isinstance(dt, datetime)
        # Verify that the datetime corresponds to the timestamp
        # Use UTC for comparison to avoid timezone issues
        dt_utc = provider.utcnow()
        assert dt_utc.timestamp() == 1000.0
    
    def test_mock_time_provider_utcnow(self):
        """Test that MockTimeProvider returns UTC datetime."""
        provider = MockTimeProvider(initial_time=1000.0)
        dt = provider.utcnow()
        
        assert dt is not None
        assert dt.tzinfo is not None


class TestTimeProviderFunctions:
    """Tests for time provider utility functions."""
    
    def test_get_default_time_provider(self):
        """Test that get_default_time_provider returns RealTimeProvider."""
        provider = get_default_time_provider()
        assert isinstance(provider, RealTimeProvider)
    
    def test_set_default_time_provider(self):
        """Test setting default time provider."""
        original = get_default_time_provider()
        mock_provider = MockTimeProvider(initial_time=5000.0)
        
        set_default_time_provider(mock_provider)
        assert get_default_time_provider() is mock_provider
        
        # Restore original
        set_default_time_provider(original)
    
    def test_create_time_provider_real(self):
        """Test creating real time provider."""
        provider = create_time_provider(use_mock=False)
        assert isinstance(provider, RealTimeProvider)
    
    def test_create_time_provider_mock(self):
        """Test creating mock time provider."""
        provider = create_time_provider(use_mock=True, initial_time=3000.0)
        assert isinstance(provider, MockTimeProvider)
        assert provider.time() == 3000.0

