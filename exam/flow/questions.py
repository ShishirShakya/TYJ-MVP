"""
Question flow functions for exam interface.

This module orchestrates the question generation flow, handling main questions,
follow-up questions, and user interactions.

**Key Functions**:
- `ask_main_question()`: Generate and ask main question from PDF context
- `ask_followup_question()`: Generate and ask follow-up question based on answer
- `on_first_mic_press()`: Handle first microphone press (plays question audio)

**Flow Pattern**:
1. Validate PDF chunks are available
2. Select context chunk (avoid duplicates)
3. Generate question from context
4. Convert to audio (TTS)
5. Update UI with question and audio

**Usage Example**:
    ```python
    from exam.flow.questions import ask_main_question
    from openai import OpenAI
    
    client = OpenAI()
    state, audio, status, mic, history, cam, proctor, timeout = ask_main_question(
        s=state_dict,
        gr_module=gr,
        client=client,
        dependencies={
            "ensure_state": ensure_state,
            "get_chunks": get_chunks,
            # ... other dependencies
        }
    )
    ```

**Dependencies**:
- Uses dependency injection pattern (all dependencies passed explicitly)
- Requires: ensure_state, get_chunks, _gen_main_question_with_ctx, tts_to_mp3, etc.
- Optional: progress callback, circuit breaker manager

**Error Handling**:
- Validates PDF chunks before generation
- Handles duplicate questions gracefully
- Uses circuit breaker for API calls
- Provides user-friendly error messages
"""

import hashlib
import logging
import time
from typing import Dict, Any, Optional, Callable, Tuple, TYPE_CHECKING

from openai import OpenAI

from shared.logging_config import get_logger
from shared.constants import (
    PROCESSING_AUDIO_RESPONSE_MSG,
    format_timeout_notification,
    format_question_label,
    format_processing_message_with_context,
    STATUS_QUESTION_ASKED,
    STATUS_FOLLOWUP_ASKED,
    STATUS_QUESTION_LIMIT_REACHED,
    ERROR_NO_PDF_CONTENT,
    ERROR_PDF_NOT_AVAILABLE,
    ERROR_NO_VALID_CHUNKS,
    INFO_COMPLETE_CURRENT_BLOCK,
    DEFAULT_ERROR_QUESTION_GENERATION,
    DEFAULT_ERROR_FOLLOWUP_GENERATION,
    PDF_ERROR_SUFFIX_LOAD_BEFORE_START,
    PDF_ERROR_SUFFIX_LOAD_VALID,
    PDF_ERROR_SUFFIX_RELOAD,
    format_pdf_validation_error,
    format_error_with_solution,
    FALLBACK_NO_TEXTBOOK_CONTENT,
)
from exam.flow.error_handling import handle_flow_error

# OBSERVABILITY: Get logger for structured logging (Principle #13)
logger = get_logger()

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr


