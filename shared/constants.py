"""
Centralized constants for the VivaAI Secure Exam Proctoring System.

This module provides single source of truth for size limits and other constants
used across multiple modules (Principle #2: SSOT).

Message Flow Documentation:
==========================

User Experience Flow:
1. Main Question Display:
   → "📋 **Question 1 of 5**\n\n[Question text]"
   → "⏱️ **Timer started:** You have 60 seconds to answer this question."

2. User Answers:
   → "🎤 Processing your audio..."

3. After Transcription:
   → "🔊 Generating assessment... (Question 1 of 5)"
   
4. If Follow-up Coming:
   → "🔊 Asking follow-up question... (Question 1 of 5, Follow-up 1 of 2)"
   
5. Follow-up Question Display:
   → "🔵 **Follow-up 1 of 2** (Question 1 of 5)\n\n[Follow-up question]"
   → "⏱️ **Timer started:** You have 60 seconds to answer this follow-up question."

6. After Assessment:
   → "Assessment: Your response seems [Excellent/Satisfactory/Not-Satisfactory]. [Feedback]"
   
7. Next Question Transition:
   → "Now, next question:\n[Next question]"
   
8. Exam Completion:
   → "Exam complete. Press Finish & Download."
"""

from typing import Dict, Any

# File size limits
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB - Maximum file size for uploads/decryption
MAX_PDF_SIZE = 2 * 1024 * 1024   # 2MB - Maximum PDF size for processing

# Request limits
MAX_REQUEST_BODY_SIZE = 25 * 1024 * 1024  # 25MB - Maximum request body size
MAX_URL_LENGTH = 2048  # 2KB - Maximum URL length
MAX_JSON_DEPTH = 10  # Maximum JSON nesting depth

# Timeout limits
REQUEST_TIMEOUT_SECONDS = 300  # 5 minutes - Request timeout
AUTO_SAVE_INTERVAL_SEC = 30  # 30 seconds - Auto-save interval

# Rate limiting defaults
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
DEFAULT_RATE_LIMIT_PER_HOUR = 1000
DEFAULT_RATE_LIMIT_BURST = 10

# Session limits
MAX_SESSION_DURATION_SEC = 3600  # 1 hour - Maximum session duration
MAX_ANSWER_TIMEOUT_SEC = 300  # 5 minutes - Maximum answer timeout

# Collection bounds (from exam/state/validation.py)
MAX_HISTORY_ENTRIES = 1000
MAX_ANSWERS_TSLOG = 500
MAX_SECURITY_EVENTS = 1000
MAX_TOKEN_USAGE = 500
MAX_QUESTIONS_META = 100
MAX_TAB_FOCUS_EVENTS = 500
MAX_CLIPBOARD_EVENTS = 500
MAX_ANSWER_HASHES = 500
MAX_ANSWER_TEXTS = 200
MAX_USED_CONTEXT_HASHES = 1000

# Cache limits
PDF_CACHE_MAX_ENTRIES = 20  # Maximum PDF cache entries in memory
PDF_CACHE_MAX_SIZE_MB = 500  # Maximum PDF cache size on disk (MB)
TRANSCRIPT_CACHE_TIMEOUT_SECONDS = 3600  # 1 hour - Transcript cache TTL

# UI Processing Messages
# These messages are shown to users during exam flow to indicate system status
PROCESSING_ASSESSMENT_MSG = "🔊 Generating assessment..."
PROCESSING_FOLLOWUP_MSG = "🔊 Asking follow-up question..."
PROCESSING_AUDIO_RESPONSE_MSG = "🔊 Generating audio response..."
PROCESSING_AUDIO_MSG = "🎤 Processing your audio..."

# UI Status Messages (shown in status indicators)
UI_STATUS_GENERATING_QUESTION = "🔄 Generating question..."
UI_STATUS_ASKING_FOLLOWUP = "🔄 Asking follow-up question..."
UI_STATUS_GENERATING_ASSESSMENT = "🔄 Generating assessment..."
UI_STATUS_PROCESSING_AUDIO = "🔄 Processing audio..."

# Timeout Notification Messages
TIMEOUT_NOTIFICATION_MAIN_TEMPLATE = "⏱️ **Timer started:** You have {timeout} seconds to answer this question."
TIMEOUT_NOTIFICATION_FOLLOWUP_TEMPLATE = "⏱️ **Timer started:** You have {timeout} seconds to answer this follow-up question."

# Assessment Message Template
ASSESSMENT_MESSAGE_TEMPLATE = "Assessment: Your response seems {qualitative}. {feedback_text}"

# Transition Messages
TRANSITION_NEXT_QUESTION = "Now, next question:"

