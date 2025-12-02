"""
Wrapper functions for exam.ipynb.

This module contains wrapper functions that bridge between the notebook's
global variables/context variables and the modular functions. These wrappers
handle backward compatibility and provide a clean interface for the notebook.

Modules:
- config: Configuration wrappers (parse_professor_link_and_setup, get_chunks, etc.)
- state: State management wrappers (ensure_state, save_state_to_disk, etc.)
- export: Export wrappers (finalize_and_export_encrypted, _auto_wipe_local_after_export)
"""

from exam.wrappers.config import (
    parse_professor_link_and_setup,
    get_chunks,
    load_pdf_from_url_with_cache,
    validate_chunks_available,
)

from exam.wrappers.state import (
    ensure_state,
    save_state_to_disk,
    auto_save_state,
    queue_answer_locally,
    load_state_from_disk,
    resume_from_disk,
)

from exam.wrappers.export import (
    _auto_wipe_local_after_export,
    finalize_and_export_encrypted,
)

__all__ = [
    # Config wrappers
    "parse_professor_link_and_setup",
    "get_chunks",
    "load_pdf_from_url_with_cache",
    "validate_chunks_available",
    # State wrappers
    "ensure_state",
    "save_state_to_disk",
    "auto_save_state",
    "queue_answer_locally",
    "load_state_from_disk",
    "resume_from_disk",
    # Export wrappers
    "_auto_wipe_local_after_export",
    "finalize_and_export_encrypted",
]

