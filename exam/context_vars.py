"""
Context variable utilities for exam.ipynb - thread-safe configuration management.

This module provides thread-safe context variables for storing exam configuration
and state across concurrent requests. Context variables are Python's built-in
mechanism for thread-local storage.

**Naming Convention**:
- Variables ending with `_ctx` are context variables (ctx = context)
- Example: `chunks_ctx` = context variable for PDF chunks
- Example: `course_id_ctx` = context variable for course ID

**Key Functions**:
- `get_course_id()`: Get course ID from context (with fallback to env var)
- `get_exam_id()`: Get exam ID from context (with fallback to env var)
- `get_chunks()`: Get PDF chunks from context
- `get_textbook_sha256()`: Get textbook hash from context

**Usage Example**:
    ```python
    from exam.context_vars import (
        course_id_ctx, exam_id_ctx, chunks_ctx,
        get_course_id, get_exam_id, get_chunks
    )
    
    # Set context variables (typically done in notebook)
    course_id_ctx.set("CS101")
    exam_id_ctx.set("MIDTERM_2024")
    chunks_ctx.set(["Chunk 1 text...", "Chunk 2 text..."])
    
    # Get context variables (thread-safe)
    course_id = get_course_id()  # Returns "CS101"
    exam_id = get_exam_id()      # Returns "MIDTERM_2024"
    chunks = get_chunks()        # Returns list of chunks
    ```

**Why Context Variables?**:
- Thread-safe: Each thread has its own context
- No global state pollution
- Works with async/concurrent code
- Fallback to environment variables if not set

**Timeout Configuration Naming Convention (Single Source of Truth)**:
- **External/URL Layer**: `time_per_question` - What professor provides in URL
  - Used in: URL encoding/decoding, professor interface
  - Source: Professor's exam configuration URL
- **Internal/Storage Layer**: `max_answer_timeout_sec` - Internal representation
  - Context variable: `max_answer_timeout_sec_ctx` (SSOT - Single Source of Truth)
  - Getter function: `get_max_answer_timeout_sec()` - Use this to access the value
  - Config constant: `MAX_ANSWER_TIMEOUT_SEC_DEFAULT` - Default fallback (60 seconds)
- **Local Variables**: `max_timeout` - Acceptable short name in function scope
  - Used within functions for brevity
  - Always retrieved via `get_max_answer_timeout_sec()`

**Data Flow**:
```
Professor URL → time_per_question (external)
     ↓
URL Parser → converts to max_answer_timeout_sec_ctx (internal storage - SSOT)
     ↓
Context Variable → max_answer_timeout_sec_ctx (SSOT)
     ↓
Getter Function → get_max_answer_timeout_sec() (accessor - use this!)
     ↓
Code Usage → max_timeout (local variable, acceptable)
```

**Abbreviations**:
- **ctx**: Context (context variable suffix)
- **sha256**: SHA-256 hash algorithm
- **SSOT**: Single Source of Truth
"""

import os
from typing import List, Optional, Dict, Any
from contextvars import ContextVar

from shared.constants import FALLBACK_NO_TEXTBOOK_CONTENT

# Context variables for thread-safe state management
course_id_ctx: ContextVar[str] = ContextVar('course_id', default="UNKNOWN")
exam_id_ctx: ContextVar[str] = ContextVar('exam_id', default="UNKNOWN")
n_questions_ctx: ContextVar[int] = ContextVar('n_questions', default=1)
followups_min_ctx: ContextVar[int] = ContextVar('followups_min', default=0)
followups_max_ctx: ContextVar[int] = ContextVar('followups_max', default=1)
passphrase_ctx: ContextVar[str] = ContextVar('passphrase', default="")
chunks_ctx: ContextVar[List[str]] = ContextVar('chunks', default=[])
textbook_sha256_ctx: ContextVar[str] = ContextVar('textbook_sha256', default="")
# NOTE: No default value - must be explicitly set from URL to avoid silently using wrong timeout
# Using None as sentinel to detect if value was actually set
max_answer_timeout_sec_ctx: ContextVar[Optional[int]] = ContextVar('max_answer_timeout_sec', default=None)


