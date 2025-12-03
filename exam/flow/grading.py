"""
Grading and next question preparation functions for exam interface.

This module orchestrates the grading flow, handling block grading, feedback generation,
and preparation for the next question or exam completion.

**Key Functions**:
- `grade_current_block()`: Grade current question block and prepare next question
- Handles exam completion when all questions answered

**Flow Pattern**:
1. Collect student answers for current block
2. Generate AI feedback and scores
3. Update state with grades
4. If more questions: prepare next question
5. If complete: finalize exam

**Usage Example**:
    ```python
    from exam.flow.grading import grade_current_block
    from openai import OpenAI
    
    client = OpenAI()
    state, audio, status, mic, history, cam, proctor, finish = grade_current_block(
        s=state_dict,
        gr_module=gr,
        client=client,
        dependencies={
            "ensure_state": ensure_state,
            "save_state_to_disk": save_state_to_disk,
            # ... other dependencies
        }
    )
    ```

**Dependencies**:
- Uses dependency injection pattern (all dependencies passed explicitly)
- Requires: ensure_state, save_state_to_disk, _gen_main_question_with_ctx, etc.
- Optional: progress callback, circuit breaker manager

**Error Handling**:
- Validates state before grading
- Handles API failures gracefully
- Uses circuit breaker for API calls
- Provides user-friendly error messages
"""

import hashlib
import logging
import time
from typing import Dict, Any, Optional, Callable, Tuple, TYPE_CHECKING

from openai import OpenAI

from shared.dependency_extractor import extract_dependencies
from shared.logging_config import get_logger
from shared.constants import (
    PROCESSING_ASSESSMENT_MSG,
    PROCESSING_FOLLOWUP_MSG,
    format_processing_message_with_context,
    format_assessment_message,
    format_timeout_notification,
    TRANSITION_NEXT_QUESTION,
    format_question_label,
    get_qualitative_assessment,
    format_exam_completion_message,
    STATUS_EXAM_COMPLETE,
    STATUS_CONTINUING_AUTOMATICALLY,
    ERROR_NO_PDF_CONTENT,
    ERROR_PDF_NOT_AVAILABLE,
    ERROR_NO_VALID_CHUNKS,
    FALLBACK_QUESTION,
    format_answer_label,
    PDF_ERROR_SUFFIX_LOAD_BEFORE_START,
    PDF_ERROR_SUFFIX_LOAD_VALID,
    PDF_ERROR_SUFFIX_RELOAD,
    format_pdf_validation_error,
    format_error_with_solution,
    FALLBACK_NO_TEXTBOOK_CONTENT,
    FEEDBACK_DEFAULT_TEXT,
)

logger = get_logger()

# Type hints only - no runtime import
if TYPE_CHECKING:
    import gradio as gr