def ask_main_question(
    s: Dict[str, Any],
    gr_module,
    client: OpenAI,
    dependencies: Dict[str, Any],
    progress: Optional[Callable] = None
) -> Tuple:
    """
    Ask main question with chunk selection, validation, and audio generation.
    
    **Contract**:
    - **Inputs**: State dictionary, Gradio module, OpenAI client, dependencies dict, optional progress callback
    - **Outputs**: Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, timeout_update)
    - **Invariants**: State must have required fields (ensured by `ensure_state()`)
    - **Failure Modes**: Returns error state in status_update; does not raise exceptions
    
    Args:
        s: State dictionary (must have required fields from `ensure_state()`)
        gr_module: Gradio module (for `gr.update()`)
        client: OpenAI client instance
        dependencies: Dictionary with dependencies (see required_keys list below)
        progress: Optional progress callback
        
    Returns:
        Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, timeout_update)
        - state: Updated state dictionary
        - audio: Audio update (Gradio update object or None)
        - status_update: Status message update (Gradio update object)
        - mic_update: Microphone component update (Gradio update object)
        - history: Chat history update (Gradio update object)
        - cam_update: Camera component update (Gradio update object)
        - status_update: Status update (Gradio update object)
        - timeout_update: Timeout countdown update (Gradio update object)
        
    Raises:
        Never raises exceptions. Errors are handled internally and returned in status_update.
        
    **Required Dependencies**:
    - ensure_state, reset_current_block, get_followup_range
    - get_chunks, validate_chunks_available, _validate_context
    - _gen_main_question_with_ctx, tts_to_mp3, get_audio_duration
    - get_max_answer_timeout_sec, _calculate_timeout_status
    - _proctor_end_updates, _categorize_error
    """
    # Extract dependencies
    ensure_state = dependencies["ensure_state"]
    reset_current_block = dependencies["reset_current_block"]
    get_followup_range = dependencies["get_followup_range"]
    get_chunks = dependencies["get_chunks"]
    _validate_context = dependencies["_validate_context"]
    _gen_main_question_with_ctx = dependencies["_gen_main_question_with_ctx"]
    tts_to_mp3 = dependencies["tts_to_mp3"]
    get_audio_duration = dependencies["get_audio_duration"]
    get_max_answer_timeout_sec = dependencies["get_max_answer_timeout_sec"]
    _calculate_timeout_status = dependencies["_calculate_timeout_status"]
    _proctor_end_updates = dependencies["_proctor_end_updates"]
    _categorize_error = dependencies["_categorize_error"]
    # DETERMINISTIC: Extract time_provider for deterministic behavior (Principle #5)
    time_provider = dependencies.get("time_provider")
    if time_provider is None:
        # Fallback to default if not provided (backward compatibility)
        from shared.time_provider import get_default_time_provider
        time_provider = get_default_time_provider()
    
    s = ensure_state(s)
    if s["phase"] == "complete":
        proctor_cam_upd, proctor_status_upd = _proctor_end_updates(s, gr_module)
        return s, None, gr_module.update(value="✔️ Exam already completed."), gr_module.update(interactive=False), s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(value="", visible=False)  # timeout_update
    if s["asked_main"] >= s["limit"]:
        s["phase"] = "complete"
        proctor_cam_upd, proctor_status_upd = _proctor_end_updates(s, gr_module)
        return s, None, gr_module.update(value=STATUS_QUESTION_LIMIT_REACHED), gr_module.update(interactive=False), s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(value="", visible=False)  # timeout_update
    if s["phase"] not in ("armed", "idle", "awaiting_next_main"):
        return s, None, gr_module.update(value=INFO_COMPLETE_CURRENT_BLOCK), gr_module.update(interactive=False), s["history"], gr_module.update(), gr_module.update(), gr_module.update(value="", visible=False)  # timeout_update
    try:
        reset_current_block(s)
        # Use state values for followups range if available, otherwise use globals
        followups_min, followups_max = get_followup_range(s)
        # Ensure target_followups respects the range properly
        # If max=0, then target_followups must be 0
        # If min=0 and max=1, can be 0 or 1 (both valid)
        # Otherwise, use normal randint range
        if followups_max == 0:
            s["current"]["target_followups"] = 0
        elif followups_min == 0 and followups_max == 1:
            # Special case: can be 0 or 1, both are valid
            s["current"]["target_followups"] = s["_rng"].randint(0, 1)
        else:
            # Normal case: min >= 1 or max > 1
            s["current"]["target_followups"] = s["_rng"].randint(followups_min, followups_max)
        
        # RNG OPTIMIZATION: Pre-validate chunks array before selection
        # Handle edge cases early for better performance and user experience
        chunks = get_chunks()  # Use helper function for thread safety
        if not chunks:
            # OBSERVABILITY: Use structured logging (Principle #13)
            logger.warning(
                "chunks_empty_main",
                session_id=s.get("session_id", "unknown"),
                request_id=s.get("request_id", "unknown"),
                message="CHUNKS is empty during main question generation"
            )
            raise ValueError(format_error_with_solution(ERROR_NO_PDF_CONTENT, PDF_ERROR_SUFFIX_LOAD_BEFORE_START))
        
        # Check if chunks contains only fallback message
        if len(chunks) == 1 and chunks[0].startswith(FALLBACK_NO_TEXTBOOK_CONTENT.split("(")[0] + "("):
            # OBSERVABILITY: Use structured logging (Principle #13)
            logger.warning(
                "chunks_fallback_only",
                session_id=s.get("session_id", "unknown"),
                request_id=s.get("request_id", "unknown"),
                message="CHUNKS contains only fallback message - PDF not loaded"
            )
            raise ValueError(format_error_with_solution(ERROR_PDF_NOT_AVAILABLE, PDF_ERROR_SUFFIX_LOAD_VALID))
        
        # Pre-filter valid chunks for efficiency
        valid_chunks_with_hashes = []
        for candidate_ctx in chunks:
            is_valid, _ = _validate_context(candidate_ctx)
            if is_valid:
                candidate_hash = hashlib.sha256(candidate_ctx.encode("utf-8")).hexdigest()
                valid_chunks_with_hashes.append((candidate_ctx, candidate_hash))
        
        # RANDOMIZATION: Shuffle valid chunks immediately after building the list
        # This ensures the pool is randomized before any selection, improving true randomness
        if valid_chunks_with_hashes:
            s["_rng"].shuffle(valid_chunks_with_hashes)
        
        # If no valid chunks, raise error
        if not valid_chunks_with_hashes:
            chunks = get_chunks()
            # OBSERVABILITY: Use structured logging (Principle #13)
            logger.warning(
                "no_valid_chunks_after_validation",
                session_id=s.get("session_id", "unknown"),
                request_id=s.get("request_id", "unknown"),
                total_chunks=len(chunks),
                valid_chunks=0,
                message="No valid chunks found after validation"
            )
            raise ValueError(format_error_with_solution(
                ERROR_NO_VALID_CHUNKS,
                format_pdf_validation_error(len(chunks), 0) + " " + PDF_ERROR_SUFFIX_RELOAD
            ))
        
        # GUARDRAIL: Duplicate Context Chunk Prevention with improved randomization
        # Track used context chunks to ensure questions are spread across the chapter
        used_ctx_hashes = s.get("used_context_hashes", set())
        
        # RNG OPTIMIZATION: Early exit - if all chunks used, reset and shuffle for even distribution
        if len(used_ctx_hashes) >= len(valid_chunks_with_hashes):
            # All chunks used - reset and shuffle for round-robin-like even distribution
            # This ensures questions are spread across the entire chapter, not just repeating same chunks
            used_ctx_hashes.clear()
            # Shuffle valid chunks for this round to ensure different order each cycle
            shuffled_valid = valid_chunks_with_hashes.copy()
            s["_rng"].shuffle(shuffled_valid)
            ctx, ctx_hash = s["_rng"].choice(shuffled_valid)
            used_ctx_hashes.add(ctx_hash)
        else:
            # Find unused chunk with improved randomization
            unused_valid = [(c, h) for c, h in valid_chunks_with_hashes if h not in used_ctx_hashes]
            
            if unused_valid:
                # Randomly select from unused chunks for better distribution
                ctx, ctx_hash = s["_rng"].choice(unused_valid)
                used_ctx_hashes.add(ctx_hash)
            else:
                # Fallback: all valid chunks were used somehow (shouldn't happen but handle gracefully)
                ctx, ctx_hash = s["_rng"].choice(valid_chunks_with_hashes)
                used_ctx_hashes.add(ctx_hash)
        
        s["current"]["ctx"] = ctx
        s["used_context_hashes"] = used_ctx_hashes
        
        # Find the chunk index in chunks for status display (use helper function for thread safety)
        chunks = get_chunks()
        chunk_index = None
        for idx, chunk in enumerate(chunks):
            if chunk == ctx:
                chunk_index = idx + 1  # 1-based for readability
                break
        
        # Store chunk index and total chunks in state
        s["current"]["chunk_index"] = chunk_index
        s["current"]["total_chunks"] = len(chunks) if chunks else 0
        
        # Generate question with retry on validation/duplicate errors
        q = None
        max_gen_attempts = 3
        for gen_attempt in range(max_gen_attempts):
            try:
                q = _gen_main_question_with_ctx(s, ctx, client=client)
                break  # Success, exit loop
            except ValueError as ve:
                # If validation/duplicate error and we have retries left, try again
                if gen_attempt < max_gen_attempts - 1:
                    continue  # Try generating again
                else:
                    # Last attempt failed, use fallback
                    q = "Could you explain your understanding of the key concepts from this section?"
                    break
        
        if not q:
            q = "Could you explain your understanding of the key concepts from this section?"
        
        s["current"]["main_question"] = q
        
        # QUESTION PROVENANCE TRACKING: Store cryptographic provenance for auditability
        # FERPA-compliant: Only stores cryptographic hashes (SHA-256) of context and questions.
        # No personally identifiable information (PII) is stored - only hashes for integrity verification.
        q_sha = hashlib.sha256(q.encode("utf-8")).hexdigest()
        ctx_sha = hashlib.sha256(ctx.encode("utf-8")).hexdigest()
        s.setdefault("questions_meta", []).append({
            "index": s.get("asked_main", 0) + 1,   # 1-based for readability
            "context_sha256": ctx_sha,             # Cryptographic hash only - not PII
            "context_len": len(ctx),               # Metadata for validation only
            "question_sha256": q_sha,              # Cryptographic hash only - not PII
            "question_text": q,                     # Store question text for better duplicate detection
        })
        
        s["history"].append({"role":"assistant","content":PROCESSING_AUDIO_RESPONSE_MSG})
        
        # Add visual distinction for main questions with numbering
        asked_main = s.get("asked_main", 0)
        limit = s.get("limit", 0)
        if limit > 0:
            question_label = format_question_label(asked_main + 1, limit, "main")
            q_with_label = f"{question_label}\n\n{q}"
        else:
            q_with_label = q
        
        s["history"][-1] = {"role":"assistant","content":q_with_label}
        s["phase"] = "awaiting_main_answer"
        # Notify student about answer timeout (use helper function with state for cross-context reliability)
        max_timeout = get_max_answer_timeout_sec(s)  # Pass state to get value from state dict if context var unavailable
        timeout_notification = f"\n\n{format_timeout_notification(max_timeout, is_followup=False)}"
        s["history"].append({"role":"assistant","content":timeout_notification})
        if progress:
            progress(0.5)
        audio = tts_to_mp3(q, client, s, progress=progress)
        if progress:
            progress(1.0)
        # Get audio duration and start timer AFTER audio finishes playing
        audio_duration = get_audio_duration(audio) if audio else 0.0
        # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
        s["current"]["q_time"] = time_provider.time() + audio_duration
        # Mic should only be enabled when timer countdown starts (elapsed >= 0)
        # Since timer starts after audio finishes, mic will be disabled until then
        from exam.ui.helpers import _calculate_mic_interactive_state
        mic_interactive = _calculate_mic_interactive_state(s, gr_module)
        return s, audio, gr_module.update(value=STATUS_QUESTION_ASKED), gr_module.update(value=None, interactive=mic_interactive), s["history"], gr_module.update(), gr_module.update(), _calculate_timeout_status(s, gr_module, get_max_answer_timeout_sec)  # timeout countdown
    except Exception as e:
        # Use centralized error handling
        return handle_flow_error(
            s=s,
            e=e,
            gr_module=gr_module,
            dependencies=dependencies,
            processing_message=PROCESSING_AUDIO_RESPONSE_MSG,
            default_msg="Question generation failed",
            tuple_length=8,
            error_context="question_generation_error"
        )