def get_course_id() -> str:
    """
    Get course_id from context variable, fallback to environment variable.
    
    Note: This function requires context variables to be set. If not set,
    it will fall back to the VIVA_COURSE_ID environment variable.
    """
    try:
        return course_id_ctx.get() or os.getenv("VIVA_COURSE_ID", "UNKNOWN")
    except LookupError:
        return os.getenv("VIVA_COURSE_ID", "UNKNOWN")


def get_exam_id() -> str:
    """
    Get exam_id from context variable, fallback to environment variable.
    
    Note: This function requires context variables to be set. If not set,
    it will fall back to the VIVA_EXAM_ID environment variable.
    """
    try:
        return exam_id_ctx.get() or os.getenv("VIVA_EXAM_ID", "UNKNOWN")
    except LookupError:
        return os.getenv("VIVA_EXAM_ID", "UNKNOWN")


def get_n_questions() -> int:
    """
    Get n_questions from context variable, fallback to default.
    
    Returns:
        Number of questions from context variable, or default of 1
    """
    try:
        return n_questions_ctx.get()
    except LookupError:
        return 1


def get_followups_min() -> int:
    """
    Get followups_min from context variable, fallback to default.
    
    Returns:
        Minimum followups from context variable, or default of 0
    """
    try:
        return followups_min_ctx.get()
    except LookupError:
        return 0


def get_followups_max() -> int:
    """
    Get followups_max from context variable, fallback to default.
    
    Returns:
        Maximum followups from context variable, or default of 1
    """
    try:
        return followups_max_ctx.get()
    except LookupError:
        return 1


def get_passphrase() -> str:
    """
    Get passphrase from context variable, fallback to default.
    
    Returns:
        Passphrase from context variable, or default empty string
    """
    try:
        return passphrase_ctx.get()
    except LookupError:
        return ""


def get_chunks() -> List[str]:
    """
    Get chunks from context variable, fallback to default.
    
    Returns:
        Chunks list from context variable, or default fallback message list
    """
    try:
        chunks = chunks_ctx.get()
        # If context returns empty or fallback message, return it
        if not chunks or (len(chunks) == 1 and chunks[0].startswith("(No textbook content available")):
            return chunks if chunks else [FALLBACK_NO_TEXTBOOK_CONTENT]
        return chunks
    except LookupError:
        # Return fallback message list instead of empty list
        return [FALLBACK_NO_TEXTBOOK_CONTENT]


def get_textbook_sha256() -> str:
    """
    Get textbook_sha256 from context variable, fallback to default.
    
    Returns:
        Textbook SHA256 from context variable, or default empty string
    """
    try:
        return textbook_sha256_ctx.get()
    except LookupError:
        return ""


def get_max_answer_timeout_sec(state: Optional[Dict[str, Any]] = None) -> int:
    """
    Get max_answer_timeout_sec from state dictionary, context variable, or default.
    
    This is the SINGLE SOURCE OF TRUTH for timeout configuration.
    The value is set from the professor's URL (time_per_question parameter)
    and stored in both the state dictionary and max_answer_timeout_sec_ctx context variable.
    
    Priority order:
    1. State dictionary (time_per_question) - most reliable across Gradio contexts
    2. Context variable (max_answer_timeout_sec_ctx) - thread-safe but context-local
    3. Default (60 seconds) - fallback if neither is available
    
    All code should use this function to access the timeout value.
    Local variables may use 'max_timeout' for brevity, but should always
    retrieve the value via this function.
    
    Args:
        state: Optional state dictionary. If provided and contains 'time_per_question',
               that value will be used (most reliable across Gradio contexts).
    
    Returns:
        Max answer timeout in seconds from state, context variable, or default of 60
    """
    # Priority 1: Check state dictionary (most reliable across Gradio contexts)
    if state is not None:
        time_per_question = state.get("time_per_question")
        if time_per_question is not None:
            return int(time_per_question)
    
    # Priority 2: Check context variable
    try:
        value = max_answer_timeout_sec_ctx.get()
        # Check if value was actually set (not None/default)
        if value is not None:
            return value
    except LookupError:
        pass  # Context variable not set in this context
    
    # Priority 3: Use default (only log warning if state was provided but didn't have value)
    if state is not None:
        # State was provided but didn't have time_per_question - this is unexpected
        import logging
        logging.warning(
            f"max_answer_timeout_sec not found in state or context - using default 60. "
            f"State keys: {list(state.keys()) if state else 'None'}"
        )
    
    return 60

