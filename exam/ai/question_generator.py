"""
Question generation module for exam.ipynb.

This module provides AI-powered question generation functionality, creating
contextual questions from PDF content and generating follow-up questions based
on student answers.

FERPA COMPLIANCE:
- PDF context and student answers are sent to OpenAI API for question generation
- No student_id, session_id, or other PII is included in API calls
- Data is encrypted in transit (HTTPS/TLS)
- Content is sanitized to prevent prompt injection and accidental PII exposure
- Ensure OpenAI agreement covers FERPA compliance (School Official exception or consent)
- Student consent is required before exam begins (handled in exam flow)

**Key Functions**:
- `_gen_main_question_with_ctx()`: Generate main question from context (ctx = context)
- `_gen_followup()`: Generate follow-up question from student answer
- `_check_duplicate_question()`: Detect duplicate questions
- `_get_cached_or_generate()`: Cache-aware question generation

**Naming Conventions**:
- **ctx**: Abbreviation for "context" (PDF text chunk used for question generation)
- **ctx_text**: Context text (the PDF chunk content)
- **ctx_sha**: Context SHA256 hash (for duplicate detection)

**Usage Example**:
    ```python
    from exam.ai.question_generator import _gen_main_question_with_ctx
    from openai import OpenAI
    
    client = OpenAI()
    
    # Generate question from PDF context
    context_text = "The main idea is that..."  # PDF chunk
    question = _gen_main_question_with_ctx(
        s=state_dict,
        ctx_text=context_text,  # ctx = context
        client=client
    )
    print(f"Generated question: {question}")
    ```

**Dependencies**:
- OpenAI client for GPT API
- Circuit breaker protection (automatic)
- Context validation and sanitization

**Error Handling**:
- Validates context before generation
- Detects and prevents duplicate questions
- Uses circuit breaker for graceful failure
"""

import hashlib
from typing import Dict, Any, Callable, Optional, Set, List

from openai import OpenAI

from shared.pdf_processing import _validate_context
from exam.utils import (
    _sanitize_for_prompt,
    _ensure_no_pii_in_content,
    _normalize_answer_for_hash,
    _compress_context_chunk,
    _truncate_answer_for_followup,
    _ensure_qmark,
    _validate_question,
    with_retry,
    _log_token_usage,
)
from exam.ai.context_manager import _get_relevant_history
from exam.config import CHAT_MODEL

# Import centralized prompts (supports encrypted prompts in production)
from shared.config.prompts import (
    SYSTEM_PROMPT,
    MAIN_QUESTION_INSTR,
    FOLLOWUP_QUESTION_INSTR,
)


def _check_duplicate_question(new_question: str, previous_questions_meta: list) -> bool:
    """
    Check if a newly generated question is a duplicate of previous questions.
    
    Uses hash comparison and semantic similarity (word overlap) to detect duplicates.
    
    Args:
        new_question: The newly generated question to check
        previous_questions_meta: List of previous question metadata dictionaries
        
    Returns:
        True if duplicate, False otherwise
    """
    if not previous_questions_meta:
        return False
    
    # Hash of the new question
    new_q_hash = hashlib.sha256(new_question.encode("utf-8")).hexdigest()
    
    # Check for exact hash match
    for q_meta in previous_questions_meta:
        if q_meta.get("question_sha256") == new_q_hash:
            return True  # Exact duplicate
    
    # IMPROVED: Check for similar questions by normalizing and comparing keywords
    new_q_normalized = _normalize_answer_for_hash(new_question.lower())
    new_q_words = set(w for w in new_q_normalized.split() if len(w) >= 4)  # Changed from 3 to 4 for better matching
    
    if len(new_q_words) < 5:
        return False  # Too short for meaningful comparison
    
    # Check against previous questions' normalized text if stored
    # For better duplicate detection, we'll check the start of questions (first ~50 chars)
    # as similar questions often start the same way
    new_q_start = new_question[:50].lower().strip()
    
    # Store question text in meta for better duplicate checking
    # We'll compare against stored question text patterns
    for q_meta in previous_questions_meta:
        # Check if stored question text exists for comparison
        if "question_text" in q_meta:
            prev_q_text = q_meta.get("question_text", "")
            if prev_q_text:
                prev_q_normalized = _normalize_answer_for_hash(prev_q_text.lower())
                prev_q_start = prev_q_text[:50].lower().strip()
                
                # Check if questions start similarly (high similarity)
                if new_q_start == prev_q_start and len(new_q_start) > 20:
                    return True  # Very similar start indicates duplicate
                
                # Check word overlap (if 80%+ words match, likely duplicate)
                prev_q_words = set(w for w in prev_q_normalized.split() if len(w) >= 4)
                if prev_q_words and new_q_words:
                    overlap = len(new_q_words.intersection(prev_q_words))
                    total_unique = len(new_q_words.union(prev_q_words))
                    if total_unique > 0 and (overlap / total_unique) > 0.8:  # 80% similarity
                        return True  # Too similar
    
    return False