# Qualitative Assessment Configuration
QUALITATIVE_THRESHOLD_EXCELLENT = 85
QUALITATIVE_THRESHOLD_SATISFACTORY = 70
QUALITATIVE_EXCELLENT = "Excellent"
QUALITATIVE_SATISFACTORY = "Satisfactory"
QUALITATIVE_NOT_SATISFACTORY = "Inadequate"

# Status Messages
STATUS_QUESTION_ASKED = "Question asked."
STATUS_FOLLOWUP_ASKED = "Follow-up asked."
STATUS_EXAM_COMPLETE = "✔️ Exam complete. Press Finish & Download."
STATUS_QUESTION_LIMIT_REACHED = "✔️ Question limit reached. Press Finish & Download."
STATUS_CONTINUING_AUTOMATICALLY = "➡️ Continuing automatically…"

# Exam Completion Messages
EXAM_COMPLETE_MESSAGE = "Exam complete. Press Finish & Download."

# Timeout Error Messages
TIMEOUT_ERROR_MESSAGE = "⏱️ **Answer timeout:** Per-question time limit exceeded. Exam session ended."
TIMEOUT_ERROR_STATUS = "⚠️ Answer timeout: Per-question time limit exceeded. Exam ended."

# Question Generation Error Messages
ERROR_NO_PDF_CONTENT = "❌ Cannot generate questions: No PDF content loaded."
ERROR_PDF_NOT_AVAILABLE = "❌ Cannot generate questions: PDF content not available."
ERROR_NO_VALID_CHUNKS = "❌ Cannot generate questions: No valid chunks found."

# Informational Status Messages
INFO_COMPLETE_CURRENT_BLOCK = "ℹ️ Please complete the current block first."
INFO_CHECK_CONSENT = "🔒 Please check the consent box to begin."

# Default Error Messages
DEFAULT_ERROR_QUESTION_GENERATION = "Question generation failed"
DEFAULT_ERROR_FOLLOWUP_GENERATION = "Follow-up question generation failed"

# Fallback Content
FALLBACK_QUESTION = "Could you explain your understanding of the key concepts from this section?"

# Answer Labels
ANSWER_LABEL_MAIN = "Main Answer"
ANSWER_LABEL_FOLLOWUP_TEMPLATE = "Follow-up {num} Answer"

# PDF Error Message Suffixes
PDF_ERROR_SUFFIX_LOAD_BEFORE_START = "Please load a PDF from the Settings tab before starting the exam."
PDF_ERROR_SUFFIX_LOAD_VALID = "Please load a valid PDF from the Settings tab."
PDF_ERROR_SUFFIX_RELOAD = "Please reload the PDF from the Settings tab."
PDF_ERROR_SUFFIX_CHECK_URL = "Please check the PDF URL and try again."

# PDF Validation Error Messages
ERROR_PDF_VALIDATION_FAILED = "PDF Validation Failed"
ERROR_CANNOT_START_EXAM = "Cannot start exam:"
ERROR_PDF_LOADING_FAILED = "PDF Loading Failed:"

# Fallback Messages
FALLBACK_NO_TEXTBOOK_CONTENT = "(No textbook content available. Please load a PDF from Settings tab.)"

# PDF Validation Error Templates
PDF_VALIDATION_ERROR_TEMPLATE = "PDF validation failed: No valid chunks found. Total chunks: {total}, Valid chunks: {valid}. PDF content may be too short or invalid."

# Termination Messages
TERMINATION_CRITICAL_VIOLATION_PREFIX = "❌ **Critical violation:**"
TERMINATION_MULTI_FACE = "❌ **Critical violation:** Multiple faces detected. Exam terminated."
TERMINATION_VOICEPRINT_MISMATCH = "❌ **Critical violation:** Voiceprint mismatch detected. Different person detected. Exam terminated."
TERMINATION_PROFANITY = "❌ **Critical violation:** Profanity detected. Exam terminated."
TERMINATION_GENERIC_TEMPLATE = "❌ **Critical violation:** {violation_type}. Exam terminated."

# Exam Completion Status Messages
STATUS_EXAM_COMPLETED = "✅ Exam Completed"
STATUS_EXAM_TERMINATED = "⚠️ Exam Terminated"
INFO_CHECK_CHAT_HISTORY = "Please check chat history for details."

# Proctor Status Messages
PROCTOR_ENDED = "📷 Proctoring ended."

# Termination Detection Keywords
TERMINATION_KEYWORDS = [
    "Exam terminated",
    "Critical violation",
    "threshold exceeded",
    "Session timeout",
    "Answer timeout",
    "Profanity detected"
]

