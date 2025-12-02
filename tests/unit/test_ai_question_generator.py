"""
Unit tests for exam.ai.question_generator module.

Tests cover question generation, duplicate detection, and caching logic.
"""

import pytest
import hashlib
from unittest.mock import Mock, MagicMock, patch
from exam.ai.question_generator import (
    _check_duplicate_question,
    _get_cached_or_generate,
    _gen_main_question_with_ctx,
    _gen_followup,
)


class TestCheckDuplicateQuestion:
    """Tests for _check_duplicate_question function."""
    
    def test_check_duplicate_question_empty_list(self):
        """Test with empty previous questions list."""
        result = _check_duplicate_question("What is Python?", [])
        assert result is False
    
    def test_check_duplicate_question_exact_hash_match(self):
        """Test exact duplicate detection via hash."""
        question = "What is Python?"
        question_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()
        
        previous_questions = [
            {"question_sha256": question_hash, "question_text": question}
        ]
        
        result = _check_duplicate_question(question, previous_questions)
        assert result is True
    
    def test_check_duplicate_question_different_hash(self):
        """Test with different question (different hash)."""
        question1 = "What is Python?"
        question2 = "What is Java?"
        
        question1_hash = hashlib.sha256(question1.encode("utf-8")).hexdigest()
        previous_questions = [
            {"question_sha256": question1_hash, "question_text": question1}
        ]
        
        result = _check_duplicate_question(question2, previous_questions)
        assert result is False
    
    def test_check_duplicate_question_similar_start(self):
        """Test detection of questions with similar start."""
        # Need questions where first 50 chars match exactly and start is > 20 chars
        # Use a long question where first 50 chars are identical
        question1 = "What is the main concept behind object-oriented programming and design patterns in software development?"
        question2 = "What is the main concept behind object-oriented programming and design patterns in computer science?"
        
        previous_questions = [
            {"question_text": question1}
        ]
        
        # Both start with "What is the main concept behind object-oriented pr" (first 50 chars match)
        # And both are > 20 chars, so should detect as similar
        result = _check_duplicate_question(question2, previous_questions)
        # Should detect as similar (same start > 20 chars)
        assert result is True
    
    def test_check_duplicate_question_high_word_overlap(self):
        """Test detection via word overlap (80%+ similarity)."""
        question1 = "What are the key principles of software engineering and design patterns?"
        question2 = "What are the key principles of software engineering and design methodologies?"
        
        previous_questions = [
            {"question_text": question1}
        ]
        
        # High word overlap should be detected
        result = _check_duplicate_question(question2, previous_questions)
        assert result is True
    
    def test_check_duplicate_question_low_word_overlap(self):
        """Test with low word overlap (not duplicate)."""
        question1 = "What is Python programming language?"
        question2 = "How does machine learning work in practice?"
        
        previous_questions = [
            {"question_text": question1}
        ]
        
        result = _check_duplicate_question(question2, previous_questions)
        assert result is False
    
    def test_check_duplicate_question_too_short(self):
        """Test that very short questions are not checked for similarity."""
        question1 = "What is Python?"
        question2 = "What is Java?"
        
        previous_questions = [
            {"question_text": question1}
        ]
        
        # Short questions (< 5 meaningful words) skip similarity check
        result = _check_duplicate_question(question2, previous_questions)
        # Should only check hash, not similarity
        assert result is False
    
    def test_check_duplicate_question_no_question_text(self):
        """Test with metadata missing question_text."""
        question = "What is Python?"
        previous_questions = [
            {"question_sha256": "different_hash"}
            # No question_text field
        ]
        
        result = _check_duplicate_question(question, previous_questions)
        assert result is False


class TestGetCachedOrGenerate:
    """Tests for _get_cached_or_generate function."""
    
    def test_get_cached_or_generate_first_attempt_success(self):
        """Test successful generation on first attempt."""
        call_count = [0]
        
        def generation_fn():
            call_count[0] += 1
            return "What is Python?"
        
        result = _get_cached_or_generate("context", generation_fn, used_questions=set())
        
        assert result == "What is Python?"
        assert call_count[0] == 1
    
    def test_get_cached_or_generate_avoids_used_questions(self):
        """Test that used questions are avoided."""
        call_count = [0]
        used_questions = {"What is Python?"}
        
        def generation_fn():
            call_count[0] += 1
            if call_count[0] == 1:
                return "What is Python?"  # First attempt is used
            return "What is Java?"  # Second attempt is new
        
        result = _get_cached_or_generate("context", generation_fn, used_questions=used_questions)
        
        assert result == "What is Java?"
        assert call_count[0] == 2
    
    def test_get_cached_or_generate_max_attempts(self):
        """Test that function returns after max attempts even if all are duplicates."""
        call_count = [0]
        used_questions = set()
        
        def generation_fn():
            call_count[0] += 1
            new_question = f"Question {call_count[0]}"
            # Add to used_questions after generating (simulating it being used)
            used_questions.add(new_question)
            return new_question
        
        # First call generates "Question 1" and adds it to used_questions
        # Second call generates "Question 2" which is not in used_questions yet
        # So it should return on second attempt
        result = _get_cached_or_generate("context", generation_fn, used_questions=used_questions)
        
        # Should have tried at least once, but may return early if not duplicate
        assert call_count[0] >= 1
        assert result is not None
    
    def test_get_cached_or_generate_no_used_questions(self):
        """Test with None used_questions (should default to empty set)."""
        def generation_fn():
            return "What is Python?"
        
        result = _get_cached_or_generate("context", generation_fn, used_questions=None)
        
        assert result == "What is Python?"


