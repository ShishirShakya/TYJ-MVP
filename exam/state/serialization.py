"""
Serialization configuration and exclusions.

This module defines what data is excluded from serialization to prevent
memory growth and protect sensitive data. Used by save_state_to_disk().

PRINCIPLE #25: Selective Serialization & Bounded State
- Excludes large, transient data that can be reconstructed from cache/context
- Bounds unbounded collections to prevent memory growth
- Only serializes essential state for persistence
- Avoids redundant serialization/deserialization cycles

**Serialization Strategy**:
1. **Exclude**: Large/transient data available from cache (chunks, text, proctor_state)
2. **Bound**: Collections with size limits (history: 1000, answers: 500, etc.)
3. **Include**: Only essential state for persistence (session_id, scores, rubrics, etc.)
4. **Transport**: Serialize only at boundaries (save_state_to_disk), not in flow

**Working Data**:
- Large data (chunks, text) kept in memory/thread-local storage
- Transient data (current, queued_answers) not serialized
- State passed as parameters (naturally thread-safe)

**Usage**:
    ```python
    from exam.state.serialization import prepare_state_for_serialization
    
    # Prepare state for serialization (excludes/bounds fields)
    prepared = prepare_state_for_serialization(state)
    
    # Serialize prepared state (not original state)
    json.dump(prepared, file)
    ```
"""

from typing import Dict, Any


# Fields that are excluded from serialization
# These are large, transient, or available from cache/context
SERIALIZATION_EXCLUSIONS = {
    # Large data structures that can be reconstructed
    "chunks",  # PDF chunks - available from cache
    "text",  # Full PDF text - available from cache
    
    # Transient runtime data
    "_rng",  # Random number generator - recreated on load
    "_rng_seed",  # RNG seed - regenerated on load
    
    # Proctor state (can be large, reconstructed from summary)
    "proctor_state",  # Full proctor state object - use proctor_summary instead
    
    # Network state (ephemeral)
    "queued_answers",  # Queued answers - cleared on restart
    
    # Temporary processing data
    "current",  # Current question block - reset on restart
    
    # Audio data (large, transient)
    "audio_data",  # Raw audio data - not stored
    "audio_features",  # Audio features - recalculated if needed
}

# Fields that are included but bounded
# These have size limits to prevent unbounded growth
SERIALIZATION_BOUNDS = {
    "history": 1000,  # Maximum history entries
    "answers_tslog_all": 500,  # Maximum answer log entries
    "security_events": 1000,  # Maximum security events
    "token_usage": 500,  # Maximum token usage entries
    "questions_meta": 100,  # Maximum question metadata entries
    "tab_focus_events": 500,  # Maximum tab focus/blur events (security audit trail)
    "clipboard_events": 500,  # Maximum clipboard events (security audit trail)
    "answer_hashes": 500,  # Maximum answer hashes (for reuse detection)
    "answer_texts": 200,  # Maximum answer texts (for semantic similarity, can be large)
    "used_context_hashes": 1000,  # Maximum context hashes (set size limit)
}

# Fields that are always included (critical for state)
SERIALIZATION_REQUIRED = {
    "session_id",
    "student_id",
    "course_id",
    "exam_id",
    "section_id",
    "phase",
    "started_at",
    "session_start_time",
    "limit",
    "followups_min",
    "followups_max",
    "passphrase",
    "asked_main",
    "scores",
    "rubrics",
    "flags",
    "consent",
    "proctor_summary",
    "otet",
}


def should_serialize_field(field_name: str, value: Any) -> bool:
    """
    Determine if a field should be serialized.
    
    SELECTIVE SERIALIZATION: Excludes large/transient data (Principle #25).
    BOUNDED STATE: Checks bounds for collections (Principle #25).
    
    Args:
        field_name: Name of the field
        value: Value of the field
        
    Returns:
        True if field should be serialized, False otherwise
        
    **Decision Logic**:
    1. Always exclude fields in SERIALIZATION_EXCLUSIONS
    2. Always include fields in SERIALIZATION_REQUIRED
    3. Check bounds for fields in SERIALIZATION_BOUNDS (include if within bounds)
    4. Default: include field
    """
    # Always exclude excluded fields
    if field_name in SERIALIZATION_EXCLUSIONS:
        return False
    
    # Always include required fields
    if field_name in SERIALIZATION_REQUIRED:
        return True
    
    # Bounded fields should always be included (they will be bounded in prepare_state_for_serialization)
    # Don't exclude them here based on size - let prepare_state_for_serialization handle bounding
    if field_name in SERIALIZATION_BOUNDS:
        return True
    
    # Default: include field
    return True


def prepare_state_for_serialization(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepare state dictionary for serialization by excluding/bounding fields.
    
    **Contract**:
    - **Inputs**: Full state dictionary (may include large/transient data)
    - **Outputs**: Prepared state dictionary (excludes large data, bounds collections)
    - **Invariants**: Required fields always included; excluded fields never included
    - **Failure Modes**: Never raises exceptions; always returns valid dict
    
    SELECTIVE SERIALIZATION: Excludes large/transient data available from cache/context (Principle #25).
    BOUNDED STATE: Truncates collections to prevent unbounded growth (Principle #25).
    
    This function:
    1. Excludes large/transient data (chunks, text, proctor_state, _rng, queued_answers, current)
    2. Bounds collections (history: 1000, answers_tslog_all: 500, security_events: 1000, etc.)
    3. Includes only essential state for persistence
    
    **Performance**: Creates a new dictionary (does not modify input).
    **Memory**: Significantly reduces memory footprint by excluding large data.
    
    Args:
        state: State dictionary to prepare (may include large/transient data)
        
    Returns:
        Prepared state dictionary ready for serialization
        - Excludes: chunks, text, proctor_state, _rng, queued_answers, current, audio_data, audio_features
        - Bounds: history (1000), answers_tslog_all (500), security_events (1000), etc.
        - Includes: session_id, student_id, scores, rubrics, phase, etc.
        
    Raises:
        Never raises exceptions. Always returns valid dictionary.
        
    Example:
        ```python
        # Full state includes large data
        state = {
            "session_id": "abc123",
            "chunks": ["chunk1...", "chunk2..."],  # Large - excluded
            "history": [{"role": "user", "content": "..."}] * 2000,  # Bounded to 1000
            "scores": [85, 90, 88]
        }
        
        # Prepared state excludes/bounds
        prepared = prepare_state_for_serialization(state)
        # prepared = {
        #     "session_id": "abc123",
        #     "history": [{"role": "user", "content": "..."}] * 1000,  # Truncated
        #     "scores": [85, 90, 88]
        #     # chunks excluded
        # }
        ```
    """
    prepared = {}
    
    for field_name, value in state.items():
        if not should_serialize_field(field_name, value):
            continue
        
        # Apply bounds for bounded fields
        if field_name in SERIALIZATION_BOUNDS:
            max_size = SERIALIZATION_BOUNDS[field_name]
            if isinstance(value, (list, tuple)):
                if len(value) > max_size:
                    # Keep most recent entries
                    value = value[-max_size:]
            elif isinstance(value, dict):
                if len(value) > max_size:
                    # Keep most recent entries (if dict maintains insertion order)
                    items = list(value.items())
                    value = dict(items[-max_size:])
            elif isinstance(value, set):
                # Convert set to list and bound it
                value_list = list(value)
                if len(value_list) > max_size:
                    # Keep most recent entries (convert to list, then back to set)
                    value = set(value_list[-max_size:])
                else:
                    # Convert to list for JSON serialization
                    value = value_list
        
        prepared[field_name] = value
    
    return prepared

