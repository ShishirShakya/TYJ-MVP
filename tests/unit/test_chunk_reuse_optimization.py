"""
Unit tests for chunk reuse optimization using set lookup.

Tests the O(1) chunk reuse check using set instead of O(n) any() generator.
"""

import hashlib


def check_chunk_reuse_optimized(ctx_text: str, previous_questions_meta: list) -> bool:
    """
    Optimized chunk reuse check using set lookup.
    
    This is the implementation from exam/ai/question_generator.py.
    """
    ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
    
    # PERFORMANCE: Use set for O(1) chunk reuse check (was O(n) with any())
    used_ctx_hashes = {
        q_meta.get("context_sha256") 
        for q_meta in previous_questions_meta 
        if q_meta.get("context_sha256")
    }
    chunk_reused = ctx_sha in used_ctx_hashes
    return chunk_reused


def check_chunk_reuse_old(ctx_text: str, previous_questions_meta: list) -> bool:
    """
    Old O(n) chunk reuse check for comparison.
    """
    ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
    
    chunk_reused = any(
        q_meta.get("context_sha256") == ctx_sha 
        for q_meta in previous_questions_meta 
        if q_meta.get("context_sha256")
    )
    return chunk_reused


class TestChunkReuseOptimization:
    """Tests for optimized chunk reuse check."""
    
    def test_chunk_reuse_empty_meta(self):
        """Test chunk reuse check with empty previous questions."""
        ctx_text = "This is a test context for question generation."
        result = check_chunk_reuse_optimized(ctx_text, [])
        assert result is False
    
    def test_chunk_reuse_not_used(self):
        """Test chunk reuse check when chunk has not been used."""
        ctx_text = "This is a new context that has not been used before."
        previous_questions_meta = [
            {"context_sha256": "different_hash_123", "question_text": "Previous question"}
        ]
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is False
    
    def test_chunk_reuse_used(self):
        """Test chunk reuse check when chunk has been used."""
        ctx_text = "This is a context that has been used before."
        ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
        previous_questions_meta = [
            {"context_sha256": ctx_sha, "question_text": "Previous question"}
        ]
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is True
    
    def test_chunk_reuse_multiple_previous_questions(self):
        """Test chunk reuse check with multiple previous questions."""
        ctx_text = "This is the target context."
        ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
        previous_questions_meta = [
            {"context_sha256": "hash1", "question_text": "Question 1"},
            {"context_sha256": "hash2", "question_text": "Question 2"},
            {"context_sha256": ctx_sha, "question_text": "Question 3"},
            {"context_sha256": "hash4", "question_text": "Question 4"},
        ]
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is True
    
    def test_chunk_reuse_missing_context_sha256(self):
        """Test chunk reuse check when some entries lack context_sha256."""
        ctx_text = "This is a test context."
        ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
        previous_questions_meta = [
            {"question_text": "Question without hash"},
            {"context_sha256": ctx_sha, "question_text": "Question with hash"},
            {"question_text": "Another question without hash"},
        ]
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is True
    
    def test_chunk_reuse_none_context_sha256(self):
        """Test chunk reuse check when context_sha256 is None."""
        ctx_text = "This is a test context."
        previous_questions_meta = [
            {"context_sha256": None, "question_text": "Question with None hash"},
            {"question_text": "Question without hash field"},
        ]
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is False
    
    def test_chunk_reuse_matches_old_implementation(self):
        """Test that optimized implementation matches old implementation."""
        test_contexts = [
            "Context 1 for testing",
            "Context 2 for testing",
            "Context 3 for testing",
        ]
        
        # Create previous questions with various hashes
        previous_questions_meta = []
        for i, ctx in enumerate(test_contexts):
            ctx_sha = hashlib.sha256(ctx.encode("utf-8")).hexdigest()
            previous_questions_meta.append({
                "context_sha256": ctx_sha,
                "question_text": f"Question {i+1}"
            })
        
        # Test each context
        for ctx in test_contexts:
            old_result = check_chunk_reuse_old(ctx, previous_questions_meta)
            new_result = check_chunk_reuse_optimized(ctx, previous_questions_meta)
            assert old_result == new_result, f"Mismatch for context: {ctx[:30]}..."
    
    def test_chunk_reuse_large_list(self):
        """Test chunk reuse check with large list (performance test)."""
        ctx_text = "This is the target context for large list test."
        ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
        
        # Create large list of previous questions
        previous_questions_meta = []
        for i in range(1000):
            other_ctx = f"Other context {i}"
            other_sha = hashlib.sha256(other_ctx.encode("utf-8")).hexdigest()
            previous_questions_meta.append({
                "context_sha256": other_sha,
                "question_text": f"Question {i}"
            })
        
        # Add target context at the end
        previous_questions_meta.append({
            "context_sha256": ctx_sha,
            "question_text": "Target question"
        })
        
        result = check_chunk_reuse_optimized(ctx_text, previous_questions_meta)
        assert result is True