def _get_cached_or_generate(
    ctx_text: str,
    generation_fn: Callable[[], str],
    rng: Optional[Any] = None,
    used_questions: Optional[Set[str]] = None
) -> str:
    """
    Generate a question, avoiding duplicates within the current session.
    
    Excludes questions already used in this exam session.
    
    Args:
        ctx_text: Context text (PDF chunk) - unused, kept for compatibility
        generation_fn: Function to call to generate new question (no arguments)
        rng: Random number generator instance (optional, for consistent randomization) - unused
        used_questions: Set of question texts already used in this exam session (optional)
    
    Returns:
        Freshly generated question
    """
    used_questions = used_questions or set()
    
    # Generate up to 3 attempts to avoid duplicates within session
    max_attempts = 3
    for attempt in range(max_attempts):
        new_question = generation_fn()
        # Check if newly generated question is already used in this session
        if new_question not in used_questions:
            return new_question
    
    # If still duplicate after max attempts, use the generated question anyway
    # (The duplicate check in _gen_main_question_with_ctx will catch it)
    return new_question


def _gen_main_question_with_ctx(s: Dict[str, Any], ctx_text: str, client: OpenAI) -> str:
    """
    Generate main question from context with cost optimizations.
    
    **Contract**:
    - **Inputs**: State dict, context text, OpenAI client
    - **Outputs**: Generated question string
    - **Invariants**: Question is always non-empty, validated before return
    - **Failure Modes**: Raises ValueError if generation fails or question is invalid
    
    **Business Logic** (Principle #3):
    - Generates questions from PDF context chunks
    - Avoids duplicate questions within the same exam session
    - Validates questions before returning (must end with '?')
    - Uses compressed context and minimal history for cost optimization
    
    **Proprietary Logic Protection** (Principle #4):
    - Prompts are loaded from encrypted environment variables in production
    - Internal prompt structure is not exposed in error messages
    
    **Cost Optimization**:
    - Uses minimal history (only relevant messages)
    - Compresses context chunks to reduce token usage
    - Uses lower temperature for more consistent results
    
    **Note**: Question caching has been disabled - always generates fresh questions.
    Chunk reuse is handled by generating new questions when the same chunk is used.
    
    Args:
        s: Session state dictionary (must have session_id, history, questions_meta)
        ctx_text: Context text (PDF chunk) to generate question from
        client: OpenAI client instance
        
    Returns:
        Generated question string (validated, ends with '?')
        
    Raises:
        ValueError: If question generation fails or generated question is invalid
        
    Example:
        ```python
        question = _gen_main_question_with_ctx(
            s=state,
            ctx_text="Machine learning is a subset of AI...",
            client=openai_client
        )
        # Returns: "What is the main difference between supervised and unsupervised learning?"
        ```
    """
    # Validate context before use
    is_valid_ctx, ctx_error = _validate_context(ctx_text)
    if not is_valid_ctx:
        raise ValueError(f"Invalid context: {ctx_error}")
    
    # Calculate context hash to check if chunk has been used before
    ctx_sha = hashlib.sha256(ctx_text.encode("utf-8")).hexdigest()
    previous_questions_meta = s.get("questions_meta", [])
    
    # PERFORMANCE: Use set for O(1) chunk reuse check (was O(n) with any())
    used_ctx_hashes = {
        q_meta.get("context_sha256") 
        for q_meta in previous_questions_meta 
        if q_meta.get("context_sha256")
    }
    chunk_reused = ctx_sha in used_ctx_hashes
    
    # COST OPTIMIZATION: Compress context chunk (3000 -> 1500 chars)
    ctx_compressed = _compress_context_chunk(ctx_text, target_length=1500)
    
    # FERPA COMPLIANCE: Ensure no PII in context before sending to OpenAI
    ctx_compressed = _ensure_no_pii_in_content(ctx_compressed)
    
    # Sanitize compressed context
    ctx_sanitized = _sanitize_for_prompt(ctx_compressed, max_len=1500)
    
    def _generate_new_question():
        """Inner function to generate new question (called by cache helper)"""
        user_content = (
            "Context:\n"
            f"{ctx_sanitized}\n\n"
            f"{MAIN_QUESTION_INSTR}"
        )
        
        # COST OPTIMIZATION: Use minimal history (only last 4 messages)
        relevant_history = _get_relevant_history(s, operation_type="question")
        
        # VARIETY OPTIMIZATION: Random temperature (0.4-0.8) for question variety
        # Use session RNG for consistent randomness per session
        session_rng = s.get("_rng") if s else None
        if session_rng:
            temp = session_rng.uniform(0.4, 0.8)  # Random between 0.4 and 0.8
        else:
            temp = 0.5  # Fallback if RNG not available
        
        # GRACEFUL FAILURE: Get circuit breaker if available (Principle #16)
        circuit_breaker = None
        try:
            from shared.circuit_breaker import get_default_circuit_breaker_manager
            manager = get_default_circuit_breaker_manager()
            circuit_breaker = manager.get_breaker("openai_chat")
        except Exception:
            pass
        
        comp = with_retry(
            client.chat.completions.create,
            circuit_breaker=circuit_breaker,
            service_name="openai_chat",
            model=CHAT_MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + relevant_history + [{"role": "user", "content": user_content}],
            temperature=temp,  # Random temperature for variety
            max_tokens=200
        )
        
        # COST OPTIMIZATION: Log token usage
        _log_token_usage(comp, "question_generation", s, model=CHAT_MODEL)
        response_text = comp.choices[0].message.content.strip()
        
        # Sanitize response to ensure it's just a question
        response_sanitized = _sanitize_for_prompt(response_text, max_len=500)
        
        # Validate generated question
        is_valid, validation_error = _validate_question(response_sanitized)
        if not is_valid:
            raise ValueError(f"Generated question failed validation: {validation_error}")
        
        return _ensure_qmark(response_sanitized)
    
    # Get session RNG for consistent selection
    session_rng = s.get("_rng") if s else None
    
    # Extract already used questions from this exam session to exclude from cache pool
    used_questions = {q_meta.get("question_text") for q_meta in previous_questions_meta if q_meta.get("question_text")}
    
    # If chunk has been used before, always generate new question (skip cache)
    if chunk_reused:
        # Chunk reused - always generate new question to ensure variety
        question = _generate_new_question()
        
        # Final duplicate check
        if _check_duplicate_question(question, previous_questions_meta):
            # If somehow still duplicate, try generating again
            for attempt in range(2):
                question = _generate_new_question()
                if not _check_duplicate_question(question, previous_questions_meta):
                    break
            else:
                # Still duplicate after retries - use fallback
                question = "Could you explain your understanding of the key concepts from this section?"
        
        return question
    
    # Chunk not used before - generate fresh question (caching disabled)
    # Get fresh question (excluding used ones from this session)
    question = _get_cached_or_generate(ctx_text, _generate_new_question, rng=session_rng, used_questions=used_questions)
    
    # Final duplicate check (should rarely trigger now since we filter used questions)
    if _check_duplicate_question(question, previous_questions_meta):
        # If somehow still duplicate, generate new one
        # (Don't cache this regeneration to avoid infinite loops)
        question = _generate_new_question()
        if _check_duplicate_question(question, previous_questions_meta):
            # Still duplicate - use fallback
            question = "Could you explain your understanding of the key concepts from this section?"
    
    return question


