"""
Unit tests for shared.idempotency module.

These tests verify idempotency tracking and request ID generation.
"""

import pytest
from shared.idempotency import (
    IdempotencyTracker,
    get_default_idempotency_tracker,
    create_idempotency_tracker,
    generate_idempotency_key
)
from tests.helpers import build_minimal_state


class TestIdempotencyTracker:
    """Tests for IdempotencyTracker class."""
    
    def test_idempotency_tracker_initialization(self):
        """Test IdempotencyTracker initialization."""
        tracker = IdempotencyTracker()
        assert tracker is not None
    
    def test_generate_request_id(self):
        """Test request ID generation."""
        tracker = IdempotencyTracker()
        request_id = tracker.generate_request_id()
        
        assert isinstance(request_id, str)
        assert len(request_id) > 0
        # Should be UUID format
        assert len(request_id) == 36  # UUID string length
    
    def test_is_processed_false_initially(self):
        """Test that keys are not processed initially."""
        tracker = IdempotencyTracker()
        assert tracker.is_processed("test_key") is False
    
    def test_mark_processed(self):
        """Test marking a key as processed."""
        tracker = IdempotencyTracker()
        tracker.mark_processed("test_key")
        assert tracker.is_processed("test_key") is True
    
    def test_mark_processed_with_request_id(self):
        """Test marking processed with request ID."""
        tracker = IdempotencyTracker()
        request_id = tracker.generate_request_id()
        tracker.mark_processed("test_key", request_id)
        
        assert tracker.is_processed("test_key") is True
        info = tracker.get_request_info(request_id)
        assert info is not None
        assert info["idempotency_key"] == "test_key"
    
    def test_get_request_info(self):
        """Test getting request info."""
        tracker = IdempotencyTracker()
        request_id = tracker.generate_request_id()
        tracker.mark_processed("test_key", request_id)
        
        info = tracker.get_request_info(request_id)
        assert info is not None
        assert "idempotency_key" in info
        assert "processed_at" in info
    
    def test_get_request_info_not_found(self):
        """Test getting request info for non-existent ID."""
        tracker = IdempotencyTracker()
        info = tracker.get_request_info("nonexistent_id")
        assert info is None
    
    def test_reset(self):
        """Test resetting tracker."""
        tracker = IdempotencyTracker()
        tracker.mark_processed("test_key")
        tracker.reset()
        
        assert tracker.is_processed("test_key") is False


class TestGenerateIdempotencyKey:
    """Tests for generate_idempotency_key function."""
    
    def test_generate_idempotency_key_basic(self):
        """Test basic idempotency key generation."""
        state = build_minimal_state()
        key = generate_idempotency_key("test_operation", state)
        
        assert isinstance(key, str)
        assert "test_operation" in key
        assert state["session_id"] in key
    
    def test_generate_idempotency_key_same_inputs_same_key(self):
        """Test that same inputs generate same key."""
        state = build_minimal_state(session_id="test_session")
        key1 = generate_idempotency_key("test_operation", state)
        key2 = generate_idempotency_key("test_operation", state)
        
        assert key1 == key2
    
    def test_generate_idempotency_key_different_operations_different_keys(self):
        """Test that different operations generate different keys."""
        state = build_minimal_state(session_id="test_session")
        key1 = generate_idempotency_key("operation1", state)
        key2 = generate_idempotency_key("operation2", state)
        
        assert key1 != key2
    
    def test_generate_idempotency_key_with_args(self):
        """Test idempotency key generation with additional arguments."""
        state = build_minimal_state()
        key1 = generate_idempotency_key("test_operation", state, "arg1")
        key2 = generate_idempotency_key("test_operation", state, "arg2")
        
        assert key1 != key2  # Different args should produce different keys


class TestIdempotencyTrackerFunctions:
    """Tests for idempotency utility functions."""
    
    def test_get_default_idempotency_tracker(self):
        """Test that get_default_idempotency_tracker returns instance."""
        tracker = get_default_idempotency_tracker()
        assert isinstance(tracker, IdempotencyTracker)
    
    def test_get_default_idempotency_tracker_singleton(self):
        """Test that get_default_idempotency_tracker returns same instance."""
        tracker1 = get_default_idempotency_tracker()
        tracker2 = get_default_idempotency_tracker()
        assert tracker1 is tracker2
    
    def test_create_idempotency_tracker(self):
        """Test creating new idempotency tracker."""
        tracker = create_idempotency_tracker(max_entries=5000)
        assert isinstance(tracker, IdempotencyTracker)
        assert tracker is not get_default_idempotency_tracker()  # Should be different instance

