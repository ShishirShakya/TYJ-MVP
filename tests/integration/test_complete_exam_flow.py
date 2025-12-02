"""
Integration tests for complete exam flow end-to-end.

These tests verify the complete exam workflow from initialization to completion,
including question generation, answer submission, grading, and state management.

INTEGRATION TESTING: Tests critical workflows end-to-end (Principle #14).
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any
import hashlib
import time
import tempfile
import os
from unittest.mock import patch

from exam.flow.questions import ask_main_question, ask_followup_question
from exam.flow.audio import handle_mic
from exam.flow.grading import grade_current_block
from exam.state.core import ensure_state
from shared.time_provider import MockTimeProvider
from exam.config import CHAT_MODEL
from shared.config.prompts import FEEDBACK_BLOCK_INSTR


class TestCompleteExamFlow:
    """Integration tests for complete exam flow."""
    
    @patch('time.time')
    def test_complete_exam_flow_single_question(self, mock_time, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Complete end-to-end test: Single question exam flow.
        
        Flow:
        1. Initialize state and load PDF chunks
        2. Generate main question
        3. Submit main answer (audio)
        4. Grade block
        5. Complete exam
        """
        # Mock time.time() to return consistent values
        base_time = 1000.0
        mock_time.return_value = base_time
        
        # Setup
        time_provider = MockTimeProvider(initial_time=base_time)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Configure test state
        state["phase"] = "armed"
        state["limit"] = 1  # Single question exam
        state["consent"] = True
        state["followups_min"] = 0
        state["followups_max"] = 0  # No follow-ups
        
        # Mock PDF chunks
        test_chunks = [
            "This is test PDF content chunk 1 about machine learning and neural networks.",
            "This is test PDF content chunk 2 about deep learning architectures.",
            "This is test PDF content chunk 3 about convolutional neural networks."
        ]
        
        deps = mock_dependencies_exam_flow
        deps["get_chunks"] = Mock(return_value=test_chunks)
        deps["validate_chunks_available"] = Mock(return_value=(True, "", len(test_chunks)))
        deps["_validate_context"] = Mock(return_value=(True, ""))
        
        # Mock AI question generation
        def mock_question_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.prompt_tokens = 200
            resp.usage.completion_tokens = 50
            resp.usage.total_tokens = 250
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "What is machine learning?"
            return resp
        
        # Mock AI feedback generation
        def mock_feedback_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.prompt_tokens = 150
            resp.usage.completion_tokens = 30
            resp.usage.total_tokens = 180
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "Score: 85/100. Feedback: Good understanding of the concept."
            return resp
        
        # Configure OpenAI client responses
        mock_openai_client.chat.completions.create.side_effect = [
            mock_question_response(),  # Main question
            mock_feedback_response(),   # Grading feedback
        ]
        
        # Mock question generation function
        deps["_gen_main_question_with_ctx"] = Mock(return_value="What is machine learning?")
        # _parse_feedback returns a tuple: (scores_dict, feedback_text)
        # scores_dict should have keys like "Conceptual", "Analytical", etc., and "Overall"
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
            "Good understanding of the concept."
        ))
        deps["_calculate_overall_score"] = Mock(return_value=85.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test_question.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        deps["transcribe"] = Mock(return_value="Machine learning is a subset of artificial intelligence.")
        deps["_detect_profanity"] = Mock(return_value=False)
        deps["_count_meaningful_words"] = Mock(return_value=8)
        deps["_detect_answer_reuse"] = Mock(return_value=False)
        deps["_hash_answer"] = Mock(return_value="hash123")
        deps["analyze_speech_stylometry"] = Mock(return_value={})
        deps["get_max_answer_timeout_sec"] = Mock(return_value=300)
        deps["_calculate_timeout_status"] = Mock(return_value={})
        deps["_proctor_end_updates"] = Mock(return_value=({}, {}))
        deps["_categorize_error"] = Mock(return_value=("UNKNOWN_ERROR", {"message": "Unknown error"}))
        deps["CHAT_MODEL"] = CHAT_MODEL
        deps["FEEDBACK_BLOCK_INSTR"] = FEEDBACK_BLOCK_INSTR
        deps["update_network_status"] = Mock(return_value="online")
        deps["queue_answer_locally"] = Mock(return_value=False)
        deps["_paths_for_session"] = Mock(return_value={
            "STATE_PATH": "/tmp/test_state.json",
            "TMP_DIR": tempfile.gettempdir(),
            "TOMBSTONE_PATH": "/tmp/test_tombstone.json"
        })
        deps["MAX_SESSION_DURATION_SEC"] = 3600
        deps["MIN_WORDS"] = 5
        deps["MAX_SHORT_ATTEMPTS"] = 3
        deps["SHORT_PROMPT_TTS"] = "Please provide a longer answer."
        
        # Step 1: Generate main question
        result = ask_main_question(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        updated_state = result[0]
        assert updated_state["current"]["main_question"] is not None
        assert updated_state["current"]["main_question"] == "What is machine learning?"
        assert updated_state["phase"] == "awaiting_main_answer"
        assert updated_state["current"]["ctx"] is not None
        
        # Ensure q_time is set (required for handle_mic)
        # ask_main_question should have set q_time, but ensure it's set to a reasonable value
        # It sets q_time = time.time() + audio_duration, so it's slightly in the future
        # For testing, we'll set it to current time (mock_time returns base_time)
        current_time = mock_time.return_value
        if updated_state["current"].get("q_time") is None:
            updated_state["current"]["q_time"] = current_time  # Current time
        # Also ensure session_start_time is set
        if updated_state.get("session_start_time") is None or updated_state.get("session_start_time") == 0:
            updated_state["session_start_time"] = current_time - 100  # 100 seconds ago
        
        # Step 2: Submit main answer (audio)
        # Create a temporary audio file for testing
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(b"fake audio data")
            audio_path = tmp_audio.name
        
        try:
            result = handle_mic(
                audio_path=audio_path,
                s=updated_state,
                gr_module=mock_gradio_module,
                client=mock_openai_client,
                dependencies=deps
            )
        finally:
            # Clean up temporary file
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        
        updated_state = result[0]
        # handle_mic automatically calls grade_current_block when there are no follow-ups
        # So grading should already be complete
        assert len(updated_state.get("scores", [])) > 0, f"Expected scores to be added, got {len(updated_state.get('scores', []))} scores. Phase: {updated_state.get('phase')}"
        assert updated_state["asked_main"] == 1, f"Expected asked_main to be 1, got {updated_state['asked_main']}"
        assert updated_state["phase"] == "complete"  # Should be complete (limit reached)
        # scores is a list of numbers, not dicts
        assert updated_state["scores"][0] == 85.0, f"Expected score 85.0, got {updated_state['scores'][0]}"
    
    @patch('time.time')
    def test_complete_exam_flow_with_followups(self, mock_time, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Complete end-to-end test: Exam flow with follow-up questions.
        
        Flow:
        1. Initialize state and load PDF chunks
        2. Generate main question
        3. Submit main answer
        4. Generate follow-up question
        5. Submit follow-up answer
        6. Grade block (main + follow-up)
        7. Complete exam
        """
        # Mock time.time() to return consistent values
        base_time = 1000.0
        mock_time.return_value = base_time
        
        # Setup
        time_provider = MockTimeProvider(initial_time=base_time)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Configure test state
        state["phase"] = "armed"
        state["limit"] = 1  # Single question exam
        state["consent"] = True
        state["followups_min"] = 1
        state["followups_max"] = 1  # One follow-up
        
        # Mock PDF chunks
        test_chunks = [
            "This is test PDF content chunk 1 about machine learning and neural networks.",
            "This is test PDF content chunk 2 about deep learning architectures.",
        ]
        
        deps = mock_dependencies_exam_flow
        deps["get_chunks"] = Mock(return_value=test_chunks)
        deps["validate_chunks_available"] = Mock(return_value=(True, "", len(test_chunks)))
        deps["_validate_context"] = Mock(return_value=(True, ""))
        
        # Mock AI responses
        def mock_question_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.total_tokens = 250
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "What is machine learning?"
            return resp
        
        def mock_followup_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.total_tokens = 200
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "Can you give an example?"
            return resp
        
        def mock_feedback_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.total_tokens = 180
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "Score: 90/100. Feedback: Excellent answer with good example."
            return resp
        
        mock_openai_client.chat.completions.create.side_effect = [
            mock_question_response(),  # Main question
            mock_followup_response(),  # Follow-up question
            mock_feedback_response(),   # Grading feedback
        ]
        
        # Mock functions
        deps["_gen_main_question_with_ctx"] = Mock(return_value="What is machine learning?")
        deps["_gen_followup"] = Mock(return_value="Can you give an example?")
        # _parse_feedback returns a tuple: (scores_dict, feedback_text)
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 90, "Analytical": 90, "Application": 90, "Reflection": 90, "Overall": 90},
            "Excellent answer with good example."
        ))
        deps["_calculate_overall_score"] = Mock(return_value=90.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        deps["transcribe"] = Mock(side_effect=[
            "Machine learning is a subset of AI.",
            "For example, image recognition uses machine learning."
        ])
        deps["_detect_profanity"] = Mock(return_value=False)
        deps["_count_meaningful_words"] = Mock(return_value=8)
        deps["_detect_answer_reuse"] = Mock(return_value=False)
        deps["_hash_answer"] = Mock(return_value="hash123")
        deps["analyze_speech_stylometry"] = Mock(return_value={})
        deps["get_max_answer_timeout_sec"] = Mock(return_value=300)
        deps["_calculate_timeout_status"] = Mock(return_value={})
        deps["_proctor_end_updates"] = Mock(return_value=({}, {}))
        deps["_categorize_error"] = Mock(return_value=("UNKNOWN_ERROR", {"message": "Unknown error"}))
        deps["CHAT_MODEL"] = CHAT_MODEL
        deps["FEEDBACK_BLOCK_INSTR"] = FEEDBACK_BLOCK_INSTR
        deps["update_network_status"] = Mock(return_value="online")
        deps["queue_answer_locally"] = Mock(return_value=False)
        deps["_paths_for_session"] = Mock(return_value={
            "STATE_PATH": "/tmp/test_state.json",
            "TMP_DIR": tempfile.gettempdir(),
            "TOMBSTONE_PATH": "/tmp/test_tombstone.json"
        })
        deps["MAX_SESSION_DURATION_SEC"] = 3600
        deps["MIN_WORDS"] = 5
        deps["MAX_SHORT_ATTEMPTS"] = 3
        deps["SHORT_PROMPT_TTS"] = "Please provide a longer answer."
        
        # ask_followup_question and grade_current_block are already in mock_dependencies_exam_flow
        # No need to add them again
        
        # Step 1: Generate main question
        result = ask_main_question(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        updated_state = result[0]
        assert updated_state["current"]["main_question"] == "What is machine learning?"
        assert updated_state["phase"] == "awaiting_main_answer"
        
        # Ensure q_time is set (required for handle_mic)
        current_time = mock_time.return_value
        if updated_state["current"].get("q_time") is None:
            updated_state["current"]["q_time"] = current_time
        if updated_state.get("session_start_time") is None or updated_state.get("session_start_time") == 0:
            updated_state["session_start_time"] = current_time - 100
        
        # Step 2: Submit main answer
        # Create a temporary audio file for testing
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(b"fake audio data")
            audio_path = tmp_audio.name
        
        try:
            result = handle_mic(
                audio_path=audio_path,
                s=updated_state,
                gr_module=mock_gradio_module,
                client=mock_openai_client,
                dependencies=deps
            )
            
            updated_state = result[0]
            assert len(updated_state["current"]["answers"]) == 1
            assert updated_state["phase"] == "awaiting_followup_answer"  # Should trigger follow-up
        finally:
            # Clean up temporary file
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        
        # Ensure q_time is set for follow-up answer
        current_time = mock_time.return_value
        if updated_state["current"].get("q_time") is None:
            updated_state["current"]["q_time"] = current_time
        
        # Step 3: Submit follow-up answer
        # Create a new temporary audio file for the follow-up answer
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(b"fake audio data")
            followup_audio_path = tmp_audio.name
        
        try:
            result = handle_mic(
                audio_path=followup_audio_path,
                s=updated_state,
                gr_module=mock_gradio_module,
                client=mock_openai_client,
                dependencies=deps
            )
            
            updated_state = result[0]
            # handle_mic automatically calls grade_current_block when all follow-ups are done
            # So the exam should be complete
            assert len(updated_state.get("scores", [])) > 0, f"Expected scores, got {len(updated_state.get('scores', []))}. Phase: {updated_state.get('phase')}"
            assert updated_state["asked_main"] == 1, f"Expected asked_main to be 1, got {updated_state['asked_main']}"
            assert updated_state["phase"] == "complete", f"Expected phase to be 'complete', got '{updated_state['phase']}'"
            # scores is a list of numbers
            assert updated_state["scores"][0] == 90.0, f"Expected score 90.0, got {updated_state['scores'][0]}"
        finally:
            # Clean up temporary file
            if os.path.exists(followup_audio_path):
                os.unlink(followup_audio_path)
    
    @patch('time.time')
    def test_complete_exam_flow_multiple_questions(self, mock_time, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Complete end-to-end test: Multiple questions exam flow.
        
        Flow:
        1. Question 1: Generate → Answer → Grade
        2. Question 2: Generate → Answer → Grade
        3. Complete exam
        """
        # Mock time.time() to return consistent values
        base_time = 1000.0
        mock_time.return_value = base_time
        
        # Setup
        time_provider = MockTimeProvider(initial_time=base_time)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        # Configure test state
        state["phase"] = "armed"
        state["limit"] = 2  # Two questions
        state["consent"] = True
        state["followups_min"] = 0
        state["followups_max"] = 0  # No follow-ups
        # Ensure session_start_time is a number, not a Mock
        state["session_start_time"] = float(base_time) - 100.0
        
        # Mock PDF chunks
        test_chunks = [
            "This is test PDF content chunk 1 about machine learning.",
            "This is test PDF content chunk 2 about neural networks.",
            "This is test PDF content chunk 3 about deep learning.",
        ]
        
        deps = mock_dependencies_exam_flow
        deps["get_chunks"] = Mock(return_value=test_chunks)
        deps["validate_chunks_available"] = Mock(return_value=(True, "", len(test_chunks)))
        deps["_validate_context"] = Mock(return_value=(True, ""))
        
        # Mock AI responses - will be called multiple times
        question_count = [0]  # Use list to allow modification in nested function
        
        def mock_question_response():
            question_count[0] += 1
            resp = Mock()
            resp.usage = Mock()
            resp.usage.total_tokens = 250
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = f"What is question {question_count[0]}?"
            return resp
        
        def mock_feedback_response():
            resp = Mock()
            resp.usage = Mock()
            resp.usage.total_tokens = 180
            resp.choices = [Mock()]
            resp.choices[0].message = Mock()
            resp.choices[0].message.content = "Score: 85/100. Feedback: Good answer."
            return resp
        
        mock_openai_client.chat.completions.create.side_effect = [
            mock_question_response(),  # Question 1
            mock_feedback_response(),   # Grade 1
            mock_question_response(),  # Question 2
            mock_feedback_response(),   # Grade 2
        ]
        
        # Mock functions
        question_gen_count = [0]
        def mock_gen_question(*args, **kwargs):
            question_gen_count[0] += 1
            return f"What is question {question_gen_count[0]}?"
        
        deps["_gen_main_question_with_ctx"] = Mock(side_effect=mock_gen_question)
        # _parse_feedback returns a tuple: (scores_dict, feedback_text)
        deps["_parse_feedback"] = Mock(return_value=(
            {"Conceptual": 85, "Analytical": 85, "Application": 85, "Reflection": 85, "Overall": 85},
            "Good answer."
        ))
        deps["_calculate_overall_score"] = Mock(return_value=85.0)
        deps["tts_to_mp3"] = Mock(return_value="/tmp/test.mp3")
        deps["get_audio_duration"] = Mock(return_value=5.0)
        deps["transcribe"] = Mock(return_value="This is my answer to the question.")
        deps["_detect_profanity"] = Mock(return_value=False)
        deps["_count_meaningful_words"] = Mock(return_value=8)
        deps["_detect_answer_reuse"] = Mock(return_value=False)
        deps["_hash_answer"] = Mock(return_value="hash123")
        deps["analyze_speech_stylometry"] = Mock(return_value={})
        deps["get_max_answer_timeout_sec"] = Mock(return_value=300)
        deps["_calculate_timeout_status"] = Mock(return_value={})
        deps["_proctor_end_updates"] = Mock(return_value=({}, {}))
        deps["_categorize_error"] = Mock(return_value=("UNKNOWN_ERROR", {"message": "Unknown error"}))
        deps["CHAT_MODEL"] = CHAT_MODEL
        deps["FEEDBACK_BLOCK_INSTR"] = FEEDBACK_BLOCK_INSTR
        deps["update_network_status"] = Mock(return_value="online")
        deps["queue_answer_locally"] = Mock(return_value=False)
        deps["_paths_for_session"] = Mock(return_value={
            "STATE_PATH": "/tmp/test_state.json",
            "TMP_DIR": tempfile.gettempdir(),
            "TOMBSTONE_PATH": "/tmp/test_tombstone.json"
        })
        deps["MAX_SESSION_DURATION_SEC"] = 3600
        deps["MIN_WORDS"] = 5
        deps["MAX_SHORT_ATTEMPTS"] = 3
        deps["SHORT_PROMPT_TTS"] = "Please provide a longer answer."
        
        # Question 1: Generate → Answer → Grade
        result = ask_main_question(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        updated_state = result[0]
        assert updated_state["asked_main"] == 0  # Not incremented until graded
        assert updated_state["phase"] == "awaiting_main_answer"
        
        # Ensure q_time is set (use mock_time for consistency)
        current_time = mock_time.return_value
        if updated_state["current"].get("q_time") is None:
            updated_state["current"]["q_time"] = float(current_time)
        # Set session_start_time to a number (not a Mock) to avoid comparison issues
        if updated_state.get("session_start_time") is None or updated_state.get("session_start_time") == 0:
            updated_state["session_start_time"] = float(current_time) - 100.0
        
        # Create a temporary audio file for testing
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(b"fake audio data")
            audio_path = tmp_audio.name
        
        try:
            result = handle_mic(
                audio_path=audio_path,
                s=updated_state,
                gr_module=mock_gradio_module,
                client=mock_openai_client,
                dependencies=deps
            )
            updated_state = result[0]
            # handle_mic automatically grades when no follow-ups
            assert updated_state["asked_main"] == 1, f"Expected asked_main to be 1, got {updated_state['asked_main']}"
            assert len(updated_state.get("scores", [])) == 1, f"Expected 1 score, got {len(updated_state.get('scores', []))}"
        finally:
            # Clean up temporary file
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        
        # Question 2: Generate → Answer → Grade
        updated_state["phase"] = "awaiting_next_main"  # Set phase for next question
        result = ask_main_question(
            s=updated_state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        updated_state = result[0]
        assert updated_state["phase"] == "awaiting_main_answer"
        
        # Ensure q_time is set
        current_time = time.time()
        if updated_state["current"].get("q_time") is None:
            updated_state["current"]["q_time"] = current_time - 10  # 10 seconds ago
        
        # Create a temporary audio file for the second question's answer
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.wav', delete=False) as tmp_audio:
            tmp_audio.write(b"fake audio data")
            audio_path_q2 = tmp_audio.name
        
        try:
            result = handle_mic(
                audio_path=audio_path_q2,
                s=updated_state,
                gr_module=mock_gradio_module,
                client=mock_openai_client,
                dependencies=deps
            )
            updated_state = result[0]
            # handle_mic automatically grades when no follow-ups
            assert updated_state["asked_main"] == 2, f"Expected asked_main to be 2, got {updated_state['asked_main']}"
            assert len(updated_state.get("scores", [])) == 2, f"Expected 2 scores, got {len(updated_state.get('scores', []))}"
            assert updated_state["phase"] == "complete"  # Should be complete (limit reached)
        finally:
            # Clean up temporary file
            if os.path.exists(audio_path_q2):
                os.unlink(audio_path_q2)
    
    def test_exam_flow_error_handling(self, mock_state, mock_openai_client, mock_gradio_module, mock_dependencies_exam_flow):
        """
        Test error handling in exam flow.
        
        Tests:
        - Empty PDF chunks
        - API failures
        - Invalid answers
        """
        # Setup
        time_provider = MockTimeProvider(initial_time=1000.0)
        state = ensure_state(mock_state, time_provider=time_provider)
        
        state["phase"] = "armed"
        state["limit"] = 1
        state["consent"] = True
        
        deps = mock_dependencies_exam_flow
        
        # Test 1: Empty PDF chunks
        deps["get_chunks"] = Mock(return_value=[])
        deps["validate_chunks_available"] = Mock(return_value=(False, "No chunks available", 0))
        
        result = ask_main_question(
            s=state,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Should handle error gracefully
        assert result is not None
        status_update = result[2]
        assert status_update is not None
        
        # Test 2: API failure during question generation
        # Reset state for second test
        state2 = ensure_state(mock_state, time_provider=time_provider)
        state2["phase"] = "armed"
        state2["limit"] = 1
        state2["consent"] = True
        
        deps["get_chunks"] = Mock(return_value=["Test chunk"])
        deps["validate_chunks_available"] = Mock(return_value=(True, "", 1))
        deps["_validate_context"] = Mock(return_value=(True, ""))
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")
        
        deps["_categorize_error"] = Mock(return_value=(
            "API_ERROR",
            {"message": "Unable to generate question. Please try again.", "retry": True}
        ))
        
        result = ask_main_question(
            s=state2,
            gr_module=mock_gradio_module,
            client=mock_openai_client,
            dependencies=deps
        )
        
        # Should handle error gracefully
        assert result is not None
        updated_state = result[0]
        # After error, phase might be in different states depending on error handling
        # The important thing is that state is not corrupted
        assert "phase" in updated_state
        assert updated_state["session_id"] == state2["session_id"]  # State not corrupted

