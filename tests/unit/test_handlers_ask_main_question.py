"""
Unit tests for ask_main_question function signature in handlers.

Tests that the function signature matches what handlers.py expects.
"""

import pytest
from unittest.mock import Mock, MagicMock
from exam.flow.questions import ask_main_question
from exam.ui.handlers import handle_start_exam


class TestAskMainQuestionSignature:
    """Tests for ask_main_question function signature compatibility."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "request_id": "test_request",
            "phase": "armed",
            "asked_main": 0,
            "limit": 5,
            "history": [],
            "current": {},
            "consent": True,
            "exam_started": True,
        }
    
    @pytest.fixture
    def mock_gr_module(self):
        """Create mock Gradio module."""
        gr = Mock()
        def mock_update(**kwargs):
            return kwargs
        gr.update = mock_update
        return gr
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create mock OpenAI client."""
        return Mock()
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies with ask_main_question flow function."""
        deps = {}
        deps["ensure_state"] = lambda s: s
        deps["reset_current_block"] = lambda s: None
        deps["get_followup_range"] = lambda s: (0, 2)
        deps["get_chunks"] = lambda: ["Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms including object-oriented and functional programming."]
        deps["validate_chunks_available"] = lambda: (True, "", 5)
        deps["_validate_context"] = lambda ctx: (True, "")
        deps["_gen_main_question_with_ctx"] = lambda s, ctx, **kwargs: "What is Python?"
        deps["tts_to_mp3"] = lambda text, client, state, **kwargs: "/tmp/test.mp3"
        deps["get_audio_duration"] = lambda audio: 5.0
        deps["get_max_answer_timeout_sec"] = lambda: 300
        deps["_calculate_timeout_status"] = lambda s, gr, timeout: {}
        deps["_proctor_end_updates"] = lambda s, gr: ({}, {})
        deps["_categorize_error"] = lambda e: ("UNKNOWN_ERROR", {"message": str(e)})
        deps["ask_main_question"] = ask_main_question  # Use the actual flow function
        deps["client"] = Mock()
        return deps
    
    def test_ask_main_question_signature_matches_handlers_call(self, mock_state, mock_gr_module, mock_dependencies):
        """Test that ask_main_question can be called with handlers.py signature."""
        # This is how handlers.py calls it (line 519):
        # ask_main_question_func(current_state, gr_module, client, dependencies)
        client = mock_dependencies["client"]
        dependencies = mock_dependencies
        
        # Should not raise TypeError about argument count
        try:
            result = ask_main_question(
                mock_state,
                mock_gr_module,
                client,
                dependencies
            )
            # If we get here, the signature is correct
            assert result is not None
            assert isinstance(result, tuple)
            assert len(result) == 8  # Expected tuple length
        except TypeError as e:
            if "takes" in str(e) and "positional arguments" in str(e):
                pytest.fail(f"Function signature mismatch: {e}")
            raise
    
    def test_ask_main_question_with_progress(self, mock_state, mock_gr_module, mock_openai_client, mock_dependencies):
        """Test that ask_main_question accepts optional progress parameter."""
        progress_calls = []
        
        def mock_progress(value):
            progress_calls.append(value)
        
        # Should work with progress parameter
        result = ask_main_question(
            mock_state,
            mock_gr_module,
            mock_openai_client,
            mock_dependencies,
            progress=mock_progress
        )
        
        assert result is not None
        assert isinstance(result, tuple)
    
    def test_handle_start_exam_calls_ask_main_question_correctly(self, mock_state, mock_gr_module, mock_dependencies):
        """Test that handle_start_exam calls ask_main_question with correct signature."""
        # Mock the ask_main_question function to verify it's called correctly
        call_args = []
        
        def mock_ask_main_question(s, gr_module, client, dependencies, progress=None):
            call_args.append((s, gr_module, client, dependencies, progress))
            # Return a valid tuple
            return (
                s,  # state
                None,  # audio
                gr_module.update(value="Test"),  # status_msg
                gr_module.update(),  # mic_upd
                [],  # chatbot_update
                gr_module.update(),  # cam_upd
                gr_module.update(),  # cam_status_upd
                gr_module.update(),  # timeout_upd
            )
        
        mock_dependencies["ask_main_question"] = mock_ask_main_question
        
        # Call handle_start_exam
        result = handle_start_exam(
            mock_state,
            mock_gr_module,
            mock_dependencies
        )
        
        # Verify ask_main_question was called with correct arguments
        assert len(call_args) == 1
        s, gr, client, deps, progress = call_args[0]
        assert s == mock_state
        assert gr == mock_gr_module
        assert client == mock_dependencies["client"]
        assert deps == mock_dependencies
        assert progress is None  # Not passed in handlers.py