# Default Error Messages
DEFAULT_ERROR_OCCURRED = "Error occurred"

FEEDBACK_DEFAULT_TEXT = "Evaluation completed."


def get_qualitative_assessment(score: float) -> str:
    """
    Determine qualitative assessment based on score threshold.
    
    Business logic: Maps numeric score to qualitative assessment.
    Thresholds: >= 85 = Excellent, >= 70 = Satisfactory, < 70 = Not-Satisfactory
    
    Args:
        score: Overall score (0-100)
        
    Returns:
        Qualitative assessment string (Excellent, Satisfactory, or Not-Satisfactory)
    """
    if score >= QUALITATIVE_THRESHOLD_EXCELLENT:
        return QUALITATIVE_EXCELLENT
    elif score >= QUALITATIVE_THRESHOLD_SATISFACTORY:
        return QUALITATIVE_SATISFACTORY
    else:
        return QUALITATIVE_NOT_SATISFACTORY


def format_termination_message(violation_type: str) -> str:
    """
    Format termination message for critical violations.
    
    Args:
        violation_type: Type of violation (e.g., "MULTI_FACE", "VOICEPRINT_MISMATCH", "PROFANITY_DETECTED")
        
    Returns:
        Formatted termination message
    """
    termination_messages = {
        "VOICEPRINT_MISMATCH": TERMINATION_VOICEPRINT_MISMATCH,
        "MULTI_FACE": TERMINATION_MULTI_FACE,
        "PROFANITY_DETECTED": TERMINATION_PROFANITY,
    }
    return termination_messages.get(
        violation_type,
        TERMINATION_GENERIC_TEMPLATE.format(violation_type=violation_type)
    )


def format_pdf_validation_error(total_chunks: int, valid_chunks: int) -> str:
    """
    Format PDF validation error with chunk counts.
    
    Args:
        total_chunks: Total number of chunks found
        valid_chunks: Number of valid chunks (should be 0)
        
    Returns:
        Formatted validation error message
    """
    return PDF_VALIDATION_ERROR_TEMPLATE.format(total=total_chunks, valid=valid_chunks)


def format_error_with_solution(error_message: str, solution: str) -> str:
    """
    Format error message with solution suffix.
    
    Args:
        error_message: Base error message
        solution: Solution or instruction for the user
        
    Returns:
        Formatted error message with solution
    """
    return f"{error_message}\n\n{solution}"


def format_answer_label(index: int) -> str:
    """
    Format answer label for display.
    
    Args:
        index: Answer index (0 for main answer, >0 for follow-ups)
        
    Returns:
        Formatted answer label string
    """
    if index == 0:
        return ANSWER_LABEL_MAIN
    return ANSWER_LABEL_FOLLOWUP_TEMPLATE.format(num=index)


def format_exam_completion_message(feedback_summary: str) -> str:
    """
    Format exam completion message with feedback summary.
    
    Args:
        feedback_summary: Assessment feedback summary
        
    Returns:
        Formatted completion message
    """
    return f"{feedback_summary}\n\n{EXAM_COMPLETE_MESSAGE}"


def format_timeout_notification(timeout_sec: int, is_followup: bool = False) -> str:
    """
    Format timeout notification message.
    
    Args:
        timeout_sec: Timeout in seconds
        is_followup: If True, use follow-up template; otherwise use main question template
        
    Returns:
        Formatted timeout notification string
    """
    template = TIMEOUT_NOTIFICATION_FOLLOWUP_TEMPLATE if is_followup else TIMEOUT_NOTIFICATION_MAIN_TEMPLATE
    return template.format(timeout=timeout_sec)


def format_assessment_message(qualitative: str, feedback_text: str) -> str:
    """
    Format assessment message consistently.
    
    Args:
        qualitative: Qualitative assessment (Excellent, Satisfactory, Not-Satisfactory)
        feedback_text: Feedback text from grader
        
    Returns:
        Formatted assessment message string
    """
    return ASSESSMENT_MESSAGE_TEMPLATE.format(qualitative=qualitative, feedback_text=feedback_text)