def ask_followup_question(
    s: Dict[str, Any],
    gr_module,
    client: OpenAI,
    dependencies: Dict[str, Any],
    progress: Optional[Callable] = None
) -> Tuple:
    """
    Ask follow-up question based on student's answer.
    
    Args:
        s: State dictionary
        gr_module: Gradio module
        client: OpenAI client
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - _gen_followup: Function to generate followup question
            - tts_to_mp3: Function to convert text to speech
            - get_audio_duration: Function to get audio duration
            - get_max_answer_timeout_sec: Function to get max answer timeout
            - _calculate_timeout_status: Function to calculate timeout status
        progress: Optional progress callback
        
    Returns:
        Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, finish_update, timeout_update)
    """
    # Extract dependencies
    ensure_state = dependencies["ensure_state"]
    _gen_followup = dependencies["_gen_followup"]
    tts_to_mp3 = dependencies["tts_to_mp3"]
    get_audio_duration = dependencies["get_audio_duration"]
    get_max_answer_timeout_sec = dependencies["get_max_answer_timeout_sec"]
    _calculate_timeout_status = dependencies["_calculate_timeout_status"]
    _categorize_error = dependencies["_categorize_error"]
    # DETERMINISTIC: Extract time_provider for deterministic behavior (Principle #5)
    time_provider = dependencies.get("time_provider")
    if time_provider is None:
        # Fallback to default if not provided (backward compatibility)
        from shared.time_provider import get_default_time_provider
        time_provider = get_default_time_provider()
    
    s = ensure_state(s)
    try:
        last_answer = s["current"]["answers"][-1] if s["current"]["answers"] else ""
        s["history"].append({"role":"assistant","content":PROCESSING_AUDIO_RESPONSE_MSG})
        fq = _gen_followup(s, last_answer, client=client)
        
        # Add visual distinction for follow-up questions with progress context
        followup_num = s["current"].get("followups_done", 0) + 1
        target_followups = s["current"].get("target_followups", 0)
        asked_main = s.get("asked_main", 0)
        limit = s.get("limit", 0)
        
        # Format follow-up label using helper function
        followup_label = format_question_label(followup_num, target_followups, "followup")
        
        # Add question context if available
        if asked_main > 0 and limit > 0:
            question_context = f" (Question {asked_main + 1} of {limit})"
        else:
            question_context = ""
        
        fq_with_context = f"{followup_label}{question_context}\n\n{fq}"
        s["history"][-1] = {"role":"assistant","content":fq_with_context}
        s["phase"] = "awaiting_followup_answer"
        # Notify student about answer timeout (use helper function with state for cross-context reliability)
        max_timeout = get_max_answer_timeout_sec(s)  # Pass state to get value from state dict if context var unavailable
        timeout_notification = f"\n\n{format_timeout_notification(max_timeout, is_followup=True)}"
        s["history"].append({"role":"assistant","content":timeout_notification})
        if progress:
            progress(0.5)
        audio = tts_to_mp3(fq, client, s, progress=progress)
        if progress:
            progress(1.0)
        # Get audio duration and start timer AFTER audio finishes playing
        audio_duration = get_audio_duration(audio) if audio else 0.0
        # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
        s["current"]["q_time"] = time_provider.time() + audio_duration
        # Mic should only be enabled when timer countdown starts (elapsed >= 0)
        # Since timer starts after audio finishes, mic will be disabled until then
        from exam.ui.helpers import _calculate_mic_interactive_state
        mic_interactive = _calculate_mic_interactive_state(s, gr_module)
        return s, audio, gr_module.update(value=STATUS_FOLLOWUP_ASKED), gr_module.update(value=None, interactive=mic_interactive), s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False), _calculate_timeout_status(s, gr_module, get_max_answer_timeout_sec)  # Finish button remains disabled, timeout countdown
    except Exception as e:
        # Use centralized error handling
        return handle_flow_error(
            s=s,
            e=e,
            gr_module=gr_module,
            dependencies=dependencies,
            processing_message=PROCESSING_AUDIO_RESPONSE_MSG,
            default_msg="Follow-up question generation failed",
            tuple_length=9,
            error_context="followup_question_error"
        )


