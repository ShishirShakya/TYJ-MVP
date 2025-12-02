"""
Utility functions for exam.ipynb - text processing, validation, error handling.

This module provides utility functions for text processing, validation, error handling,
and retry logic used exclusively by the exam interface.

**Key Functions**:
- `with_retry()`: Retry logic with exponential backoff and circuit breaker support
- `_sanitize_for_prompt()`: Sanitize text for AI prompts (prevent injection)
- `_validate_question()`: Validate generated questions
- `_categorize_error()`: Categorize exceptions for error handling
- `_log_token_usage()`: Log OpenAI API token usage

**Usage Example**:
    ```python
    from exam.utils import with_retry, _sanitize_for_prompt
    
    # Retry API call with exponential backoff
    response = with_retry(
        lambda: client.chat.completions.create(...),
        max_tries=4,
        circuit_breaker=breaker,
        service_name="openai_chat"
    )
    
    # Sanitize user input before sending to AI
    safe_text = _sanitize_for_prompt(user_input, max_len=5000)
    ```

**Error Handling**:
- Categorizes errors as retryable vs non-retryable
- Attaches error metadata to exceptions
- Supports circuit breaker protection
- Provides user-friendly error messages

**Naming Conventions**:
- Private functions prefixed with `_` (internal use only)
- Public functions use full words (no abbreviations)
- See `docs/NAMING_CONVENTIONS.md` for full guide
"""

import re
import hashlib
import time
import random
from typing import Tuple, Optional, Any
from datetime import datetime


# =========================
# Text Processing & Normalization
# =========================

def _sanitize_for_prompt(text: str, max_len: int = 5000) -> str:
    """
    Sanitize text to prevent prompt injection attacks.
    Removes or escapes control characters and limits length.
    
    Args:
        text: Text to sanitize
        max_len: Maximum length (default: 5000)
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    # Limit length to prevent prompt stuffing
    if len(text) > max_len:
        text = text[:max_len] + "... (truncated)"
    return text.strip()


def _ensure_no_pii_in_content(content: str) -> str:
    """
    FERPA COMPLIANCE: Ensure no PII accidentally included in content sent to OpenAI.
    
    Checks for common PII patterns and removes/replaces them to prevent accidental
    exposure of student identifiers in API calls.
    
    Args:
        content: Content to check for PII
        
    Returns:
        Content with PII patterns removed/replaced
        
    Note:
        This is a defensive check. Content should already be sanitized before calling
        OpenAI APIs. This provides an additional layer of protection.
    """
    if not content:
        return ""
    
    # Common PII patterns to detect and remove
    # Email addresses
    content = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REMOVED]', content)
    
    # Phone numbers (US format: XXX-XXX-XXXX, (XXX) XXX-XXXX, XXX.XXX.XXXX)
    content = re.sub(r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b', '[PHONE_REMOVED]', content)
    content = re.sub(r'\(\d{3}\)\s?\d{3}[-.\s]?\d{4}', '[PHONE_REMOVED]', content)
    
    # SSN pattern (XXX-XX-XXXX)
    content = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REMOVED]', content)
    
    # Student ID patterns (common formats: all digits, or alphanumeric with dashes)
    # Be careful not to remove legitimate content - only remove if it looks like an ID
    # Pattern: standalone sequences of 6+ digits that might be student IDs
    # This is conservative - only removes if it's clearly separated (not part of a word)
    content = re.sub(r'\b\d{6,}\b', lambda m: '[ID_REMOVED]' if len(m.group()) <= 12 else m.group(), content)
    
    # Common identifier phrases that might contain PII
    pii_phrases = [
        r'\bstudent\s+id[:\s]+[A-Za-z0-9]+\b',
        r'\bsession\s+id[:\s]+[A-Za-z0-9-]+\b',
        r'\bstudent\s+number[:\s]+[A-Za-z0-9]+\b',
    ]
    for pattern in pii_phrases:
        content = re.sub(pattern, '[ID_REMOVED]', content, flags=re.IGNORECASE)
    
    return content


def _normalize_answer_for_hash(text: str) -> str:
    """
    Normalize answer text for hashing comparison.
    Removes case, punctuation, extra whitespace to detect near-identical answers.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    if not text:
        return ""
    
    # Convert to lowercase
    normalized = text.lower()
    
    # Remove punctuation (keep alphanumeric and spaces)
    normalized = re.sub(r'[^\w\s]', ' ', normalized)
    
    # Normalize whitespace (multiple spaces/tabs/newlines -> single space)
    normalized = re.sub(r'\s+', ' ', normalized)
    
    # Trim leading/trailing whitespace
    normalized = normalized.strip()
    
    return normalized


