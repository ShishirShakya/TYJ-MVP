"""
AI components module for exam.ipynb.

This module contains AI-powered functions for:
- Question generation (main and follow-up questions)
- Grading and feedback generation
- Context management and history optimization
"""

from exam.ai.question_generator import (
    _gen_main_question_with_ctx,
    _gen_followup,
    _get_cached_or_generate,
    _check_duplicate_question,
    MAIN_QUESTION_INSTR,
    FOLLOWUP_QUESTION_INSTR,
)

# Import CHAT_MODEL from config (not from question_generator)
from exam.config import CHAT_MODEL

from exam.ai.grader import (
    grade_current_block,
    _parse_feedback,
    _extract_scores,
    _calculate_overall_score,
    FEEDBACK_BLOCK_INSTR,
)

from exam.ai.context_manager import (
    msgs_from_state,
    _get_relevant_history,
    SYSTEM_PROMPT,
    MAX_HISTORY_LENGTH,
    MAX_HISTORY_LENGTH_QUESTION,
    MAX_HISTORY_LENGTH_FOLLOWUP,
    MAX_HISTORY_LENGTH_FEEDBACK,
)

__all__ = [
    # Question generation
    "_gen_main_question_with_ctx",
    "_gen_followup",
    "_get_cached_or_generate",
    "_check_duplicate_question",
    "CHAT_MODEL",
    "MAIN_QUESTION_INSTR",
    "FOLLOWUP_QUESTION_INSTR",
    # Grading
    "grade_current_block",
    "_parse_feedback",
    "_extract_scores",
    "_calculate_overall_score",
    "FEEDBACK_BLOCK_INSTR",
    # Context management
    "msgs_from_state",
    "_get_relevant_history",
    "SYSTEM_PROMPT",
    "MAX_HISTORY_LENGTH",
    "MAX_HISTORY_LENGTH_QUESTION",
    "MAX_HISTORY_LENGTH_FOLLOWUP",
    "MAX_HISTORY_LENGTH_FEEDBACK",
]