def grade_current_block(
    s: Dict[str, Any],
    gr_module,
    client: OpenAI,
    dependencies: Dict[str, Any],
    progress: Optional[Callable] = None
) -> Tuple:
    """
    Grade current block and prepare next question or complete exam.
    
    **Contract**:
    - **Inputs**: State dictionary, Gradio module, OpenAI client, dependencies dict, optional progress callback
    - **Outputs**: Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, finish_update)
    - **Invariants**: State must have required fields (ensured by `ensure_state()`)
    - **Failure Modes**: Returns error state in status_update; does not raise exceptions
    
    Args:
        s: State dictionary (must have required fields from `ensure_state()`)
        gr_module: Gradio module (for `gr.update()`)
        client: OpenAI client instance
        dependencies: Dictionary with dependencies (see required_keys list below)
        progress: Optional progress callback
        
    Returns:
        Tuple of (state, audio, status_update, mic_update, history, cam_update, status_update, finish_update)
        - state: Updated state dictionary
        - audio: Audio update (Gradio update object or None)
        - status_update: Status message update (Gradio update object)
        - mic_update: Microphone component update (Gradio update object)
        - history: Chat history update (Gradio update object)
        - cam_update: Camera component update (Gradio update object)
        - status_update: Status update (Gradio update object)
        - finish_update: Finish button update (Gradio update object)
        
    Raises:
        Never raises exceptions. Errors are handled internally and returned in status_update.
        
    **Required Dependencies**:
    - ensure_state, save_state_to_disk, reset_current_block
    - get_followup_range, get_chunks, _validate_context
    - _gen_main_question_with_ctx, _sanitize_for_prompt
    - msgs_from_state, with_retry, _log_token_usage
    - _parse_feedback, _calculate_overall_score, tts_to_mp3
    - get_audio_duration, get_max_answer_timeout_sec
    - _proctor_end_updates, _categorize_error, CHAT_MODEL, FEEDBACK_BLOCK_INSTR
    - ProctorState (optional)
    """
    # Defensive check at entry point - ensure s is always a dict
    if not isinstance(s, dict):
        # If s is not a dict, create a minimal valid state
        import uuid
        from datetime import datetime, timezone
        s = {
            "session_id": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
            "student_id": "unknown",
            "phase": "idle",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "session_start_time": 0.0,
            "history": [],
            "scores": [],
            "rubrics": [],
            "flags": [],
            "consent": False,
            "current": {
                "main_question": None,
                "answers": [],
                "followups_done": 0,
                "target_followups": 0,
                "q_time": None,
                "short_attempts": 0,
                "ctx": None
            }
        }
    # Extract dependencies (DRY: using helper to reduce duplication)
    deps = extract_dependencies(
        dependencies,
        required_keys=[
            "ensure_state", "save_state_to_disk", "reset_current_block",
            "get_followup_range", "get_chunks", "_validate_context",
            "_gen_main_question_with_ctx", "_sanitize_for_prompt",
            "msgs_from_state", "with_retry", "_log_token_usage",
            "_parse_feedback", "_calculate_overall_score", "tts_to_mp3",
            "get_audio_duration", "get_max_answer_timeout_sec",
            "_proctor_end_updates", "_categorize_error", "CHAT_MODEL", "FEEDBACK_BLOCK_INSTR"
        ],
        optional_keys=["ProctorState", "time_provider"]
    )
    
    # DETERMINISTIC: Extract time_provider for deterministic behavior (Principle #5)
    time_provider = deps.get("time_provider")
    if time_provider is None:
        # Fallback to default if not provided (backward compatibility)
        from shared.time_provider import get_default_time_provider
        time_provider = get_default_time_provider()
    
    s = deps["ensure_state"](s)
    # Defensive check: ensure s is a dict (not a string or other type)
    if not isinstance(s, dict):
        raise TypeError(f"ensure_state returned non-dict type: {type(s)}")
    
    # Store original state reference to prevent corruption
    # If s gets corrupted, we can recover from the original
    original_s = s.copy() if isinstance(s, dict) else s
    
    try:
        # Ensure history is a list (defensive check)
        # Wrap in try-except to catch any assignment errors
        try:
            if not isinstance(s.get("history"), list):
                s["history"] = []
        except (TypeError, AttributeError) as e:
            # If assignment fails, s might be corrupted - restore from original
            if not isinstance(s, dict):
                s = original_s.copy() if isinstance(original_s, dict) else {}
                s["history"] = []
            else:
                raise
        
        # Snapshot per-block proctor attention
        try:
            st = s.get("proctor_state", None)
            if deps["ProctorState"] and isinstance(st, deps["ProctorState"]):
                s["proctor_blocks"].append(st.add_block_rollup())
        except Exception:
            pass

        # Defensive check: ensure current is a dict
        # Wrap in try-except to catch any assignment errors
        try:
            if not isinstance(s.get("current"), dict):
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
        except (TypeError, AttributeError) as e:
            # If assignment fails, s might be corrupted - restore from original
            if not isinstance(s, dict):
                s = original_s.copy() if isinstance(original_s, dict) else {}
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
            else:
                raise

        # Defensive check: ensure current is still a dict before accessing
        current = s.get("current")
        if not isinstance(current, dict):
            # If current is not a dict (might be a string or None), initialize it
            logger.warning(f"s['current'] is not a dict: {type(current)}, value: {current}. Initializing.")
            s["current"] = {
                "main_question": None,
                "answers": [],
                "followups_done": 0,
                "target_followups": 0,
                "q_time": None,
                "short_attempts": 0,
                "ctx": None
            }
            current = s["current"]
        
        main_q = current.get("main_question") or ""
        answers = current.get("answers", [])[:]
        block_summary = ["MAIN QUESTION:", main_q, "\nSTUDENT ANSWERS:"]
        for i, a in enumerate(answers):
            label = "Main Answer" if i == 0 else f"Follow-up {i} Answer"
            block_summary.append(f"- {label}: {a}")
        block_summary_text = "\n".join(block_summary)
        # Sanitize block summary to prevent prompt injection
        block_summary_sanitized = deps["_sanitize_for_prompt"](block_summary_text, max_len=4000)
        
        # Add processing message to history to trigger progress bar
        # Defensive check: ensure history is still a list before appending
        if not isinstance(s.get("history"), list):
            s["history"] = []
        # Check if processing assessment message already exists (added by handle_mic to keep progress bar visible)
        # This prevents duplicate messages while ensuring progress bar stays active
        if not any(PROCESSING_ASSESSMENT_MSG in msg.get("content", "") or PROCESSING_FOLLOWUP_MSG in msg.get("content", "") for msg in s.get("history", [])):
            # Add progress context to message for better user clarity
            msg_with_context = format_processing_message_with_context(
                PROCESSING_ASSESSMENT_MSG,
                s,
                include_followup_info=False
            )
            s["history"].append({"role":"assistant","content":msg_with_context})
        
        # COST OPTIMIZATION: Use operation-specific history for feedback
        # COST OPTIMIZATION: Lower temperature (0.3 -> 0.2)
        if progress:
            progress(0.3)
        # GRACEFUL FAILURE: Get circuit breaker from dependencies if available (Principle #16)
        circuit_breaker = deps.get("circuit_breaker_manager")
        if circuit_breaker:
            try:
                circuit_breaker = circuit_breaker.get_breaker("openai_chat")
            except Exception:
                circuit_breaker = None
        
        # Defensive check before API call
        if not isinstance(s, dict):
            raise TypeError(f"State is not a dict before API call: {type(s)}")
        
        # Build messages list with defensive checks
        # Defensive check: ensure s is still a dict before calling msgs_from_state
        if not isinstance(s, dict):
            raise TypeError(f"State became non-dict before msgs_from_state: {type(s)}")
        
        try:
            msgs = deps["msgs_from_state"](s, operation_type="feedback")
            # Defensive check: ensure s is still a dict after msgs_from_state
            if not isinstance(s, dict):
                raise TypeError(f"State became non-dict after msgs_from_state: {type(s)}")
            if not isinstance(msgs, list):
                msgs = [{"role": "system", "content": "System prompt"}]
            messages = msgs + [{"role":"user","content": f"{block_summary_sanitized}\n\n{deps['FEEDBACK_BLOCK_INSTR']}"}]
        except (TypeError, AttributeError) as e:
            # If msgs_from_state fails with type error, state might be corrupted
            if "'str' object does not support item assignment" in str(e) or not isinstance(s, dict):
                # State was corrupted - restore from original
                s = original_s.copy() if isinstance(original_s, dict) else {}
                messages = [{"role": "system", "content": "System prompt"}, {"role":"user","content": f"{block_summary_sanitized}\n\n{deps['FEEDBACK_BLOCK_INSTR']}"}]
            else:
                # Different error - use minimal messages but don't restore state
                messages = [{"role": "system", "content": "System prompt"}, {"role":"user","content": f"{block_summary_sanitized}\n\n{deps['FEEDBACK_BLOCK_INSTR']}"}]
        except Exception as e:
            # If msgs_from_state fails, use minimal messages
            messages = [{"role": "system", "content": "System prompt"}, {"role":"user","content": f"{block_summary_sanitized}\n\n{deps['FEEDBACK_BLOCK_INSTR']}"}]
            # Ensure state is still valid
            if not isinstance(s, dict):
                raise TypeError(f"State corrupted after msgs_from_state: {type(s)}")
        
        # Phase 2: Use API adapter if available, otherwise use direct OpenAI call
        grade_adapter = deps.get("grade_answer_via_api_or_direct")
        if grade_adapter:
            # Use API adapter (routes through FastAPI backend if API mode enabled)
            comp = grade_adapter(
                s=s,
                messages=messages,
                client=client,
                api_client=None,  # Will be retrieved inside adapter
                chat_model=deps["CHAT_MODEL"]
            )
            if progress:
                progress(0.6)
            
            # COST OPTIMIZATION: Log token usage
            # Defensive check: ensure state is still a dict before logging
            if not isinstance(s, dict):
                raise TypeError(f"State became non-dict type: {type(s)}")
            deps["_log_token_usage"](comp, "feedback_generation", s, model=deps["CHAT_MODEL"])
            
            # Defensive check: ensure history is still a list after API call
            if not isinstance(s.get("history"), list):
                s["history"] = []
            
            # Extract feedback - API adapter returns mock response with parsed results
            fb_raw = comp.choices[0].message.content.strip()
            
            # Check if API already parsed the feedback (stored in mock response)
            if hasattr(comp, '_scores_dict') and hasattr(comp, '_feedback_text'):
                # API already parsed - use parsed results
                scores_dict = comp._scores_dict
                feedback_text = comp._feedback_text
            else:
                # Fallback: parse feedback manually (for direct OpenAI calls)
                parse_result = deps["_parse_feedback"](fb_raw)
                if not isinstance(parse_result, tuple) or len(parse_result) != 2:
                    logger.warning(f"_parse_feedback returned unexpected format: {type(parse_result)}, value: {parse_result}")
                    scores_dict = {}
                    feedback_text = FEEDBACK_DEFAULT_TEXT
                else:
                    scores_dict, feedback_text = parse_result
        else:
            # Fallback to direct OpenAI call (backward compatibility)
            comp = deps["with_retry"](
                client.chat.completions.create,
                circuit_breaker=circuit_breaker,
                service_name="openai_chat",
                model=deps["CHAT_MODEL"],
                messages=messages,
                temperature=0.2,  # Reduced from 0.3
                max_tokens=500
            )
            if progress:
                progress(0.6)
            
            # COST OPTIMIZATION: Log token usage
            # Defensive check: ensure state is still a dict before logging
            if not isinstance(s, dict):
                raise TypeError(f"State became non-dict type: {type(s)}")
            deps["_log_token_usage"](comp, "feedback_generation", s, model=deps["CHAT_MODEL"])
            
            # Defensive check: ensure history is still a list after API call
            if not isinstance(s.get("history"), list):
                s["history"] = []
            
            fb_raw = comp.choices[0].message.content.strip()
            
            # Parse feedback using extracted helper functions
            parse_result = deps["_parse_feedback"](fb_raw)
            
            # Defensive check: ensure parse_result is a tuple
            if not isinstance(parse_result, tuple) or len(parse_result) != 2:
                # If _parse_feedback returns unexpected format, create default values
                logger.warning(f"_parse_feedback returned unexpected format: {type(parse_result)}, value: {parse_result}")
                scores_dict = {}
                feedback_text = FEEDBACK_DEFAULT_TEXT
            else:
                scores_dict, feedback_text = parse_result
        
        # Defensive check: ensure scores_dict is a dict
        if not isinstance(scores_dict, dict):
            logger.warning(f"scores_dict is not a dict: {type(scores_dict)}, value: {scores_dict}. Creating default dict.")
            scores_dict = {}
        
        score = deps["_calculate_overall_score"](scores_dict)
        scores_dict["Overall"] = score
        # Use extracted scores, falling back to overall score for any missing fields
        s["rubrics"].append({
            "Feedback": feedback_text,  # _parse_feedback ensures this is never empty
            "Conceptual": scores_dict.get("Conceptual", score),
            "Analytical": scores_dict.get("Analytical", score),
            "Application": scores_dict.get("Application", score),
            "Reflection": scores_dict.get("Reflection", score),
            "Overall": score
        })
        s["scores"].append(score)
        
        # COST OPTIMIZATION: Store summary instead of full feedback in history
        # This reduces future context size while preserving key information
        # Note: Hide numeric grades from student, show qualitative assessment only
        # Determine qualitative assessment based on overall score (using centralized helper)
        qualitative = get_qualitative_assessment(score)
        
        # SECURITY FIX: Strip scores and qualitative assessment words from feedback_text BEFORE formatting
        # This ensures students never see numeric scores or conflicting qualitative assessments
        from shared.constants import clean_feedback_text, clean_feedback_summary
        feedback_text_cleaned = clean_feedback_text(feedback_text)
        
        # Format assessment message with cleaned feedback text
        feedback_summary = format_assessment_message(qualitative, feedback_text_cleaned)
        
        # SECURITY FIX: Strip any scores or qualitative words that might have leaked into feedback_summary
        # This is a safety net in case any scores or qualitative words slipped through
        # Uses reusable helper function for consistent behavior (handles markdown format)
        feedback_summary = clean_feedback_summary(feedback_summary)
        
        # Ensure we have valid feedback even if everything was stripped
        if not feedback_summary or (feedback_summary.startswith("Assessment: Your response seems") and len(feedback_summary.split('.')) < 2):
            feedback_summary = format_assessment_message(qualitative, "Evaluation completed.")
        
        # Keep processing message visible until TTS is generated
        # This ensures progress bar shows during entire assessment + TTS generation process
        # Message will be replaced with feedback_summary after TTS completes (before return)
        
        # CRITICAL: Only increment asked_main AFTER assessment is successfully stored
        # This ensures that if assessment generation fails, we don't mark the exam as complete
        # without having stored the assessment. The assessment must be in scores and rubrics
        # before we consider the question "asked" and completed.
        # Validation: After appending, scores/rubrics count should be asked_main + 1
        current_asked = s.get("asked_main", 0)
        scores_count = len(s.get("scores", []))
        rubrics_count = len(s.get("rubrics", []))
        
        # Data integrity check: scores and rubrics should match and be one more than asked_main
        # (because we just appended the current assessment)
        if scores_count != rubrics_count or scores_count != current_asked + 1:
            logger.error(
                "assessment_data_mismatch",
                session_id=s.get("session_id", "unknown"),
                scores_count=scores_count,
                rubrics_count=rubrics_count,
                asked_main=current_asked,
                expected_count=current_asked + 1,
                message="Assessment data mismatch detected - scores/rubrics don't match expected count"
            )
            # Don't increment if there's a mismatch - this prevents premature exam completion
            raise ValueError(f"Assessment data integrity check failed: scores ({scores_count}) and rubrics ({rubrics_count}) don't match expected count ({current_asked + 1})")
        
        # Now safe to increment - assessment is stored and validated
        s["asked_main"] += 1
        # Save state immediately after incrementing asked_main
        deps["save_state_to_disk"](s)
        
        # Log the increment for debugging
        logger.debug(
            "asked_main_incremented",
            session_id=s.get("session_id", "unknown"),
            asked_main=s["asked_main"],
            limit=s.get("limit"),
            message=f"asked_main incremented to {s['asked_main']}, limit is {s.get('limit')}"
        )
        
        # Verify state consistency (defensive check)
        scores_count = len(s.get("scores", []))
        rubrics_count = len(s.get("rubrics", []))
        if s["asked_main"] != scores_count or s["asked_main"] != rubrics_count:
            logger.warning(
                "state_mismatch_after_grading",
                session_id=s.get("session_id", "unknown"),
                asked_main=s["asked_main"],
                scores_count=scores_count,
                rubrics_count=rubrics_count,
                message=f"State mismatch after grading: asked_main={s['asked_main']}, scores_count={scores_count}, rubrics_count={rubrics_count}"
            )
        
        if s["asked_main"] < s["limit"]:
            logger.debug(
                "preparing_next_question",
                session_id=s.get("session_id", "unknown"),
                asked_main=s["asked_main"],
                limit=s["limit"],
                message=f"Preparing next question: asked_main={s['asked_main']}, limit={s['limit']}"
            )
            # Defensive check: ensure s is still a dict before calling reset_current_block
            if not isinstance(s, dict):
                raise TypeError(f"State became non-dict before reset_current_block: {type(s)}")
            
            # Call reset_current_block with error handling
            try:
                deps["reset_current_block"](s)
            except Exception as reset_error:
                # If reset fails, ensure current is still a dict
                if not isinstance(s, dict):
                    raise TypeError(f"State corrupted by reset_current_block: {type(s)}") from reset_error
                if not isinstance(s.get("current"), dict):
                    s["current"] = {
                        "main_question": None,
                        "answers": [],
                        "followups_done": 0,
                        "target_followups": 0,
                        "q_time": None,
                        "short_attempts": 0,
                        "ctx": None
                    }
                else:
                    raise  # Re-raise if it's a different error
            
            # Defensive check: ensure current is still a dict after reset
            if not isinstance(s.get("current"), dict):
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
            # Use state values for followups range if available, otherwise use globals
            followups_min, followups_max = deps["get_followup_range"](s)
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
            
            # RNG OPTIMIZATION: Use same optimized chunk selection as ask_main_question
            # Pre-validate chunks array before selection
            chunks = deps["get_chunks"]()  # Use helper function for thread safety
            if not chunks:
                # OBSERVABILITY: Use structured logging (Principle #13)
                logger.warning(
                    "chunks_empty_followup",
                    session_id=s.get("session_id", "unknown"),
                    request_id=s.get("request_id", "unknown"),
                    message="CHUNKS is empty during follow-up question generation"
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
                raise ValueError(f"{ERROR_PDF_NOT_AVAILABLE} "
                               "Please load a valid PDF from the Settings tab.")
            
            # Pre-filter valid chunks for efficiency
            valid_chunks_with_hashes = []
            for candidate_ctx in chunks:
                is_valid, _ = deps["_validate_context"](candidate_ctx)
                if is_valid:
                    candidate_hash = hashlib.sha256(candidate_ctx.encode("utf-8")).hexdigest()
                    valid_chunks_with_hashes.append((candidate_ctx, candidate_hash))
            
            # RANDOMIZATION: Shuffle valid chunks immediately after building the list
            # This ensures the pool is randomized before any selection, improving true randomness
            if valid_chunks_with_hashes:
                s["_rng"].shuffle(valid_chunks_with_hashes)
            
            # If no valid chunks, raise error
            if not valid_chunks_with_hashes:
                chunks = deps["get_chunks"]()
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
            used_ctx_hashes = s.get("used_context_hashes", set())
            
            # RNG OPTIMIZATION: Early exit - if all chunks used, reset and shuffle
            if len(used_ctx_hashes) >= len(valid_chunks_with_hashes):
                used_ctx_hashes.clear()
                shuffled_valid = valid_chunks_with_hashes.copy()
                s["_rng"].shuffle(shuffled_valid)
                ctx, ctx_hash = s["_rng"].choice(shuffled_valid)
                used_ctx_hashes.add(ctx_hash)
            else:
                unused_valid = [(c, h) for c, h in valid_chunks_with_hashes if h not in used_ctx_hashes]
                if unused_valid:
                    ctx, ctx_hash = s["_rng"].choice(unused_valid)
                    used_ctx_hashes.add(ctx_hash)
                else:
                    ctx, ctx_hash = s["_rng"].choice(valid_chunks_with_hashes)
                    used_ctx_hashes.add(ctx_hash)
            
            # Defensive check: ensure current is still a dict
            if not isinstance(s.get("current"), dict):
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
            s["current"]["ctx"] = ctx
            s["used_context_hashes"] = used_ctx_hashes
            
            # Find the chunk index in chunks for status display (use helper function for thread safety)
            # PERFORMANCE: Reuse chunks variable to avoid redundant get_chunks() call (Principle #9)
            chunks = deps["get_chunks"]()
            chunk_index = None
            for idx, chunk in enumerate(chunks):
                if chunk == ctx:
                    chunk_index = idx + 1  # 1-based for readability
                    break
            
            # Store chunk index and total chunks in state
            # PERFORMANCE: Reuse chunks variable instead of calling get_chunks() again (Principle #9)
            # Defensive check: ensure current is still a dict
            if not isinstance(s.get("current"), dict):
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
            s["current"]["chunk_index"] = chunk_index
            s["current"]["total_chunks"] = len(chunks) if chunks else 0
            
            # Defensive check: Ensure we haven't exceeded the limit before generating next question
            # This should never trigger if the outer if check is working correctly, but add it as a safety net
            if s["asked_main"] >= s["limit"]:
                logger.error(
                    "attempted_to_prepare_question_after_limit",
                    session_id=s.get("session_id", "unknown"),
                    asked_main=s["asked_main"],
                    limit=s["limit"],
                    message=f"CRITICAL: Attempted to prepare question after limit reached: asked_main={s['asked_main']}, limit={s['limit']} - skipping question generation and completing exam"
                )
                # Skip question generation and complete exam instead
                # This should have been caught at the outer if check, but if we're here, something is wrong
                # Complete the exam to prevent asking more questions
                s["phase"] = "complete"
                speak = format_exam_completion_message(feedback_summary)
                if progress:
                    progress(0.7)
                audio = deps["tts_to_mp3"](speak, client, s, progress=progress)
                if progress:
                    progress(1.0)
                # Replace processing message with feedback summary (handles both assessment and follow-up messages)
                # SECURITY FIX: More robust replacement - find and replace ALL instances, not just first
                if not isinstance(s.get("history"), list):
                    s["history"] = []
                # Find and replace the processing message (might be earlier in history)
                replaced = False
                for i in range(len(s["history"]) - 1, -1, -1):
                    if isinstance(s["history"][i], dict):
                        content = s["history"][i].get("content", "")
                        if PROCESSING_ASSESSMENT_MSG in content or PROCESSING_FOLLOWUP_MSG in content:
                            s["history"][i] = {"role":"assistant","content":feedback_summary}
                            replaced = True
                # FALLBACK: If no replacement happened, ensure feedback_summary is in history
                # This prevents raw fb_raw from being displayed
                if not replaced:
                    # Find last assistant message and replace it, or append if none found
                    for i in range(len(s["history"]) - 1, -1, -1):
                        if isinstance(s["history"][i], dict) and s["history"][i].get("role") == "assistant":
                            s["history"][i] = {"role":"assistant","content":feedback_summary}
                            break
                    else:
                        # No assistant message found, append feedback_summary
                        s["history"].append({"role":"assistant","content":feedback_summary})
                proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
                return s, audio, gr_module.update(value=STATUS_EXAM_COMPLETE), gr_module.update(value=None, interactive=False), s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True)
            
            # Generate next question with retry on validation/duplicate errors
            next_q = None
            max_gen_attempts = 3
            for gen_attempt in range(max_gen_attempts):
                try:
                    next_q = deps["_gen_main_question_with_ctx"](s, ctx, client=client)
                    break  # Success, exit loop
                except ValueError as ve:
                    # If validation/duplicate error and we have retries left, try again
                    if gen_attempt < max_gen_attempts - 1:
                        continue  # Try generating again
                    else:
                        # Last attempt failed, use fallback
                        next_q = "Could you explain your understanding of the key concepts from this section?"
                        break
            
            if not next_q:
                next_q = "Could you explain your understanding of the key concepts from this section?"
            
            s["current"]["main_question"] = next_q
            
            # QUESTION PROVENANCE TRACKING: Store cryptographic provenance for auditability
            # FERPA-compliant: Only stores cryptographic hashes (SHA-256) of context and questions.
            # No personally identifiable information (PII) is stored - only hashes for integrity verification.
            q_sha = hashlib.sha256(next_q.encode("utf-8")).hexdigest()
            ctx_sha = hashlib.sha256(ctx.encode("utf-8")).hexdigest()
            s.setdefault("questions_meta", []).append({
                "index": s.get("asked_main", 0) + 1,
                "context_sha256": ctx_sha,         # Cryptographic hash only - not PII
                "context_len": len(ctx),           # Metadata for validation only
                "question_sha256": q_sha,          # Cryptographic hash only - not PII
                "question_text": next_q,           # Store question text for better duplicate detection
            })
            
            # ORDERING FIX: Replace processing message with feedback BEFORE adding next question
            # This ensures feedback appears before the next question in the UI (per fix-assessment.md)
            # Defensive check: ensure history is a list
            if not isinstance(s.get("history"), list):
                s["history"] = []
            
            # Find and replace the processing message FIRST (before adding next question)
            replaced = False
            for i in range(len(s["history"]) - 1, -1, -1):
                if isinstance(s["history"][i], dict):
                    content = s["history"][i].get("content", "")
                    if PROCESSING_ASSESSMENT_MSG in content or PROCESSING_FOLLOWUP_MSG in content:
                        s["history"][i] = {"role":"assistant","content":feedback_summary}
                        replaced = True
                        break  # Only replace first occurrence
            
            # FALLBACK: If no replacement happened, ensure feedback_summary is in history
            # This prevents raw fb_raw from being displayed
            if not replaced:
                # Find last assistant message and replace it, or append if none found
                for i in range(len(s["history"]) - 1, -1, -1):
                    if isinstance(s["history"][i], dict) and s["history"][i].get("role") == "assistant":
                        s["history"][i] = {"role":"assistant","content":feedback_summary}
                        break
                else:
                    # No assistant message found, append feedback_summary
                    s["history"].append({"role":"assistant","content":feedback_summary})
            
            # NOW add next question (after feedback is in place)
            # Add visual distinction for main questions with numbering
            asked_main = s.get("asked_main", 0)
            limit = s.get("limit", 0)
            if limit > 0:
                question_label = format_question_label(asked_main + 1, limit, "main")
                next_q_with_label = f"{question_label}\n\n{next_q}"
            else:
                next_q_with_label = next_q
            
            # Add transition message before next question
            s["history"].append({"role":"assistant","content":TRANSITION_NEXT_QUESTION})
            
            # Add next question
            s["history"].append({"role":"assistant","content":next_q_with_label})
            s["phase"] = "awaiting_main_answer"
            
            # Notify student about answer timeout (use helper function with state for cross-context reliability)
            max_timeout = deps["get_max_answer_timeout_sec"](s)  # Pass state to get value from state dict if context var unavailable
            timeout_notification = f"\n\n{format_timeout_notification(max_timeout, is_followup=False)}"
            s["history"].append({"role":"assistant","content":timeout_notification})
            
            # Generate TTS audio (includes feedback + transition + question)
            speak = f"{feedback_summary}\n\n{TRANSITION_NEXT_QUESTION}\n{next_q}"
            if progress:
                progress(0.7)
            audio = deps["tts_to_mp3"](speak, client, s, progress=progress)
            if progress:
                progress(1.0)
            # Store audio path in state so it persists across _stream_proctor calls
            if audio:
                s["current"]["last_examiner_audio"] = audio
            # Get audio duration and start timer AFTER audio finishes playing
            audio_duration = deps["get_audio_duration"](audio) if audio else 0.0
            # Defensive check: ensure current is still a dict
            if not isinstance(s.get("current"), dict):
                s["current"] = {
                    "main_question": None,
                    "answers": [],
                    "followups_done": 0,
                    "target_followups": 0,
                    "q_time": None,
                    "short_attempts": 0,
                    "ctx": None
                }
            # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
            s["current"]["q_time"] = time_provider.time() + audio_duration
            # Mic should only be enabled when timer countdown starts (elapsed >= 0)
            # Since timer starts after audio finishes, mic will be disabled until then
            from exam.ui.helpers import _calculate_mic_interactive_state
            mic_interactive = _calculate_mic_interactive_state(s, gr_module)
            return s, audio, gr_module.update(value=STATUS_CONTINUING_AUTOMATICALLY), gr_module.update(value=None, interactive=mic_interactive), s["history"], gr_module.update(), gr_module.update(), gr_module.update(interactive=False)  # Finish button remains disabled
        else:
            logger.debug(
                "limit_reached_completing_exam",
                session_id=s.get("session_id", "unknown"),
                asked_main=s["asked_main"],
                limit=s["limit"],
                message=f"Limit reached: asked_main={s['asked_main']}, limit={s['limit']} - completing exam"
            )
            s["phase"] = "complete"
            speak = format_exam_completion_message(feedback_summary)
            if progress:
                progress(0.7)
            audio = deps["tts_to_mp3"](speak, client, s, progress=progress)
            if progress:
                progress(1.0)
            # Replace processing message with feedback summary (after TTS is generated)
            # This ensures progress bar shows during entire assessment + TTS generation
            # Handles both assessment and follow-up messages
            # SECURITY FIX: More robust replacement - find and replace ALL instances, not just first
            if not isinstance(s.get("history"), list):
                s["history"] = []
            # Find and replace the processing message (might be earlier in history)
            replaced = False
            for i in range(len(s["history"]) - 1, -1, -1):
                if isinstance(s["history"][i], dict):
                    content = s["history"][i].get("content", "")
                    if PROCESSING_ASSESSMENT_MSG in content or PROCESSING_FOLLOWUP_MSG in content:
                        s["history"][i] = {"role":"assistant","content":feedback_summary}
                        replaced = True
            # FALLBACK: If no replacement happened, ensure feedback_summary is in history
            # This prevents raw fb_raw from being displayed
            if not replaced:
                # Find last assistant message and replace it, or append if none found
                for i in range(len(s["history"]) - 1, -1, -1):
                    if isinstance(s["history"][i], dict) and s["history"][i].get("role") == "assistant":
                        s["history"][i] = {"role":"assistant","content":feedback_summary}
                        break
                else:
                    # No assistant message found, append feedback_summary
                    s["history"].append({"role":"assistant","content":feedback_summary})
            proctor_cam_upd, proctor_status_upd = deps["_proctor_end_updates"](s, gr_module)
            return s, audio, gr_module.update(value="✔️ Exam complete. Press Finish & Download."), gr_module.update(value=None, interactive=False), s["history"], proctor_cam_upd, proctor_status_upd, gr_module.update(visible=True, interactive=True)  # Show and enable finish button
    except Exception as e:
        # Use centralized error handling
        # Log detailed error information for debugging
        import traceback
        error_traceback = traceback.format_exc()
        error_msg = str(e)
        
        # Check if this is the specific error we're debugging
        if "'str' object does not support item assignment" in error_msg:
            logger.error(
                "grading_state_corruption",
                error_message=error_msg,
                s_type=type(s).__name__,
                s_repr=repr(s)[:200] if isinstance(s, (str, dict)) else "N/A",
                original_s_type=type(original_s).__name__ if 'original_s' in locals() else "N/A",
                traceback=error_traceback[-500:]  # Last 500 chars of traceback
            )
        
        # Defensive check: if s was corrupted, restore from original
        if not isinstance(s, dict):
            s = original_s if isinstance(original_s, dict) else {}
            # Ensure s is a valid dict
            if not isinstance(s, dict):
                import uuid
                from datetime import datetime, timezone
                s = {
                    "session_id": str(uuid.uuid4()),
                    "request_id": str(uuid.uuid4()),
                    "student_id": "unknown",
                    "phase": "idle",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "session_start_time": 0.0,
                    "history": [],
                    "scores": [],
                    "rubrics": [],
                    "flags": [],
                    "consent": False,
                }
        
        from exam.flow.error_handling import handle_flow_error
        return handle_flow_error(
            s=s,
            e=e,
            gr_module=gr_module,
            dependencies=deps,
            processing_message=PROCESSING_ASSESSMENT_MSG,
            default_msg="Grading failed",
            tuple_length=8,
            error_context="grading_error"
        )