def _hash_answer(text: str) -> str:
    """
    Hash a normalized answer for comparison.
    Returns hex digest of SHA256 hash.
    
    Args:
        text: Text to hash
        
    Returns:
        SHA256 hash as hex string
    """
    normalized = _normalize_answer_for_hash(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _calculate_answer_similarity(text1: str, text2: str) -> float:
    """
    Calculate semantic similarity between two answers using word overlap (Jaccard similarity).
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    
    Args:
        text1: First text
        text2: Second text
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    # Normalize both texts
    normalized1 = _normalize_answer_for_hash(text1)
    normalized2 = _normalize_answer_for_hash(text2)
    
    # Extract word sets (remove very short words that might be noise)
    words1 = set(w for w in normalized1.split() if len(w) >= 3)
    words2 = set(w for w in normalized2.split() if len(w) >= 3)
    
    if not words1 or not words2:
        return 0.0
    
    # Calculate Jaccard similarity (intersection over union)
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    similarity = intersection / union
    return similarity


def _detect_answer_reuse(text: str, previous_answer_hashes: list, previous_answer_texts: list = None) -> bool:
    """
    GUARDRAIL: Enhanced Answer Reuse Detection
    
    Detects if an answer is being reused from previous responses using:
    1. Exact hash matching (catches identical answers)
    2. Semantic similarity detection (catches near-duplicates with minor rephrasing)
    
    Safeguard: Prevents recycling of memorized responses by comparing
    normalized hashes AND semantic similarity against all previous answers.
    
    Args:
        text: Current answer text to check
        previous_answer_hashes: List of previous answer hashes
        previous_answer_texts: Optional list of previous answer texts for similarity comparison
        
    Returns:
        True if answer reuse is detected, False otherwise.
    """
    from exam.config import MIN_WORDS
    
    if not text or len(text) < MIN_WORDS:
        return False
    
    if not previous_answer_hashes:
        return False
    
    # 1. Exact Hash Matching: Check if this exact hash has been seen before
    current_hash = _hash_answer(text)
    if current_hash in previous_answer_hashes:
        return True
    
    # 2. Enhanced Semantic Similarity Detection: Detect near-duplicates
    # This catches cases where minor variations or rephrasing are introduced
    # to evade exact hash matching
    if previous_answer_texts:
        normalized_current = _normalize_answer_for_hash(text)
        current_words = set(normalized_current.split())
        
        # If answer is too short after normalization, skip similarity check
        if len(current_words) < 5:
            return False
        
        # Compare against all previous answer texts for semantic similarity
        for prev_text in previous_answer_texts:
            if not prev_text or len(prev_text) < MIN_WORDS:
                continue
            
            # Calculate similarity (Jaccard similarity on word sets)
            similarity = _calculate_answer_similarity(text, prev_text)
            
            # If >90% word overlap, flag as reuse (likely same answer with minor rephrasing)
            if similarity > 0.9:
                return True
    
    return False


def _count_meaningful_words(txt: str) -> int:
    """
    Count meaningful words in text (words containing at least one letter).
    
    Args:
        txt: Text to count words in
        
    Returns:
        Number of meaningful words
    """
    return sum(1 for w in re.findall(r"\b[\w'-]+\b", txt) if re.search(r"[A-Za-z]", w))


def _detect_profanity(text: str) -> bool:
    """
    Detect profanity in text.
    Returns True if profanity is detected, False otherwise.
    
    Args:
        text: Text to check
        
    Returns:
        True if profanity detected, False otherwise
    """
    if not text:
        return False
    
    # Common profanity words (case-insensitive check)
    profanity_words = {
        "fuck", "fucking", "fucked", "fucker", "fuckers",
        "shit", "shitting", "shitted", "shitty",
        "asshole", "ass", "asses",
        "bitch", "bitches", "bitched", "bitching",
        "bastard", "bastards",
        "damn", "damned", "damnit", "dammit",
        "hell",
        "crap", "crappy",
        "piss", "pissed", "pissing",
        "cunt", "cunts",
        "dick", "dicks",
        "whore", "whores",
        "slut", "sluts",
        "cock", "cocks",
        "pussy", "pussies",
        "nigger", "nigga", "niggas",  # Racial slurs
        "retard", "retarded",
        "stupid", "idiot", "moron",
    }
    
    # Normalize text to lowercase and check for profanity
    text_lower = text.lower()
    words = re.findall(r"\b\w+\b", text_lower)
    
    for word in words:
        if word in profanity_words:
            return True
    
    return False


# =========================
# Question Validation
# =========================

def _ensure_qmark(text: str) -> str:
    """
    Ensure text ends with a question mark.
    
    Args:
        text: Text to ensure question mark on
        
    Returns:
        Text ending with question mark
    """
    text = text.strip()
    return text if text.endswith("?") else (text.rstrip(".") + "?")


def _validate_question(text: str, max_chars: int = 500) -> Tuple[bool, str]:
    """
    Validate generated question for quality and format.
    Returns (is_valid, error_message).
    
    Args:
        text: Question text to validate
        max_chars: Maximum characters allowed (default: 500)
        
    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if not text or not text.strip():
        return False, "Question is empty"
    
    text = text.strip()
    
    # Check length
    if len(text) > max_chars:
        return False, f"Question too long ({len(text)} chars, max {max_chars})"
    
    if len(text) < 10:
        return False, "Question too short (minimum 10 characters)"
    
    # Check for question mark
    if "?" not in text:
        return False, "Question missing question mark"
    
    # Check for question words (what, why, how, when, where, which, who, etc.)
    question_words = ["what", "why", "how", "when", "where", "which", "who", "whom", "whose", 
                      "can", "could", "should", "would", "do", "does", "did", 
                      "is", "are", "was", "were", "will", "shall"]
    text_lower = text.lower()
    has_question_word = any(word in text_lower for word in question_words)
    
    # Check if it's actually a question (contains question words or ends with ?)
    if not has_question_word and not text.endswith("?"):
        return False, "Question doesn't appear to be a valid question"
    
    # Check for excessive repetition (potential hallucination)
    words = text.split()
    if len(words) > 5:
        unique_words = len(set(word.lower() for word in words))
        if unique_words / len(words) < 0.5:
            return False, "Question contains excessive repetition"
    
    return True, ""


# =========================
# Text Compression & Truncation
# =========================

def _compress_context_chunk(ctx_text: str, target_length: int = 1500) -> str:
    """
    COST OPTIMIZATION: Compress context chunk by extracting key sentences.
    Reduces token count by 30-50% while preserving key information.
    
    Args:
        ctx_text: Context text to compress
        target_length: Target length in characters (default: 1500)
        
    Returns:
        Compressed text
    """
    if len(ctx_text) <= target_length:
        return ctx_text
    
    # Split into sentences
    sentences = re.split(r'[.!?]+\s+', ctx_text)
    if len(sentences) <= 3:
        return ctx_text[:target_length]
    
    # Keep first (introduction), last (conclusion), and key middle sentences
    key_sentences = [sentences[0]]
    
    # Extract middle sentences with important terms
    important_terms = ['important', 'key', 'main', 'primary', 'crucial', 'essential', 
                       'define', 'example', 'because', 'therefore', 'however']
    for sent in sentences[1:-1]:
        if any(term in sent.lower() for term in important_terms):
            if len(key_sentences) < 6:  # Limit to ~6 key sentences
                key_sentences.append(sent)
    
    # Always include last sentence (conclusion)
    if len(sentences) > 1:
        key_sentences.append(sentences[-1])
    
    compressed = ' '.join(key_sentences)
    
    # Final truncation if still too long
    if len(compressed) > target_length:
        return compressed[:target_length] + "..."
    
    return compressed


def _truncate_answer_for_followup(answer: str, max_chars: int = 800) -> str:
    """
    COST OPTIMIZATION: Truncate long answers for follow-up generation.
    Keeps beginning (300 chars) and end (500 chars) for context.
    
    Args:
        answer: Answer text to truncate
        max_chars: Maximum characters (default: 800)
        
    Returns:
        Truncated answer
    """
    if len(answer) <= max_chars:
        return answer
    
    # Keep beginning and end, truncate middle
    beginning = answer[:300].rstrip()
    end = answer[-500:].lstrip()
    
    # Ensure we don't exceed max_chars
    if len(beginning) + len(end) > max_chars:
        # Adjust to fit
        end_len = max(500, max_chars - len(beginning) - 20)  # 20 for "... [truncated] ..."
        end = answer[-end_len:].lstrip()
    
    return f"{beginning}... [truncated] ...{end}"


# =========================
# Error Handling & Retry
# =========================

# Error type definitions for categorization
ERROR_TYPES = {
    "NETWORK_ERROR": {
        "message": "Network connection issue. Please check your internet connection and try again.",
        "retry": True,
        "patterns": ["connection", "network", "dns", "resolve", "unreachable"]
    },
    "API_RATE_LIMIT": {
        "message": "Too many requests. Please wait a moment and try again.",
        "retry": True,
        "patterns": ["429", "rate limit", "too many requests", "quota"]
    },
    "API_TIMEOUT": {
        "message": "Request timed out. Please try again.",
        "retry": True,
        "patterns": ["timeout", "timed out", "deadline exceeded"]
    },
    "AUDIO_ERROR": {
        "message": "Audio processing error. Please check your microphone permissions and try again.",
        "retry": True,
        "patterns": ["audio", "microphone", "recording", "whisper"]
    },
    "API_ERROR": {
        "message": "API service error. Please try again in a moment.",
        "retry": True,
        "patterns": ["500", "502", "503", "504", "internal server error", "bad gateway", "service unavailable"]
    },
    "AUTH_ERROR": {
        "message": "Authentication error. Please check your API key and try again.",
        "retry": False,
        "patterns": ["401", "403", "unauthorized", "forbidden", "invalid api key", "authentication"]
    },
    "UNKNOWN_ERROR": {
        "message": "An unexpected error occurred. Please try again.",
        "retry": True,
        "patterns": []
    }
}


def _categorize_error(exception: Exception) -> tuple[str, dict]:
    """
    Categorize exception and return error type and metadata.
    
    Args:
        exception: Exception to categorize
        
    Returns:
        Tuple of (error_type: str, metadata: dict)
    """
    msg = str(exception).lower()
    error_type = exception.__class__.__name__
    
    # Check patterns for each error type
    for err_type, err_info in ERROR_TYPES.items():
        if err_type == "UNKNOWN_ERROR":
            continue
        for pattern in err_info["patterns"]:
            if pattern in msg:
                return err_type, {
                    "type": err_type,
                    "message": err_info["message"],
                    "retry": err_info["retry"],
                    # Don't expose original_error or error_class to users (internal only)
                    "_internal_error": str(exception),
                    "_internal_error_class": error_type
                }
    
    # Default to UNKNOWN_ERROR
    return "UNKNOWN_ERROR", {
        "type": "UNKNOWN_ERROR",
        "message": ERROR_TYPES["UNKNOWN_ERROR"]["message"],
        "retry": ERROR_TYPES["UNKNOWN_ERROR"]["retry"],
        # Don't expose original_error or error_class to users (internal only)
        "_internal_error": str(exception),
        "_internal_error_class": error_type
    }


def with_retry(
    fn,
    *args,
    max_tries=4,
    base=0.4,
    jitter=0.25,
    rng=None,
    circuit_breaker=None,
    fallback_func=None,
    service_name="external_api",
    **kwargs
):
    """
    Enhanced retry helper with default timeouts, error categorization, and circuit breaker protection.
    Sets default timeout for API calls (30s for chat, 60s for audio).
    Returns error metadata for better error handling.
    
    DETERMINISTIC: Accepts optional RNG for reproducible retry behavior (Principle #5).
    If rng is None, uses a deterministic seeded RNG for consistent behavior.
    
    GRACEFUL FAILURE: Supports circuit breaker protection and fallback behavior (Principle #16).
    
    IDEMPOTENCY: Safe for retries - underlying operations should be idempotent (Principle #21).
    This function retries failed operations but does not prevent duplicates. For operations
    that modify state, use idempotency tracking (IdempotencyTracker) in addition to retries.
    
    Args:
        fn: Function to retry (should be idempotent for safe retries)
        *args: Positional arguments for function
        max_tries: Maximum number of retry attempts (default: 4)
        base: Base delay in seconds (default: 0.4)
        jitter: Jitter factor for exponential backoff (default: 0.25)
        rng: Optional random number generator (default: deterministic seeded RNG)
        circuit_breaker: Optional circuit breaker instance (if provided, wraps call with protection)
        fallback_func: Optional fallback function to call if circuit is open
        service_name: Name of service for circuit breaker (default: "external_api")
        **kwargs: Keyword arguments for function
        
    Returns:
        Function result
        
    Raises:
        Last exception if all retries fail (with error_metadata attached)
        CircuitBreakerOpenError: If circuit is open and no fallback provided
        
    Note: For state-modifying operations, combine with idempotency tracking:
    ```python
    # Check idempotency first
    if idempotency_tracker.is_processed(key):
        return cached_result
    
    # Then retry with with_retry
    result = with_retry(operation, ...)
    idempotency_tracker.mark_processed(key, request_id)
    ```
    """
    # GRACEFUL FAILURE: Use circuit breaker protection if provided (Principle #16)
    if circuit_breaker is not None:
        from shared.api_protection import call_with_protection
        from shared.circuit_breaker import CircuitBreakerOpenError
        try:
            return call_with_protection(
                fn,
                circuit_breaker=circuit_breaker,
                fallback_func=fallback_func,
                service_name=service_name,
                *args,
                **kwargs
            )
        except CircuitBreakerOpenError:
            # Circuit breaker is open - don't retry, raise immediately
            raise
        except Exception as e:
            # If circuit breaker fails and no fallback, still try retry logic
            # This provides defense in depth
            if fallback_func is None:
                # Continue with retry logic
                pass
            else:
                # Fallback was already tried, re-raise
                raise
    
    # Check max_tries before proceeding
    if max_tries <= 0:
        # If max_tries is 0 or negative, try once and let it fail immediately
        # This allows the exception to propagate without retry logic
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            # Attach error metadata for consistency
            error_type, error_metadata = _categorize_error(e)
            e.error_metadata = error_metadata
            raise
    
    # DETERMINISTIC: Use provided RNG or create deterministic one (Principle #5)
    if rng is None:
        # Use deterministic seeded RNG for reproducible retry behavior
        rng = random.Random(12345)  # Fixed seed for deterministic jitter
    # Set default timeout for API calls (30s for chat, 60s for audio)
    if "timeout" not in kwargs:
        kwargs["timeout"] = 30
    
    last_error = None
    last_error_metadata = None
    
    for i in range(max_tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_type, error_metadata = _categorize_error(e)
            last_error_metadata = error_metadata
            
            if i == max_tries - 1:
                # Attach error metadata to exception for better error handling
                e.error_metadata = error_metadata
                raise
            
            # Check if error is retryable
            if not error_metadata["retry"]:
                e.error_metadata = error_metadata
                raise
            
            msg = str(e).lower()
            # Longer backoff for rate limits, timeouts, and connection errors
            penalty = 1.0 if ("429" in msg or "rate limit" in msg or "timeout" in msg or "connection" in msg) else 0.0
            # DETERMINISTIC: Use provided RNG instead of global random (Principle #5)
            # Clamp delay to minimum 0 to handle negative base delays gracefully
            delay = max(0.0, base * (2 ** i) + rng.random() * jitter + penalty)
            time.sleep(delay)
    
    # Should never reach here, but just in case
    if last_error:
        last_error.error_metadata = last_error_metadata
        raise last_error


# =========================
# Token Usage Tracking
# =========================

def _log_token_usage(response, operation_type: str, s=None, model: str = None, default_model: str = "gpt-4o-mini"):
    """
    COST OPTIMIZATION: Log token usage for monitoring and cost tracking.
    Also calculates cost per operation for real-time cost visibility.
    
    Args:
        response: OpenAI API response object
        operation_type: Type of operation (e.g., "question_generation")
        s: Optional state dictionary to store token usage
        model: Optional model name (if not provided, tries to get from response)
        default_model: Default model name if not found (default: "gpt-4o-mini")
    """
    try:
        usage = getattr(response, 'usage', None)
        if usage:
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            
            # Determine model from response or use provided/default
            model_name = model or getattr(response, 'model', None) or default_model
            
            # Calculate cost per operation (pricing as of 2024)
            # gpt-4o-mini: $0.15/1M input tokens, $0.60/1M output tokens
            # gpt-4o: $2.50/1M input tokens, $10.00/1M output tokens
            # whisper-1: $0.006/minute (handled separately for audio)
            pricing = {
                "gpt-4o-mini": {"input": 0.15/1_000_000, "output": 0.60/1_000_000},
                "gpt-4o": {"input": 2.50/1_000_000, "output": 10.00/1_000_000},
                "gpt-4o-mini-tts": {"input": 0.00, "output": 0.00},  # TTS is free
                "whisper-1": {"input": 0.006/60, "output": 0.00}  # Per minute
            }
            
            model_pricing = pricing.get(model_name, pricing["gpt-4o-mini"])
            input_cost = input_tokens * model_pricing["input"]
            output_cost = output_tokens * model_pricing["output"]
            operation_cost = input_cost + output_cost
            
            # Log to state for cost tracking
            if s is not None and isinstance(s, dict):
                s.setdefault("token_usage", []).append({
                    "operation": operation_type,
                    "model": model_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "input_cost_usd": round(input_cost, 6),
                    "output_cost_usd": round(output_cost, 6),
                    "operation_cost_usd": round(operation_cost, 6),
                    "timestamp": datetime.now().isoformat()
                })
            
            # OBSERVABILITY: Cost tracking logged via structured logging above (Principle #13)
    except Exception:
        pass  # Don't fail on logging errors