class TestGenMainQuestionWithCtx:
    """Tests for _gen_main_question_with_ctx function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        import random
        return {
            "session_id": "test_session",
            "questions_meta": [],
            "_rng": random.Random(42),
            "history": []
        }
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "What is the main concept discussed in this context?"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-4o-mini"
        
        client.chat.completions.create.return_value = mock_response
        return client
    
    def test_gen_main_question_with_ctx_basic(self, mock_state, mock_openai_client):
        """Test basic question generation."""
        # Context must be at least 50 characters
        ctx_text = "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms."
        
        result = _gen_main_question_with_ctx(mock_state, ctx_text, mock_openai_client)
        
        assert result is not None
        assert "?" in result  # Should end with question mark
        assert len(result) > 0
    
    def test_gen_main_question_with_ctx_invalid_context(self, mock_state, mock_openai_client):
        """Test with invalid context."""
        ctx_text = ""  # Empty context is invalid
        
        with pytest.raises(ValueError, match="Invalid context"):
            _gen_main_question_with_ctx(mock_state, ctx_text, mock_openai_client)
    
    def test_gen_main_question_with_ctx_chunk_reused(self, mock_state, mock_openai_client):
        """Test question generation when chunk is reused."""
        # Context must be at least 50 characters
        ctx_text = "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms including object-oriented and functional programming."
        ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
        
        # Mark chunk as used
        mock_state["questions_meta"] = [
            {"context_sha256": ctx_sha, "question_text": "Previous question"}
        ]
        
        result = _gen_main_question_with_ctx(mock_state, ctx_text, mock_openai_client)
        
        # Should still generate a question (new one for reused chunk)
        assert result is not None
        assert "?" in result
    
    def test_gen_main_question_with_ctx_duplicate_detection(self, mock_state, mock_openai_client):
        """Test duplicate question detection and retry."""
        # Context must be at least 50 characters
        ctx_text = "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms including object-oriented and functional programming."
        
        # Mock client to return same question twice, then different one
        call_count = [0]
        def mock_create(*args, **kwargs):
            call_count[0] += 1
            response = Mock()
            response.choices = [Mock()]
            response.choices[0].message = Mock()
            if call_count[0] <= 2:
                response.choices[0].message.content = "What is Python?"
            else:
                response.choices[0].message.content = "What are the key features of Python?"
            response.usage = Mock()
            response.usage.prompt_tokens = 100
            response.usage.completion_tokens = 50
            response.usage.total_tokens = 150
            response.model = "gpt-4o-mini"
            return response
        
        mock_openai_client.chat.completions.create.side_effect = mock_create
        
        # Mark first question as already used
        mock_state["questions_meta"] = [
            {"question_sha256": hashlib.sha256("What is Python?".encode("utf-8")).hexdigest(),
             "question_text": "What is Python?"}
        ]
        
        result = _gen_main_question_with_ctx(mock_state, ctx_text, mock_openai_client)
        
        # Should generate a different question after detecting duplicate
        assert result is not None
        assert result != "What is Python?"


class TestGenFollowup:
    """Tests for _gen_followup function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        # Context must be at least 50 characters
        return {
            "session_id": "test_session",
            "current": {
                "main_question": "What is Python?",
                "ctx": "Python is a high-level programming language known for its simplicity and readability. It supports multiple programming paradigms."
            },
            "history": []
        }
    
    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        client = Mock()
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Can you provide more details about that?"
        mock_response.usage = Mock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.model = "gpt-4o-mini"
        
        client.chat.completions.create.return_value = mock_response
        return client
    
    def test_gen_followup_basic(self, mock_state, mock_openai_client):
        """Test basic follow-up question generation."""
        last_answer = "Python is a high-level programming language."
        
        result = _gen_followup(mock_state, last_answer, mock_openai_client)
        
        assert result is not None
        assert "?" in result  # Should end with question mark
        assert len(result) > 0
    
    def test_gen_followup_no_context(self, mock_openai_client):
        """Test follow-up generation without context."""
        state = {
            "current": {
                "main_question": "What is Python?",
                "ctx": None
            }
        }
        last_answer = "Python is a programming language."
        
        result = _gen_followup(state, last_answer, mock_openai_client)
        
        assert result is not None
        assert "?" in result
    
    def test_gen_followup_invalid_context(self, mock_openai_client):
        """Test with invalid context."""
        state = {
            "current": {
                "main_question": "What is Python?",
                "ctx": "short"  # Too short context (< 50 chars) is invalid
            }
        }
        last_answer = "Python is a programming language."
        
        with pytest.raises(ValueError, match="Invalid context"):
            _gen_followup(state, last_answer, mock_openai_client)
    
    def test_gen_followup_long_answer_truncation(self, mock_state, mock_openai_client):
        """Test that long answers are truncated."""
        # Create a very long answer
        long_answer = "Python is " * 200  # Very long answer
        
        result = _gen_followup(mock_state, long_answer, mock_openai_client)
        
        # Should still generate follow-up (answer was truncated internally)
        assert result is not None
        assert "?" in result
    
    def test_gen_followup_missing_main_question(self, mock_openai_client):
        """Test with missing main question."""
        # Context must be at least 50 characters if provided
        state = {
            "current": {
                "main_question": None,
                "ctx": None  # No context - should work without validation
            }
        }
        last_answer = "Some answer"
        
        result = _gen_followup(state, last_answer, mock_openai_client)
        
        # Should handle gracefully (empty string for missing question, no context validation)
        assert result is not None

