"""
Test helper functions and utilities.

This module provides helper functions for writing tests while preserving
the dependency injection wiring pattern.
"""

import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone


def build_minimal_state(**overrides) -> Dict[str, Any]:
    """
    Build a minimal valid state dictionary for testing.
    
    Args:
        **overrides: Key-value pairs to override defaults
        
    Returns:
        Dictionary with all required state fields
    """
    state = {
        "session_id": str(uuid.uuid4()),
        "student_id": "",
        "ip_address": "127.0.0.1",
        "history": [],
        "asked_main": 0,
        "scores": [],
        "rubrics": [],
        "limit": 1,
        "followups_min": 0,
        "followups_max": 1,
        "passphrase": "",
        "course_id": "TEST_COURSE",
        "exam_id": "TEST_EXAM",
        "section_id": "TEST_SECTION",
        "phase": "idle",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "session_start_time": 1000.0,
        "flags": [],
        "consent": False,
        "security_events": [],
        "tab_focus_events": [],
        "clipboard_events": [],
        "last_auto_save_time": 0,
        "network_status": "online",
        "last_network_check": 0,
        "queued_answers": [],
        "network_check_interval": 5,
        "ready_for_question": False,
        "current": {
            "main_question": None,
            "answers": [],
            "followups_done": 0,
            "target_followups": 0,
            "q_time": None,
            "short_attempts": 0,
            "ctx": None
        },
        "answers_tslog_all": [],
        "otet": None,
        "proctor_state": None,
        "proctor_summary": {},
        "proctor_blocks": [],
        "answer_hashes": [],
        "answer_texts": [],
        "used_context_hashes": set(),
        "questions_meta": [],
        "token_usage": [],
    }
    state.update(overrides)
    return state


def assert_state_valid(state: Dict[str, Any]) -> None:
    """
    Assert that a state dictionary has all required fields.
    
    Args:
        state: State dictionary to validate
        
    Raises:
        AssertionError: If required fields are missing
    """
    required_fields = [
        "session_id",
        "student_id",
        "history",
        "asked_main",
        "scores",
        "rubrics",
        "limit",
        "followups_min",
        "followups_max",
        "passphrase",
        "course_id",
        "exam_id",
        "section_id",
        "phase",
        "started_at",
        "session_start_time",
        "flags",
        "consent",
        "security_events",
        "current",
        "answers_tslog_all",
    ]
    
    for field in required_fields:
        assert field in state, f"Missing required field: {field}"


def assert_dependencies_structure(dependencies: Dict[str, Any], expected_keys: list) -> None:
    """
    Assert that a dependencies dictionary has the expected structure.
    
    Args:
        dependencies: Dependencies dictionary to validate
        expected_keys: List of expected keys
        
    Raises:
        AssertionError: If expected keys are missing
    """
    for key in expected_keys:
        assert key in dependencies, f"Missing dependency: {key}"


def create_mock_dependency(name: str, return_value: Any = None):
    """
    Create a mock dependency function.
    
    Args:
        name: Name of the dependency
        return_value: Value to return when called
        
    Returns:
        Mock function
    """
    from unittest.mock import Mock
    mock = Mock(name=name)
    if return_value is not None:
        mock.return_value = return_value
    return mock