def clean_feedback_text(feedback_text: str) -> str:
    """
    Strip qualitative assessment words and numeric scores from feedback text.
    
    This ensures that feedback_text doesn't contain leaked qualitative words
    (Not-Satisfactory, Satisfactory, Excellent) or numeric scores that should
    be hidden from students.
    
    Args:
        feedback_text: Raw feedback text that may contain scores/qualitative words
        
    Returns:
        Cleaned feedback text with scores and qualitative words removed
    """
    import re
    
    if not feedback_text:
        return "Evaluation completed."
    
    cleaned = feedback_text
    
    # Strip any qualitative assessment words that might have leaked into feedback_text
    # The AI might include "Not-Satisfactory", "Satisfactory", or "Excellent" in feedback_text,
    # but we want to use our own calculation based on the actual numeric scores
    cleaned = re.sub(
        r'(?i)\b(Excellent|Satisfactory|Not-Satisfactory|Not Satisfactory)\b',
        '',
        cleaned
    ).strip()
    
    # Strip any numeric scores from feedback_text (handles multiline cases and markdown)
    # Pattern matches: "Conceptual: 85", "**Conceptual:** 85", "Conceptual : 85", etc.
    # Handles scores both inline and on separate lines
    # First, remove inline markdown scores (e.g., "**Conceptual:** 85" in the middle of text)
    cleaned = re.sub(
        r'(?i)\*{0,2}(Conceptual|Analytical|Application|Reflection|Overall)\*{0,2}\s*[:：]\s*\*{0,2}\s*\d{1,3}\b',
        '',
        cleaned
    )
    # Also handle scores at line boundaries (multiline-aware)
    cleaned = re.sub(
        r'(?i)(?:^|\n|\r)\s*\*{0,2}(Conceptual|Analytical|Application|Reflection|Overall)\*{0,2}\s*[:：]\s*\*{0,2}\s*\d{1,3}\s*(?:\n|\r|$)',
        '',
        cleaned,
        flags=re.MULTILINE
    )
    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n\s*\n+', '\n', cleaned).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # If feedback_text was completely stripped, use fallback
    if not cleaned:
        cleaned = "Evaluation completed."
    
    return cleaned


def clean_feedback_summary(feedback_summary: str) -> str:
    """
    Strip qualitative assessment words and numeric scores from feedback_summary.
    
    This is a safety net that ensures any scores or qualitative words that leaked
    into feedback_summary (after formatting) are removed. The intended qualitative
    assessment from format_assessment_message is preserved.
    
    Args:
        feedback_summary: Formatted assessment message that may contain leaked scores/words
        
    Returns:
        Cleaned feedback_summary with scores and leaked qualitative words removed
    """
    import re
    
    if not feedback_summary:
        return "Assessment: Evaluation completed."
    
    cleaned = feedback_summary
    
    # Strip any qualitative assessment words that might have leaked (but preserve the intended one)
    # The intended format is "Assessment: Your response seems [qualitative]."
    # So we strip qualitative words that appear elsewhere in the text
    cleaned = re.sub(
        r'(?i)(?<!Assessment: Your response seems )\b(Excellent|Satisfactory|Not-Satisfactory|Not Satisfactory)\b',
        '',
        cleaned
    ).strip()
    
    # Strip any numeric scores from feedback_summary (handles multiline cases and markdown)
    # Pattern matches: "Conceptual: 85", "**Conceptual:** 85", "Conceptual : 85", etc.
    # Handles scores both inline and on separate lines
    # First, remove inline markdown scores (e.g., "**Conceptual:** 85" in the middle of text)
    cleaned = re.sub(
        r'(?i)\*{0,2}(Conceptual|Analytical|Application|Reflection|Overall)\*{0,2}\s*[:：]\s*\*{0,2}\s*\d{1,3}\b',
        '',
        cleaned
    )
    # Also handle scores at line boundaries (multiline-aware)
    cleaned = re.sub(
        r'(?i)(?:^|\n|\r)\s*\*{0,2}(Conceptual|Analytical|Application|Reflection|Overall)\*{0,2}\s*[:：]\s*\*{0,2}\s*\d{1,3}\s*(?:\n|\r|$)',
        '',
        cleaned,
        flags=re.MULTILINE
    )
    # Clean up extra whitespace and newlines
    cleaned = re.sub(r'\n\s*\n+', '\n', cleaned).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    return cleaned


def format_question_label(
    question_num: int,
    total_questions: int,
    question_type: str = "main"
) -> str:
    """
    Format question label with numbering for visual distinction.
    
    Args:
        question_num: Current question number (1-based)
        total_questions: Total number of questions (for main) or follow-ups (for followup)
        question_type: "main" or "followup"
        
    Returns:
        Formatted question label string
    """
    if question_type == "main":
        return f"📋 **Question {question_num} of {total_questions}**"
    else:  # followup
        if total_questions > 1:
            return f"🔵 **Follow-up {question_num} of {total_questions}**"
        else:
            return "🔵 **Follow-up Question**"


