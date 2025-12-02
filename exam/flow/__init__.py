"""
Flow module for exam interface.

This module contains core business logic functions for the exam flow:
- Question generation (main and follow-up questions)
- Audio processing and flow control
- Grading and next question preparation

All functions use dependency injection for Gradio and other dependencies
to ensure compatibility across different environments.
"""

from exam.flow.questions import (
    ask_main_question,
    ask_followup_question,
    on_first_mic_press,
)
from exam.flow.audio import handle_mic
from exam.flow.grading import grade_current_block

__all__ = [
    "ask_main_question",
    "ask_followup_question",
    "on_first_mic_press",
    "handle_mic",
    "grade_current_block",
]