def _gen_followup_direct(
    main_question: str,
    student_answer: str,
    context_text: Optional[str] = None,
    previous_followups: Optional[List[str]] = None,
    client: Optional[OpenAI] = None
) -> str:
    """
    Generate follow-up question directly (low-level wrapper for API mode).
    
    Phase 3.2: Direct follow-up question generation for API mode.
    
    Args:
        main_question: The main question text
        student_answer: The student's answer to the main question
        context_text: Optional context chunk text
        previous_followups: Optional list of previous follow-up questions
        client: OpenAI client instance (required)
        
    Returns:
        Generated follow-up question string
    """
    if client is None:
        raise ValueError("OpenAI client is required")
    
    # Validate context if present
    if context_text:
        is_valid_ctx, ctx_error = _validate_context(context_text)
        if not is_valid_ctx:
            raise ValueError(f"Invalid context: {ctx_error}")
    
    # COST OPTIMIZATION: Truncate answer (2000 -> 800 chars)
    answer_truncated = _truncate_answer_for_followup(student_answer, max_chars=800)
    
    # FERPA COMPLIANCE: Ensure no PII in student answer before sending to OpenAI
    answer_truncated = _ensure_no_pii_in_content(answer_truncated)
    
    answer_sanitized = _sanitize_for_prompt(answer_truncated, max_len=1000)
    
    # COST OPTIMIZATION: Compress context if present
    ctx_sanitized = ""
    if context_text:
        ctx_compressed = _compress_context_chunk(context_text, target_length=1000)
        
        # FERPA COMPLIANCE: Ensure no PII in context before sending to OpenAI
        ctx_compressed = _ensure_no_pii_in_content(ctx_compressed)
        
        ctx_sanitized = _sanitize_for_prompt(ctx_compressed, max_len=1000)
    
    # COST OPTIMIZATION: Minimal context - only current question and answer
    user_content = ""
    if ctx_sanitized:
        user_content = f"Context: {ctx_sanitized[:800]}...\n\n"  # Further truncate for follow-ups
    
    user_content += (
        f"Question: {main_question}\n"
        f"Student Answer: {answer_sanitized}\n\n"
    )
    
    # Add previous follow-ups if provided
    if previous_followups:
        user_content += "Previous Follow-ups:\n"
        for i, prev_fq in enumerate(previous_followups[-2:], 1):  # Only last 2
            user_content += f"{i}. {prev_fq}\n"
        user_content += "\n"
    
    user_content += FOLLOWUP_QUESTION_INSTR
    
    # GRACEFUL FAILURE: Get circuit breaker if available (Principle #16)
    circuit_breaker = None
    try:
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        manager = get_default_circuit_breaker_manager()
        circuit_breaker = manager.get_breaker("openai_chat")
    except Exception:
        pass
    
    comp = with_retry(
        client.chat.completions.create,
        circuit_breaker=circuit_breaker,
        service_name="openai_chat",
        model=CHAT_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        temperature=0.6,  # Slightly higher for follow-up variety
        max_tokens=150
    )
    
    response_text = comp.choices[0].message.content.strip()
    
    # Sanitize response to ensure it's just a question
    response_sanitized = _sanitize_for_prompt(response_text, max_len=300)
    
    # Validate generated question
    is_valid, validation_error = _validate_question(response_sanitized)
    if not is_valid:
        raise ValueError(f"Generated follow-up question failed validation: {validation_error}")
    
    return _ensure_qmark(response_sanitized)