def format_processing_message_with_context(
    base_message: str,
    s: Dict[str, Any],
    include_followup_info: bool = False
) -> str:
    """
    Format processing message with progress context.
    
    Adds question progress (e.g., "Question 2 of 5") and optionally follow-up info
    to processing messages for better user clarity.
    
    Args:
        base_message: Base processing message (e.g., PROCESSING_ASSESSMENT_MSG)
        s: State dictionary
        include_followup_info: If True, include follow-up progress info
        
    Returns:
        Formatted message with progress context
        
    Example:
        >>> format_processing_message_with_context(
        ...     PROCESSING_ASSESSMENT_MSG,
        ...     {"asked_main": 1, "limit": 5}
        ... )
        "🔊 Generating assessment... (Question 2 of 5)"
    """
    asked_main = s.get("asked_main", 0)
    limit = s.get("limit", 0)
    
    # Build context string
    context_parts = []
    
    # Add question progress if available
    if asked_main >= 0 and limit > 0:
        current_q = asked_main + 1
        context_parts.append(f"Question {current_q} of {limit}")
    
    # Add follow-up info if requested
    if include_followup_info:
        current = s.get("current", {})
        followups_done = current.get("followups_done", 0)
        target_followups = current.get("target_followups", 0)
        if target_followups > 0:
            followup_num = followups_done + 1
            context_parts.append(f"Follow-up {followup_num} of {target_followups}")
    
    # Format final message
    if context_parts:
        context_str = " (" + ", ".join(context_parts) + ")"
        return f"{base_message}{context_str}"
    
    return base_message

# Export all constants
__all__ = [
    "MAX_FILE_SIZE",
    "MAX_PDF_SIZE",
    "MAX_REQUEST_BODY_SIZE",
    "MAX_URL_LENGTH",
    "MAX_JSON_DEPTH",
    "REQUEST_TIMEOUT_SECONDS",
    "AUTO_SAVE_INTERVAL_SEC",
    "DEFAULT_RATE_LIMIT_PER_MINUTE",
    "DEFAULT_RATE_LIMIT_PER_HOUR",
    "DEFAULT_RATE_LIMIT_BURST",
    "MAX_SESSION_DURATION_SEC",
    "MAX_ANSWER_TIMEOUT_SEC",
    "MAX_HISTORY_ENTRIES",
    "MAX_ANSWERS_TSLOG",
    "MAX_SECURITY_EVENTS",
    "MAX_TOKEN_USAGE",
    "MAX_QUESTIONS_META",
    "MAX_TAB_FOCUS_EVENTS",
    "MAX_CLIPBOARD_EVENTS",
    "MAX_ANSWER_HASHES",
    "MAX_ANSWER_TEXTS",
    "MAX_USED_CONTEXT_HASHES",
    "PDF_CACHE_MAX_ENTRIES",
    "PDF_CACHE_MAX_SIZE_MB",
    "TRANSCRIPT_CACHE_TIMEOUT_SECONDS",
    # UI Processing Messages
    "PROCESSING_ASSESSMENT_MSG",
    "PROCESSING_FOLLOWUP_MSG",
    "PROCESSING_AUDIO_RESPONSE_MSG",
    "PROCESSING_AUDIO_MSG",
    # UI Status Messages
    "UI_STATUS_GENERATING_QUESTION",
    "UI_STATUS_ASKING_FOLLOWUP",
    "UI_STATUS_GENERATING_ASSESSMENT",
    "UI_STATUS_PROCESSING_AUDIO",
    # Timeout Notifications
    "TIMEOUT_NOTIFICATION_MAIN_TEMPLATE",
    "TIMEOUT_NOTIFICATION_FOLLOWUP_TEMPLATE",
    # Assessment Messages
    "ASSESSMENT_MESSAGE_TEMPLATE",
    # Transition Messages
    "TRANSITION_NEXT_QUESTION",
    # Qualitative Assessment
    "QUALITATIVE_THRESHOLD_EXCELLENT",
    "QUALITATIVE_THRESHOLD_SATISFACTORY",
    "QUALITATIVE_EXCELLENT",
    "QUALITATIVE_SATISFACTORY",
    "QUALITATIVE_NOT_SATISFACTORY",
    # Status Messages
    "STATUS_QUESTION_ASKED",
    "STATUS_FOLLOWUP_ASKED",
    "STATUS_EXAM_COMPLETE",
    "STATUS_QUESTION_LIMIT_REACHED",
    "STATUS_CONTINUING_AUTOMATICALLY",
    # Exam Completion Messages
    "EXAM_COMPLETE_MESSAGE",
    # Helper Functions
    "get_qualitative_assessment",
    "format_exam_completion_message",
    "format_timeout_notification",
    "format_assessment_message",
    "clean_feedback_text",
    "format_question_label",
    "format_processing_message_with_context",
]

