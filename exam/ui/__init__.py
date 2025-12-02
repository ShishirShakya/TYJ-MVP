"""
UI module for exam interface.

This module contains UI components, helpers, handlers, and layout functions
for the exam interface. All functions use dependency injection for Gradio
to ensure compatibility across different environments.
"""

from exam.ui.components import create_ui_components
from exam.ui.helpers import (
    _calculate_timeout_status,
    _calculate_progress,
    _calculate_processing_status,
    _calculate_connection_status,
    _stream_proctor,
)
from exam.ui.handlers import (
    _proctor_end_updates,
    handle_security_event,
    handle_parse_and_show_chatbot,
    handle_consent_checkbox,
    handle_student_id_verify,
    handle_webcam_consent_checkbox,
    handle_start_exam,
    handle_mic_wrapper,
    _after_finish_ui,
    handle_file_integrity_checkbox,
)
from exam.ui.layout import create_ui_layout, get_layout_components
from exam.ui.security_js import get_security_javascript

__all__ = [
    "create_ui_components",
    "_calculate_timeout_status",
    "_calculate_progress",
    "_calculate_processing_status",
    "_calculate_connection_status",
    "_stream_proctor",
    "_proctor_end_updates",
    "handle_security_event",
    "handle_parse_and_show_chatbot",
    "handle_consent_checkbox",
    "handle_student_id_verify",
    "handle_webcam_consent_checkbox",
    "handle_start_exam",
    "handle_mic_wrapper",
    "_after_finish_ui",
    "handle_file_integrity_checkbox",
    "create_ui_layout",
    "get_layout_components",
    "get_security_javascript",
]

