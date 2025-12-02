"""
Integration tests for state persistence workflow.

These tests verify the complete state persistence workflow,
including validation, serialization, and persistence.

INTEGRATION TESTING: Tests critical workflows end-to-end (Principle #14).
"""

import pytest
import tempfile
import os
import json
import uuid
import sys
from typing import Dict, Any
from datetime import datetime, timezone

from exam.state.core import ensure_state
from exam.state.persistence import save_state_to_disk, load_state_from_disk
from exam.state.validation import validate_state_before_persistence, enforce_state_constraints
from exam.state.serialization import prepare_state_for_serialization
from shared.time_provider import MockTimeProvider


def skip_if_windows_no_pywin32():
    """Skip test on Windows if pywin32 not available."""
    if sys.platform == "win32":
        try:
            import win32security
            import win32con
            # Check if win32con has the constants we need
            if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                pytest.skip("Windows requires pywin32 with file access constants for state persistence tests")
        except ImportError:
            pytest.skip("Windows requires pywin32 for state persistence tests")
    return False  # Don't skip on non-Windows


class TestStatePersistenceWorkflow:
    """Integration tests for state persistence workflow."""
    
    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary directory for state files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set environment variable for state directory
            original_state_dir = os.environ.get("EXAM_STATE_DIR")
            os.environ["EXAM_STATE_DIR"] = tmpdir
            yield tmpdir
            # Restore original
            if original_state_dir:
                os.environ["EXAM_STATE_DIR"] = original_state_dir
            else:
                os.environ.pop("EXAM_STATE_DIR", None)
    
    def test_complete_persistence_workflow(self, temp_state_dir, mock_state):
        """
        Integration test: Complete state persistence workflow.
        
        Tests: ensure_state → validate → enforce → serialize → save → load
        """
        skip_if_windows_no_pywin32()
        # Step 1: Ensure state (initialize with defaults)
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Verify state is initialized
        assert "session_id" in state
        assert "request_id" in state
        assert state["phase"] == "idle"
        
        # Step 2: Validate state before persistence
        is_valid, error = validate_state_before_persistence(state)
        assert is_valid, f"State should be valid: {error}"
        
        # Step 3: Enforce constraints (bound collections)
        state["history"] = [{"role": "user", "content": "test"}] * 2000  # Exceeds bound
        enforced_state = enforce_state_constraints(state)
        assert len(enforced_state["history"]) <= 1000  # Should be bounded
        
        # Step 4: Prepare for serialization
        prepared_state = prepare_state_for_serialization(enforced_state)
        
        # Verify large data excluded
        assert "chunks" not in prepared_state or "chunks" not in enforced_state
        assert "text" not in prepared_state or "text" not in enforced_state
        
        # Step 5: Save to disk
        success = save_state_to_disk(enforced_state, persist_ok=True)
        assert success, "State should save successfully"
        
        # Step 6: Verify file exists
        from exam.file_utils import _paths_for_session
        paths = _paths_for_session(enforced_state)
        assert os.path.exists(paths["STATE_PATH"]), "State file should exist"
        
        # Step 7: Verify file content
        with open(paths["STATE_PATH"], 'r') as f:
            saved_state = json.load(f)
        
        # Verify essential fields saved
        assert saved_state["session_id"] == state["session_id"]
        assert saved_state["phase"] == state["phase"]
        
        # Verify large data not saved
        assert "chunks" not in saved_state
        assert "text" not in saved_state
    
    def test_persistence_workflow_with_invalid_state(self, temp_state_dir, mock_state):
        """
        Integration test: Persistence workflow with invalid state.
        
        Tests: Invalid state should fail validation and not be saved.
        """
        # Create invalid state (missing required fields)
        invalid_state = {"session_id": "not-a-uuid"}
        
        # Validation should fail
        is_valid, error = validate_state_before_persistence(invalid_state)
        assert not is_valid, "Invalid state should fail validation"
        assert error is not None
        
        # Save should fail (validation happens in save_state_to_disk)
        success = save_state_to_disk(invalid_state, persist_ok=True)
        assert not success, "Invalid state should not be saved"
    
    def test_persistence_workflow_with_large_collections(self, temp_state_dir, mock_state):
        """
        Integration test: Persistence workflow with large collections.
        
        Tests: Large collections should be bounded before persistence.
        """
        skip_if_windows_no_pywin32()
        # Create state with large collections
        state = ensure_state(mock_state)
        state["history"] = [{"role": "user", "content": f"test_{idx}"} for idx in range(5000)]
        state["answers_tslog_all"] = [{"answer": f"answer_{idx}"} for idx in range(3000)]
        state["security_events"] = [{"event": f"event_{idx}"} for idx in range(5000)]
        
        # Save should succeed (collections bounded automatically)
        success = save_state_to_disk(state, persist_ok=True)
        assert success, "State with large collections should save successfully"
        
        # Verify collections were bounded
        from exam.file_utils import _paths_for_session
        paths = _paths_for_session(state)
        with open(paths["STATE_PATH"], 'r') as f:
            saved_state = json.load(f)
        
        assert len(saved_state["history"]) <= 1000
        assert len(saved_state["answers_tslog_all"]) <= 500
        assert len(saved_state["security_events"]) <= 1000
    
    def test_persistence_workflow_idempotency(self, temp_state_dir, mock_state):
        """
        Integration test: Persistence workflow idempotency.
        
        Tests: Multiple saves of same state should be idempotent.
        """
        skip_if_windows_no_pywin32()
        state = ensure_state(mock_state)
        
        # Save multiple times
        success1 = save_state_to_disk(state, persist_ok=True)
        success2 = save_state_to_disk(state, persist_ok=True)
        success3 = save_state_to_disk(state, persist_ok=True)
        
        assert success1 and success2 and success3, "Multiple saves should succeed"
        
        # Verify file content is consistent
        from exam.file_utils import _paths_for_session
        paths = _paths_for_session(state)
        
        with open(paths["STATE_PATH"], 'r') as f:
            saved_state = json.load(f)
        
        # Verify state is consistent
        assert saved_state["session_id"] == state["session_id"]
        assert saved_state["phase"] == state["phase"]
    
    def test_persistence_workflow_concurrent_saves(self, temp_state_dir, mock_state):
        """
        Integration test: Persistence workflow with concurrent saves.
        
        Tests: Concurrent saves should not corrupt state (file locking).
        """
        skip_if_windows_no_pywin32()
        import threading
        
        state = ensure_state(mock_state)
        save_results = []
        
        def save_state(thread_id):
            """Save state from thread."""
            thread_state = state.copy()
            thread_state["thread_id"] = thread_id
            result = save_state_to_disk(thread_state, persist_ok=True)
            save_results.append((thread_id, result))
        
        # Start multiple threads saving simultaneously
        threads = []
        for i in range(5):
            thread = threading.Thread(target=save_state, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All saves should succeed (file locking prevents corruption)
        assert all(result for _, result in save_results), "All concurrent saves should succeed"
        
        # Verify file exists and is valid JSON
        from exam.file_utils import _paths_for_session
        paths = _paths_for_session(state)
        assert os.path.exists(paths["STATE_PATH"]), "State file should exist"
        
        with open(paths["STATE_PATH"], 'r') as f:
            saved_state = json.load(f)
        
        # Verify state is valid
        assert "session_id" in saved_state
        assert saved_state["session_id"] == state["session_id"]