def _gen_followup(s: Dict[str, Any], last_answer: str, client: OpenAI) -> str:
    """
    Generate follow-up question with cost optimizations.
    
    COST OPTIMIZATION: Minimal context (no history), truncated answer, compressed context.
    
    Args:
        s: Session state dictionary
        last_answer: The student's last answer
        client: OpenAI client instance
        
    Returns:
        Generated follow-up question string
    """
    ctx_text = s.get("current", {}).get("ctx") or ""
    main_q = s.get("current", {}).get("main_question") or ""
    
    # Validate context if present
    if ctx_text:
        is_valid_ctx, ctx_error = _validate_context(ctx_text)
        if not is_valid_ctx:
            raise ValueError(f"Invalid context: {ctx_error}")
    
    # COST OPTIMIZATION: Truncate answer (2000 -> 800 chars)
    answer_truncated = _truncate_answer_for_followup(last_answer, max_chars=800)
    
    # FERPA COMPLIANCE: Ensure no PII in student answer before sending to OpenAI
    answer_truncated = _ensure_no_pii_in_content(answer_truncated)
    
    answer_sanitized = _sanitize_for_prompt(answer_truncated, max_len=1000)
    
    # COST OPTIMIZATION: Compress context if present
    ctx_sanitized = ""
    if ctx_text:
        ctx_compressed = _compress_context_chunk(ctx_text, target_length=1000)
        
        # FERPA COMPLIANCE: Ensure no PII in context before sending to OpenAI
        ctx_compressed = _ensure_no_pii_in_content(ctx_compressed)
        
        ctx_sanitized = _sanitize_for_prompt(ctx_compressed, max_len=1000)
    
    # COST OPTIMIZATION: Minimal context - only current question and answer
    user_content = ""
    if ctx_sanitized:
        user_content = f"Context: {ctx_sanitized[:800]}...\n\n"  # Further truncate for follow-ups
    
    user_content += (
        f"Question: {main_q}\n"
        f"Student Answer: {answer_sanitized}\n\n"
        f"{FOLLOWUP_QUESTION_INSTR}"
    )
    
    # COST OPTIMIZATION: NO history for follow-ups (only system prompt)
    minimal_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "assistant", "content": main_q},
        {"role": "user", "content": answer_sanitized}
    ]
    
    # GRACEFUL FAILURE: Get circuit breaker if available (Principle #16)
    circuit_breaker = None
    try:
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        manager = get_default_circuit_breaker_manager()
        circuit_breaker = manager.get_breaker("openai_chat")
    except Exception:
        pass
    
    # COST OPTIMIZATION: Lower temperature (0.5 -> 0.3)
    comp = with_retry(
        client.chat.completions.create,
        circuit_breaker=circuit_breaker,
        service_name="openai_chat",
        model=CHAT_MODEL,
        messages=minimal_messages + [{"role": "user", "content": user_content}],
        temperature=0.3,  # Reduced from 0.5
        max_tokens=150
    )
    
    # COST OPTIMIZATION: Log token usage
    _log_token_usage(comp, "followup_generation", s, model=CHAT_MODEL)
    response_text = comp.choices[0].message.content.strip()
    
    # Sanitize response to ensure it's just a question
    response_sanitized = _sanitize_for_prompt(response_text, max_len=500)
    
    # Validate generated question
    is_valid, validation_error = _validate_question(response_sanitized)
    if not is_valid:
        raise ValueError(f"Generated follow-up question failed validation: {validation_error}")
    
    return _ensure_qmark(response_sanitized)