def on_first_mic_press(
    s: Dict[str, Any],
    status_md: Any,
    gr_module,
    client: OpenAI,
    dependencies: Dict[str, Any]
) -> Tuple:
    """
    First press after consent: play examiner's question (mic OFF), do NOT record.
    Student releases and presses Record again to answer.
    
    Args:
        s: State dictionary
        status_md: Status markdown component
        gr_module: Gradio module
        client: OpenAI client
        dependencies: Dictionary with dependencies:
            - ensure_state: Function to ensure state
            - ask_main_question: Function to ask main question
            
    Returns:
        Tuple of (state, audio, status_update, history, cam_update, status_update, step_indicator_update)
    """
    ensure_state_fn = dependencies["ensure_state"]
    ask_main_question_func = dependencies["ask_main_question"]
    
    s = ensure_state_fn(s)
    if s.get("ready_for_question", False) and s.get("phase") in ("armed", "idle"):
        s["ready_for_question"] = False
        # Call ask_main_question with all required parameters
        s, audio, msg, _micupd, _hist, cam_upd, cam_status_upd, _timeout = ask_main_question_func(
            s, gr_module, client, dependencies
        )
        # Priority 1: Update step indicator to show exam is now Active (Step 6)
        from exam.ui.helpers import get_step_indicator_html
        step_indicator_value = get_step_indicator_html(6)
        return (s, audio,
                gr_module.update(value="🎤 Examiner is asking your question. After it finishes, press **Record** again to answer."),
                s["history"], cam_upd, cam_status_upd,
                gr_module.update(value=step_indicator_value, visible=True))  # Priority 1: Update step indicator
    # Priority 1: Keep step indicator unchanged if not ready
    return s, None, gr_module.update(value=""), s["history"], gr_module.update(), gr_module.update(), gr_module.update()

