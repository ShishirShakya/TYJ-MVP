# -*- coding: utf-8 -*-
# VivaAI Secure — Exam Interface
# Student-facing exam application with proctoring and audio recording

# Standard library imports
import os
import logging
import time
from typing import Optional, Tuple, Dict, Any, List
from contextvars import ContextVar
from dotenv import load_dotenv
import structlog

# Load environment variables BEFORE importing modules that use VIVA_HMAC_SECRET
# This ensures .env file is loaded before exam.cryptography, shared.cryptography,
# and other modules try to read VIVA_HMAC_SECRET at import time
load_dotenv()

# =========================
# SINGLE SOURCE OF TRUTH: Base Temp Directory Configuration
# =========================
# MUST be set before importing ANY module that uses tempfile or platform_provider
# This includes: gradio, exam.pdf_cache, exam.file_utils, shared.platform
import tempfile
from pathlib import Path

def choose_base_temp_dir() -> str:
    """
    Decide on a single base temp directory for:
    - Python's tempfile (via platform_provider)
    - Gradio (via GRADIO_TEMP_DIR)
    - vivaai session directories
    - PDF cache directories
    
    Preference:
    1. VIVAAI_BASE_TEMP_DIR (explicit override)
    2. TMPDIR (if set and valid)
    3. system tempfile.gettempdir()
    
    Note: GRADIO_TEMP_DIR is NOT used here - it's always a subdir of base
    """
    candidate = (
        os.getenv("VIVAAI_BASE_TEMP_DIR")
        or os.getenv("TMPDIR")
        or tempfile.gettempdir()
    )
    
    candidate = os.path.abspath(candidate)
    
    try:
        Path(candidate).mkdir(parents=True, exist_ok=True)
        if not os.access(candidate, os.W_OK):
            raise PermissionError(f"Base temp dir not writable: {candidate}")
        return candidate
    except Exception as e:
        system_temp = os.path.abspath(tempfile.gettempdir())
        Path(system_temp).mkdir(parents=True, exist_ok=True)
        logging.warning(
            f"Configured base temp dir not usable ({candidate}), "
            f"falling back to system temp ({system_temp}): {e}"
        )
        return system_temp

# ------------ SINGLE SOURCE OF TRUTH ------------
BASE_TEMP_DIR = choose_base_temp_dir()

# Determine GRADIO_TEMP_DIR (always a subdir of BASE_TEMP_DIR)
user_gradio_temp = os.getenv("GRADIO_TEMP_DIR")
if user_gradio_temp:
    user_gradio_temp = os.path.abspath(user_gradio_temp)
    try:
        # Only use user's GRADIO_TEMP_DIR if it's under BASE_TEMP_DIR
        common_path = os.path.commonpath([BASE_TEMP_DIR, user_gradio_temp])
        if common_path == BASE_TEMP_DIR:
            candidate_gradio = user_gradio_temp
        else:
            candidate_gradio = os.path.join(BASE_TEMP_DIR, "gradio")
    except ValueError:
        # Paths don't share common path (Windows drive mismatch, etc.)
        candidate_gradio = os.path.join(BASE_TEMP_DIR, "gradio")
else:
    # Default: gradio subdirectory under base
    candidate_gradio = os.path.join(BASE_TEMP_DIR, "gradio")

# Verify GRADIO_TEMP_DIR is writable
try:
    Path(candidate_gradio).mkdir(parents=True, exist_ok=True)
    if not os.access(candidate_gradio, os.W_OK):
        raise PermissionError(f"GRADIO_TEMP_DIR not writable: {candidate_gradio}")
    GRADIO_TEMP_DIR = candidate_gradio
except Exception as e:
    # Fall back to a safe subdir under BASE_TEMP_DIR
    fallback = os.path.join(BASE_TEMP_DIR, "gradio")
    Path(fallback).mkdir(parents=True, exist_ok=True)
    logging.warning(
        f"Configured GRADIO_TEMP_DIR not usable ({candidate_gradio}), "
        f"falling back to {fallback}: {e}"
    )
    GRADIO_TEMP_DIR = fallback

# Tell Gradio where to put microphone recordings
# CRITICAL: Must be set BEFORE importing gradio (line 169)
os.environ["GRADIO_TEMP_DIR"] = GRADIO_TEMP_DIR

# VERIFICATION: Ensure GRADIO_TEMP_DIR is under BASE_TEMP_DIR
abs_base = os.path.abspath(BASE_TEMP_DIR)
abs_gradio = os.path.abspath(GRADIO_TEMP_DIR)
if not abs_gradio.startswith(abs_base):
    raise ValueError(
        f"GRADIO_TEMP_DIR ({abs_gradio}) must be under BASE_TEMP_DIR ({abs_base}). "
        f"This is a critical configuration error."
    )

# VERIFICATION: Ensure GRADIO_TEMP_DIR is writable
if not os.access(GRADIO_TEMP_DIR, os.W_OK):
    raise PermissionError(
        f"GRADIO_TEMP_DIR is not writable: {GRADIO_TEMP_DIR}. "
        f"Check permissions and disk space."
    )

# OBSERVABILITY: Log configuration for troubleshooting (Principle #13)
logging.info(
    f"BASE_TEMP_DIR configured: {BASE_TEMP_DIR}",
    extra={
        "base_temp_dir": BASE_TEMP_DIR,
        "gradio_temp_dir": GRADIO_TEMP_DIR,
        "env_gradio_temp_dir": os.environ.get("GRADIO_TEMP_DIR"),
        "gradio_under_base": abs_gradio.startswith(abs_base),
        "gradio_writable": os.access(GRADIO_TEMP_DIR, os.W_OK),
        "base_writable": os.access(BASE_TEMP_DIR, os.W_OK),
        "tempfile_gettempdir": tempfile.gettempdir()
    }
)

# CRITICAL: Update platform_provider to use BASE_TEMP_DIR (dependency injection)
try:
    from shared.platform import set_default_platform_provider, RealPlatformProvider
    
    class ConfiguredPlatformProvider(RealPlatformProvider):
        """Platform provider that uses BASE_TEMP_DIR instead of tempfile.gettempdir()."""
        def get_temp_dir(self) -> str:
            return BASE_TEMP_DIR
    
    # Set the configured provider BEFORE any modules use it
    set_default_platform_provider(ConfiguredPlatformProvider())
    _PLATFORM_PROVIDER_SET_LATER = False
except ImportError:
    # Circular import - will set in __main__
    _PLATFORM_PROVIDER_SET_LATER = True
    logging.warning(
        "Could not set platform_provider at import time - "
        "will set in __main__ before demo construction"
    )

# ------------------------------------------------

# =========================
# Startup Validation
# =========================
# Validate required environment variables (fail fast in production)
environment = os.getenv("ENVIRONMENT", "development").lower()
if environment == "production":
    from shared.config_validation import validate_required_env_vars
    is_valid, error = validate_required_env_vars(["VIVA_HMAC_SECRET", "OPENAI_API_KEY"])
    if not is_valid:
        print(f"❌ Configuration Error: {error}")
        print("   Set required environment variables in .env file or environment variables.")
        import sys
        sys.exit(1)
else:
    # Warn in development if critical vars are missing
    missing = []
    if not os.getenv("VIVA_HMAC_SECRET"):
        missing.append("VIVA_HMAC_SECRET")
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    if missing:
        print(f"⚠️  Warning: Missing environment variables: {', '.join(missing)}")
        print("   Set them in .env file for full functionality.")
        print("   See .env.example for a template.")

# Configure logging for chunk validation warnings
logging.basicConfig(level=logging.WARNING)

# Get logger for API mode and session recovery
logger = structlog.get_logger(__name__)

# Third-party library imports
import gradio as gr
from openai import OpenAI

# =========================
# API Mode & Session Recovery Imports
# =========================
from exam.api_client import get_api_client, ExamAPIClient
from exam.session_recovery import check_for_saved_session, prompt_resume_session
from exam.api_mode_adapters import (
    transcribe_audio_via_api_or_direct,
    generate_question_via_api_or_direct,
    grade_answer_via_api_or_direct,
    generate_tts_via_api_or_direct,
    generate_followup_question_via_api_or_direct
)

# =========================
# Shared Module Imports
# =========================
# Import shared utilities (cryptography, URL encoding, file utilities, PDF processing, utilities)
from exam.cryptography import encrypt_bytes
from shared.cryptography import decrypt_bytes
from exam.file_utils import _paths_for_session
from shared.file_utils import _lock_file, _unlock_file
from shared.pdf_processing import (
    _convert_dropbox_url,
    _download_pdf_from_url,
    _load_pdf_from_bytes,
    _chunk_text,
    _validate_context,
)
from exam.utils import (
    _sanitize_for_prompt,
    _normalize_answer_for_hash,
    _hash_answer,
    _calculate_answer_similarity,
    _count_meaningful_words,
    _detect_profanity,
    _detect_answer_reuse,
    _ensure_qmark,
    _validate_question,
    _compress_context_chunk,
    _truncate_answer_for_followup,
    _categorize_error,
    with_retry,
    _log_token_usage,
)
# =========================
# Import video proctoring components
# =========================
from exam.proctor import (
    ProctorState,
    proctor_analyze_frame,
    PROCTOR_RULES,
    PROCTOR_CONFIG,
    PROCTOR_FLAG_RULES,
)
from shared.config_parsing import (
    parse_professor_link_and_setup as _parse_professor_link_and_setup_shared,
    parse_passphrase_from_url,
)
from shared.time_provider import get_default_time_provider
from exam.context_vars import (
    get_course_id,
    get_exam_id,
    get_n_questions,
    get_followups_min,
    get_followups_max,
    get_passphrase,
    get_chunks,
    get_textbook_sha256,
    get_max_answer_timeout_sec,
    course_id_ctx,
    exam_id_ctx,
    n_questions_ctx,
    followups_min_ctx,
    followups_max_ctx,
    passphrase_ctx,
    chunks_ctx,
    textbook_sha256_ctx,
    max_answer_timeout_sec_ctx,
)
from exam.state import (
    ensure_state as _ensure_state_base,
    reset_current_block,
    get_followup_range,
    atomic_write_json_secure,
    save_state_to_disk as _save_state_to_disk_base,
    auto_save_state as _auto_save_state_base,
    load_state_from_disk as _load_state_from_disk_base,
    resume_from_disk as _resume_from_disk_base,
    check_network_status,
    update_network_status,
    queue_answer_locally as _queue_answer_locally_base,
    process_queued_answers,
)
from exam.audio import (
    tts_to_mp3,
    transcribe,
    extract_audio_features,
    compare_voiceprints,
    analyze_speech_stylometry,
    get_audio_duration,
    cleanup_session_tmp,
    TTS_MODEL,
    TTS_VOICE,
    STT_MODEL,
)
from exam.ai import (
    _gen_main_question_with_ctx,
    _gen_followup,
    _get_cached_or_generate,
    _check_duplicate_question,
    grade_current_block,
    _parse_feedback,
    _calculate_overall_score,
    msgs_from_state,
    _get_relevant_history,
    CHAT_MODEL,
    SYSTEM_PROMPT,
    MAIN_QUESTION_INSTR,
    FOLLOWUP_QUESTION_INSTR,
    FEEDBACK_BLOCK_INSTR,
    MAX_HISTORY_LENGTH,
    MAX_HISTORY_LENGTH_QUESTION,
    MAX_HISTORY_LENGTH_FOLLOWUP,
    MAX_HISTORY_LENGTH_FEEDBACK,
)
# =========================
# Flow Module Imports
# =========================
from exam.flow import (
    ask_main_question as ask_main_question_flow,
    ask_followup_question as ask_followup_question_flow,
    on_first_mic_press as on_first_mic_press_flow,
    handle_mic as handle_mic_flow,
    grade_current_block as grade_current_block_flow,
)
from exam.pdf_cache import (
    load_pdf_from_url_with_cache as _load_pdf_from_url_with_cache_base,
    validate_chunks_available as _validate_chunks_available_base,
)
# =========================
# Wrapper Module Imports
# =========================
from exam.wrappers import (
    parse_professor_link_and_setup as parse_professor_link_and_setup_wrapper,
    get_chunks as get_chunks_wrapper,
    load_pdf_from_url_with_cache as load_pdf_from_url_with_cache_wrapper,
    validate_chunks_available as validate_chunks_available_wrapper,
    ensure_state as ensure_state_wrapper,
    save_state_to_disk as save_state_to_disk_wrapper,
    auto_save_state as auto_save_state_wrapper,
    queue_answer_locally as queue_answer_locally_wrapper,
    load_state_from_disk as load_state_from_disk_wrapper,
    resume_from_disk as resume_from_disk_wrapper,
    _auto_wipe_local_after_export as _auto_wipe_local_after_export_wrapper,
    finalize_and_export_encrypted as finalize_and_export_encrypted_wrapper,
)
# =========================
# UI Module Imports
# =========================
from exam.ui.handlers import (
    _proctor_end_updates,
    handle_security_event,
    handle_parse_and_show_chatbot as handle_parse_and_show_chatbot_handler,
    handle_consent_checkbox as handle_consent_checkbox_handler,
    handle_student_id_verify as handle_student_id_verify_handler,
    handle_webcam_consent_checkbox as handle_webcam_consent_checkbox_handler,
    handle_start_exam as handle_start_exam_handler,
    _after_finish_ui as _after_finish_ui_handler,
    handle_file_integrity_checkbox as handle_file_integrity_checkbox_handler,
)
from exam.ui.helpers import (
    _calculate_timeout_status,
    _calculate_progress as _calculate_progress_helper,
    _calculate_processing_status as _calculate_processing_status_helper,
    _calculate_connection_status as _calculate_connection_status_helper,
    _calculate_queue_status as _calculate_queue_status_helper,
    _stream_proctor as _stream_proctor_helper,
)
# =========================
# Import export functions
# =========================
from exam.export import (
    finalize_and_export_encrypted as _finalize_and_export_encrypted_base,
    auto_wipe_local_after_export as _auto_wipe_local_after_export_base,
)
from exam.security import (
    get_otet,
    get_or_create_device_key,
    pubkey_bytes,
    answers_to_merkle,
    log_security_event,
)
# Note: dashboard_utils functions moved to dash/ modules (not used in exam.ipynb)

# Optional heavy dependencies (graceful fallback)
try:
    import numpy as np
    import mediapipe as mp
    _HAS_PROCTOR = True
    # LOG: Report MediaPipe installation status
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"MediaPipe successfully imported (version: {getattr(mp, '__version__', 'unknown')})"
    )
except Exception as e:
    _HAS_PROCTOR = False
    np = None
    mp = None
    # LOG: Report MediaPipe installation failure
    import logging
    logger = logging.getLogger(__name__)
    logger.error(
        f"MediaPipe import failed - proctoring will use basic mode. Error: {type(e).__name__}: {str(e)}"
    )

# Audio analysis for voiceprint/stylometric checks
# Audio analysis is enabled by default (stylometric analysis runs without librosa)
_HAS_AUDIO_ANALYSIS = True  # Audio analysis is always enabled by default
try:
    import librosa
    _HAS_LIBROSA = True  # librosa available for voiceprint analysis
except ImportError:
    _HAS_LIBROSA = False  # librosa not available, but audio analysis still enabled
    librosa = None

# =========================
# Configuration Imports
# =========================
from exam.config import (
    APP_VERSION,
    RECEIPT_VERSION,
    RUBRIC_VERSION,
    MIN_WORDS,
    MAX_SHORT_ATTEMPTS,
    SHORT_PROMPT_TTS,
    MAX_ANSWER_TIMEOUT_SEC_DEFAULT,
    PROCESSING_BUFFER_SEC,
    SESSION_BUFFER_SEC,
    MAX_PDF_SIZE,
    MAX_PAGES,
    PERSIST_OK,
    HMAC_SECRET,
    continuity_mode,
    model_versions,
    logger,
)

# =========================
# Global Viva Configuration
# =========================

# API Mode Configuration
api_client = get_api_client()  # None if API mode is disabled
EXAM_API_MODE = api_client is not None

if EXAM_API_MODE:
    api_url = os.getenv("API_BASE_URL") or os.getenv("EXAM_API_URL", "unknown")
    logger.info(
        "api_mode_enabled",
        api_url=api_url,
        message="API mode enabled - exam will use FastAPI backend"
    )
else:
    logger.info(
        "api_mode_disabled",
        message="API mode disabled - exam will run in standalone mode"
    )

# Exam Configuration (defaults - actual values set from URL via context variables)
N_QUESTIONS = 1
FOLLOWUPS_MIN = 0
FOLLOWUPS_MAX = 1
# Initialize PASSPHRASE (exam-specific decryption key from URL)
# This is set when parse_professor_link() is called
PASSPHRASE = ""

# Timeout Configuration (dynamic - set from URL)
MAX_ANSWER_TIMEOUT_SEC = MAX_ANSWER_TIMEOUT_SEC_DEFAULT
MAX_SESSION_DURATION_SEC = (get_max_answer_timeout_sec()+PROCESSING_BUFFER_SEC+SESSION_BUFFER_SEC) * (get_n_questions() + (get_n_questions() * get_followups_max()))

# Initialize textbook content (empty initially, loaded from URL)
TEXTBOOK_SHA256 = ""

# Helper functions for configuration (imported from exam.config)
# Aliases for backward compatibility
_continuity_mode = continuity_mode
_model_versions = model_versions

# =========================
# Section 3: Utility Classes and Helper Functions
# =========================

def parse_professor_link_and_setup(url: str):
    """
    Parse professor's link URL and automatically set up the examination.
    Returns: (success: bool, status_message: str, state_updates: dict)
    
    This is a wrapper around the shared parse_professor_link_and_setup function
    that provides exam-specific callbacks for context variables, PDF loading, etc.
    """
    global COURSE_ID, EXAM_ID, N_QUESTIONS, FOLLOWUPS_MIN, FOLLOWUPS_MAX, PASSPHRASE, MAX_ANSWER_TIMEOUT_SEC, MAX_SESSION_DURATION_SEC
    
    # Define callbacks for exam-specific operations (need to access notebook globals)
    def set_globals_callback(config_dict):
        """Set global variables for backward compatibility"""
        global COURSE_ID, EXAM_ID, N_QUESTIONS, FOLLOWUPS_MIN, FOLLOWUPS_MAX, PASSPHRASE, MAX_ANSWER_TIMEOUT_SEC
        COURSE_ID = config_dict["course_id"]
        EXAM_ID = config_dict["exam_id"]
        N_QUESTIONS = config_dict["num_questions"]
        FOLLOWUPS_MIN = config_dict["min_followups"]
        FOLLOWUPS_MAX = config_dict["max_followups"]
        PASSPHRASE = config_dict["passphrase"]
        MAX_ANSWER_TIMEOUT_SEC = config_dict["time_per_question"]
    
    def calculate_session_duration_callback():
        """Recalculate MAX_SESSION_DURATION_SEC with new values"""
        global MAX_SESSION_DURATION_SEC
        max_timeout = get_max_answer_timeout_sec()
        n_questions = get_n_questions()
        followups_max = get_followups_max()
        MAX_SESSION_DURATION_SEC = (max_timeout + 30 + 10) * (n_questions + (n_questions * followups_max))  # 30 seconds processing time and 10 seconds buffer
    
    # Call wrapper function with callbacks that use notebook's wrapper functions
    return parse_professor_link_and_setup_wrapper(
        url,
        load_pdf_callback=load_pdf_from_url_with_cache,
        validate_chunks_callback=validate_chunks_available,
        set_globals_callback=set_globals_callback,
        calculate_session_duration_callback=calculate_session_duration_callback,
    )

# Initialize with empty content (no fallback to chapter-02.pdf)
# User must load PDF via URL in Settings tab

# Initialize CHUNKS as empty - will be updated when PDF is loaded
CHUNKS = ["(No textbook content available. Please load a PDF from Settings tab.)"]

# =========================
# PDF Caching Wrapper Functions
# =========================

# Override get_chunks to check both context variable and global CHUNKS variable
# This handles cases where context variables might not be shared across Gradio handlers
def get_chunks() -> list:
    """
    Get chunks from context variable, fallback to global CHUNKS variable.
    
    This wrapper checks both the context variable and the global CHUNKS variable
    to handle cases where context variables might not be shared across Gradio handlers.
    """
    global CHUNKS
    return get_chunks_wrapper(CHUNKS=CHUNKS)

def load_pdf_from_url_with_cache(url: str) -> tuple[str, str]:
    """
    Wrapper for load_pdf_from_url_with_cache that handles global variables.
    Returns (status_message, updated_sha256)
    """
    global TEXTBOOK_SHA256, CHUNKS
    
    # Call wrapper function with global variables
    status_msg, new_sha256, new_chunks = load_pdf_from_url_with_cache_wrapper(
        url,
        TEXTBOOK_SHA256=TEXTBOOK_SHA256,
        CHUNKS=CHUNKS,
    )
    
    # Update global variables if successful
    if new_sha256 and new_chunks:
        TEXTBOOK_SHA256 = new_sha256
        CHUNKS = new_chunks
    
    return status_msg, new_sha256

def validate_chunks_available() -> tuple[bool, str, int]:
    """
    Wrapper for validate_chunks_available that uses notebook getter function.
    Returns (is_valid, error_message, valid_count)
    """
    return validate_chunks_available_wrapper(get_chunks_fn=get_chunks)

# =========================
# OpenAI setup
# =========================
client = OpenAI()

# =========================
# Question Generation (Caching Disabled)
# =========================
# NOTE: Question caching has been disabled to prevent duplicate questions.
# All questions are generated fresh for maximum variety.

# =========================
# State Management Wrapper
# =========================
def ensure_state(s):
    """Wrapper for ensure_state that uses notebook getter functions"""
    return ensure_state_wrapper(s)

# Aliases for backward compatibility
_get_followup_range = get_followup_range
_atomic_write_json_secure = atomic_write_json_secure

# Wrapper functions to pass PERSIST_OK constant
def save_state_to_disk(s: dict) -> bool:
    """Wrapper for save_state_to_disk that passes PERSIST_OK"""
    return save_state_to_disk_wrapper(s, PERSIST_OK=PERSIST_OK)

def auto_save_state(s: dict) -> bool:
    """Wrapper for auto_save_state that passes PERSIST_OK"""
    return auto_save_state_wrapper(s, PERSIST_OK=PERSIST_OK)

def queue_answer_locally(s: dict, answer_text: str, answer_audio_path: str = None) -> None:
    """Wrapper for queue_answer_locally that passes PERSIST_OK"""
    return queue_answer_locally_wrapper(s, answer_text, answer_audio_path, PERSIST_OK=PERSIST_OK)

# =========================
# TTS / STT - Advanced Anti-Cheat: Voiceprint & Stylometric Analysis
# =========================

# =========================
# Flow: Ask / Answer / Grade
# =========================
def _build_flow_dependencies():
    """
    Build dependencies dictionary for flow functions.
    This function collects all dependencies needed by the extracted flow functions.
    """
    from exam.ui.helpers import _calculate_timeout_status
    from exam.ui.handlers import _proctor_end_updates
    
    return {
        # State management
        "ensure_state": ensure_state,
        "reset_current_block": reset_current_block,
        "get_followup_range": get_followup_range,
        "save_state_to_disk": save_state_to_disk,
        "_paths_for_session": _paths_for_session,
        
        # PDF and chunks
        "get_chunks": get_chunks,
        "validate_chunks_available": validate_chunks_available,
        "_validate_context": _validate_context,
        
        # AI functions
        "_gen_main_question_with_ctx": lambda s, ctx_text, client=None: generate_question_via_api_or_direct(
            s, ctx_text, client or globals().get('client'), api_client=api_client
        ) if api_client else _gen_main_question_with_ctx(s, ctx_text, client or globals().get('client')),
        "_gen_followup": lambda s, last_answer, client=None: generate_followup_question_via_api_or_direct(
            s, last_answer, client or globals().get('client'), api_client=api_client
        ) if api_client else _gen_followup(s, last_answer, client or globals().get('client')),
        "_parse_feedback": _parse_feedback,
        "_calculate_overall_score": _calculate_overall_score,
        "msgs_from_state": msgs_from_state,
        "with_retry": with_retry,
        "_log_token_usage": _log_token_usage,
        "_sanitize_for_prompt": _sanitize_for_prompt,
        # Phase 2: API adapter for grading (wraps OpenAI chat.completions.create)
        "grade_answer_via_api_or_direct": (
            lambda s, messages, client, api_client=None, chat_model="gpt-4o-mini": 
                grade_answer_via_api_or_direct(s, messages, client, api_client, chat_model)
        ) if api_client else None,  # Only inject if API mode enabled
        
        # Audio functions
        "tts_to_mp3": lambda text, client, s=None, progress=None: generate_tts_via_api_or_direct(
            text, client, s, api_client=api_client, progress=progress
        ) if api_client else tts_to_mp3(text, client, s, progress=progress),
        "transcribe": lambda audio_path, client, s=None, progress=None: transcribe_audio_via_api_or_direct(
            audio_path, s or {}, client, api_client=api_client
        ) if api_client else transcribe(audio_path, client, s, progress=progress),
        "get_audio_duration": get_audio_duration,
        "extract_audio_features": extract_audio_features if _HAS_LIBROSA else None,
        "compare_voiceprints": compare_voiceprints if _HAS_LIBROSA else None,
        "analyze_speech_stylometry": analyze_speech_stylometry,
        
        # UI helpers
        "_calculate_timeout_status": _calculate_timeout_status,
        "_proctor_end_updates": _proctor_end_updates,
        
        # State and network
        "update_network_status": update_network_status,
        "queue_answer_locally": queue_answer_locally,
        
        # Validation and security
        "_detect_profanity": _detect_profanity,
        "_count_meaningful_words": _count_meaningful_words,
        "_detect_answer_reuse": _detect_answer_reuse,
        "_hash_answer": _hash_answer,
        "_categorize_error": _categorize_error,
        
        # Flow functions (for recursive calls - use flow functions, not wrappers)
        "ask_main_question": ask_main_question_flow,
        "ask_followup_question": ask_followup_question_flow,
        "grade_current_block": grade_current_block_flow,
        
        # Constants
        "ProctorState": ProctorState,
        "CHAT_MODEL": CHAT_MODEL,
        "FEEDBACK_BLOCK_INSTR": FEEDBACK_BLOCK_INSTR,
        "MAX_SESSION_DURATION_SEC": MAX_SESSION_DURATION_SEC,
        "MIN_WORDS": MIN_WORDS,
        "MAX_SHORT_ATTEMPTS": MAX_SHORT_ATTEMPTS,
        "SHORT_PROMPT_TTS": SHORT_PROMPT_TTS,
        "get_max_answer_timeout_sec": get_max_answer_timeout_sec,
        "_HAS_LIBROSA": _HAS_LIBROSA,
        
        # Time provider for deterministic behavior (Principle #5)
        "time_provider": get_default_time_provider(),
    }

def ask_main_question(s, _status_md, progress=None):
    """Wrapper for ask_main_question_flow with dependency injection."""
    dependencies = _build_flow_dependencies()
    return ask_main_question_flow(s, gr, client, dependencies, progress=progress)

def ask_followup_question(s, _status_md, progress=None):
    """Wrapper for ask_followup_question_flow with dependency injection."""
    dependencies = _build_flow_dependencies()
    return ask_followup_question_flow(s, gr, client, dependencies, progress=progress)

def grade_current_block(s, _status_md, progress=None):
    """Wrapper for grade_current_block_flow with dependency injection."""
    dependencies = _build_flow_dependencies()
    return grade_current_block_flow(s, gr, client, dependencies, progress=progress)

# =========================
# Mic handlers (timing-safe)
# =========================

def on_first_mic_press(s, status_md):
    """
    First press after consent: play examiner’s question (mic OFF), do NOT record.
    Student releases and presses Record again to answer.
    """
    dependencies = _build_flow_dependencies()
    return on_first_mic_press_flow(s, status_md, gr, client, dependencies)

# Alias for backward compatibility
_log_security_event = log_security_event

def handle_mic(audio_path, s, status_md, progress=None):
    """Wrapper for handle_mic_flow with dependency injection."""
    dependencies = _build_flow_dependencies()
    return handle_mic_flow(audio_path, s, gr, client, dependencies, progress=progress)

# =========================
# Finalize & export (encrypted) with public receipt (VIVA2)
# =========================

def _auto_wipe_local_after_export(s):
    """
    Wrapper for auto_wipe_local_after_export that handles global variables.
    
    This wrapper handles global variables (PERSIST_OK, CHUNKS, TEXTBOOK_SHA256)
    that are used in the notebook but not in the module.
    """
    global PERSIST_OK, CHUNKS, TEXTBOOK_SHA256
    
    # Call wrapper function with global variables
    removed = _auto_wipe_local_after_export_wrapper(
        s,
        PERSIST_OK=PERSIST_OK,
        CHUNKS=CHUNKS,
        TEXTBOOK_SHA256=TEXTBOOK_SHA256,
    )
    
    # Update global variables for backward compatibility
    PERSIST_OK = False
    CHUNKS = ["(No textbook content available. Please load a PDF from Settings tab.)"]
    TEXTBOOK_SHA256 = ""
    
    return removed

def finalize_and_export_encrypted(s):
    """
    Wrapper for finalize_and_export_encrypted that handles global variables and context variables.
    
    This wrapper handles global variables (PERSIST_OK, CHUNKS, TEXTBOOK_SHA256) and
    context variables (get_chunks, get_textbook_sha256, get_max_answer_timeout_sec) that
    are used in the notebook but need to be passed to the module function.
    """
    global PERSIST_OK, CHUNKS, TEXTBOOK_SHA256
    
    # Call wrapper function with all necessary parameters
    return finalize_and_export_encrypted_wrapper(
        s,
        ensure_state_fn=ensure_state,
        save_state_to_disk_fn=save_state_to_disk,
        get_chunks_fn=get_chunks,
        get_textbook_sha256_fn=get_textbook_sha256,
        get_max_answer_timeout_sec_fn=get_max_answer_timeout_sec,
        PERSIST_OK=PERSIST_OK,
        CHUNKS=CHUNKS,
        TEXTBOOK_SHA256=TEXTBOOK_SHA256,
    )

# =========================
# Resume disabled stubs (FERPA-friendly)
# =========================

def load_state_from_disk():
    return load_state_from_disk_wrapper()

def resume_from_disk():
    return resume_from_disk_wrapper(ensure_state_fn=ensure_state)

# =========================
# UI (Exam)
# =========================
# Shared concurrency bucket
cpu_q = "cpu"

with gr.Blocks(title="VivaAI Secure - Exam") as demo:
    # Add custom JavaScript for security detection using HTML component
    security_js = gr.HTML(
        value="""
        <script>
        (function() {
            // Tab focus/blur detection
            let tabBlurCount = 0;
            let lastBlurTime = null;
            
            window.addEventListener('blur', function() {
                tabBlurCount++;
                lastBlurTime = Date.now();
                // Store in localStorage for backend retrieval
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'TAB_BLUR',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            window.addEventListener('focus', function() {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'TAB_FOCUS',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            // Clipboard detection (copy/paste)
            document.addEventListener('copy', function(e) {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'CLIPBOARD_COPY',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
            
            document.addEventListener('paste', function(e) {
                let events = JSON.parse(localStorage.getItem('security_events') || '[]');
                events.push({
                    type: 'CLIPBOARD_PASTE',
                    timestamp: new Date().toISOString()
                });
                localStorage.setItem('security_events', JSON.stringify(events));
            });
        })();
        </script>
        """,
        visible=False
    )
    
    with gr.Tab("Exam"):
        # Professor's Link Section
        with gr.Column(visible=True) as professor_link_section:
            with gr.Row():
                with gr.Column(scale=5):
                    professor_link_input = gr.Textbox(
                        label="Professor's Link",
                        placeholder="Paste exam configuration URL here...",
                        lines=2,
                        value=""
                    )
                with gr.Column(scale=1):
                    parse_link_btn = gr.Button("🔗 Parse & Setup", variant="primary", size="lg")
        
        # Verification Section
        with gr.Column(visible=False) as verification_section:
            with gr.Row():
                with gr.Column(scale=5):
                    verification_status = gr.Markdown(value="", elem_classes=["verification-status"])
        
        # Informed Consent Section
        with gr.Column(visible=False) as consent_section:
            with gr.Row():
                with gr.Column(scale=5):
                    consent_disclaimer = gr.Markdown(
                        value= f"### **⚠️ Informed Consent:** By proceeding, you acknowledge that this examination is conducted using AI and may include audio recording and proctoring for academic integrity purposes. You agree to complete this examination independently without unauthorized assistance.",
                        elem_classes=["consent-disclaimer"]
                    )
                with gr.Column(scale=1):
                    consent_checkbox = gr.Checkbox(label= "I acknowledge and consent.", value=False, interactive=True)
        
        # Student ID Section
        with gr.Column(visible=False) as student_id_section:
            with gr.Row():
                with gr.Column(scale=5):
                    student_id_input = gr.Textbox(label="Student ID", placeholder="Enter your Student ID (numeric/integer only)...", interactive=True)
                    student_id_status = gr.Markdown(value="", visible=False, elem_classes=["student-id-status"])
                with gr.Column(scale=1):
                    student_id_verify_checkbox = gr.Checkbox(label="I verify my Student ID is correct, once I check this, student ID section will be hidden.", value=False, interactive=True)
        
        # Webcam Consent Section (appears after Student ID)
        with gr.Column(visible=False) as webcam_consent_section:
            with gr.Row():
                with gr.Column(scale=5):
                    webcam_consent_disclaimer = gr.Markdown(
                        value=(
                            "### **⚠️ Webcam & Recording Consent:**\n\n"
                            "**Important:** Once you click the **Webcam** and **Record** button, the examination will start.\n\n"
                            "**Critical Rules:**\n"
                            "- Once the webcam is started, **DO NOT stop or disable the webcam** during the examination.\n"
                            "- Stopping or disabling the webcam **will be flagged** and the examination **will be terminated**.\n"
                            "- The webcam must remain active throughout the entire examination.\n"
                            "- You must keep your face visible to the webcam at all times.\n\n"
                            "**By proceeding, you acknowledge that you understand these rules and agree to keep the webcam active throughout the examination.**"
                        ),
                        elem_classes=["webcam-consent-disclaimer"]
                    )
                with gr.Column(scale=1):
                    webcam_consent_checkbox = gr.Checkbox(
                        label="I understand and agree to keep the webcam active throughout the examination.", 
                        value=False, 
                        interactive=True
                    )
        
        # Split Layout (shown after Webcam Consent)
        with gr.Column(visible=False) as exam_layout:
            with gr.Row():
                # Left side: Chatbot (60%)
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        label="Viva Dialogue", 
                        height=500, 
                        type="messages", 
                        show_copy_button=True,  # Still valid in Gradio 5.x (will be replaced by buttons in 6.0)
                        allow_tags=False,  # Explicitly set to avoid deprecation warning
                        avatar_images=(None, "👨‍🏫"),
                        value=[{"role": "assistant", "content": "Ready to begin... Webcam activation will start the exam."}]
                    )
                # Right side: Exam Setup (40%)
                with gr.Column(scale=2):
                    proctor_cam = gr.Image(
                        sources=["webcam"],
                        label="Webcam Proctoring (local only, not recorded)",
                        visible=True,
                        interactive=True
                    )
                    # Video statistics directly below camera
                    proctor_status = gr.Markdown(value="💤 Inactive", visible=True)
                    # Connection status indicator (real-time)
                    connection_status = gr.Markdown(value="🌐 Online", visible=True, elem_classes=["connection-status"])
                    # Phase 2.2.3: Queue status indicator
                    queue_status = gr.Markdown(
                        value="",
                        visible=False,
                        elem_classes=["queue-status"]
                    )
                    # Progress tracking display (real-time)
                    progress_info = gr.Markdown(value="", visible=False, elem_classes=["progress-info"])
                    # Status component below proctor status
                    unified_status = gr.HTML(value="", visible=False, elem_classes=["unified-status"])
                    # unified_status = gr.Textbox(value="", visible=True, label="Status", interactive=False, lines=2)
                    # Timeout countdown display (real-time)
                    timeout_countdown = gr.Markdown(value="", visible=False, elem_classes=["timeout-countdown"])
                    # Finish button below status (only shown after exam completion)
                    finish_btn = gr.Button(
                        "✅ Finish & Download", 
                        variant="primary", 
                        visible=False,
                        interactive=False
                    )
                    # File integrity acknowledgment checkbox (shown after file download)
                    file_integrity_checkbox = gr.Checkbox(
                        label="I acknowledge that I will not change the file name or attempt to tamper with the encrypted file.",
                        value=False,
                        interactive=True,
                        visible=False,
                        elem_classes=["file-integrity-checkbox"]
                    )
                    # File output - Hidden initially, shown after exam completion (positioned below finish button)
                    file_out = gr.File(
                        label="Encrypted Transcript (.enc)", 
                        interactive=False, 
                        visible=False, 
                        height=60
                    )

            
            # Audio components row (60/40 split matching main layout)
            with gr.Row():
                # Left side: Examiner audio (60%)
                with gr.Column(scale=3):
                    # Note: In Gradio 5.x, waveforms are shown by default
                    examiner_audio = gr.Audio(label="Examiner (spoken)", type="filepath", autoplay=True, visible=True)
                # Right side: Record button (40%)
                with gr.Column(scale=2):
                    # OBSERVABILITY: Log GRADIO_TEMP_DIR for troubleshooting (Principle #13)
                    logger.info(
                        "creating_microphone_component",
                        gradio_temp_dir_env=os.environ.get("GRADIO_TEMP_DIR"),
                        gradio_temp_dir_var=GRADIO_TEMP_DIR,
                        base_temp_dir=BASE_TEMP_DIR,
                        message=f"Creating Microphone component - GRADIO_TEMP_DIR={os.environ.get('GRADIO_TEMP_DIR')}"
                    )
                    mic = gr.Microphone(
                        label="🎤 Record",
                        type="filepath",
                        format="wav",
                        interactive=False,
                        show_label=True,
                        visible=False
                    )
        
        # Phase 2.2.2: Enhanced Session Recovery UI
        with gr.Column(visible=False) as resume_session_section:
            resume_prompt = gr.Markdown(
                value="",
                visible=False,
                elem_classes=["resume-prompt"]
            )
            with gr.Row():
                resume_btn = gr.Button(
                    "✅ Resume Session",
                    variant="primary",
                    visible=False,
                    interactive=False,
                    size="lg"
                )
                start_new_btn = gr.Button(
                    "🆕 Start New Session",
                    variant="secondary",
                    visible=False,
                    interactive=False,
                    size="lg"
                )
        
        # Initialize state with session recovery check
        initial_state = ensure_state({})
        resume_visible = False
        resume_msg = ""
        can_resume_flag = False
        session_summary_data = {}
        
        # Check for saved session and prompt user to resume
        saved_session = check_for_saved_session()
        if saved_session:
            recovered_state, status_msg, can_resume, session_summary = prompt_resume_session(
                saved_session, ensure_state_fn=ensure_state
            )
            initial_state = recovered_state
            resume_visible = can_resume
            resume_msg = status_msg
            can_resume_flag = can_resume
            session_summary_data = session_summary
            
            # If cannot resume, just show message in chatbot
            if not can_resume:
                initial_state.setdefault("history", []).insert(0, {
                    "role": "assistant",
                    "content": status_msg
                })
        
        s = gr.State(initial_state)
        
        # Phase 2.2.2: Show resume dialog if session can be resumed
        def show_resume_dialog():
            """Show resume dialog on app load if session found."""
            if resume_visible and can_resume_flag:
                return (
                    gr.update(visible=True),
                    gr.update(value=resume_msg, visible=True),
                    gr.update(visible=True, interactive=True),
                    gr.update(visible=True, interactive=True)
                )
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )
        
        def handle_resume_session(current_state):
            """Handle resume session button click."""
            # State is already set to recovered_state in initial_state
            logger.info(
                "session_resumed",
                session_id=current_state.get("session_id"),
                message="User chose to resume session"
            )
            return (
                current_state,
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )
        
        def handle_start_new_session(current_state):
            """Handle start new session button click."""
            fresh_state = ensure_state({})
            logger.info(
                "new_session_started",
                message="User chose to start new session"
            )
            return (
                fresh_state,
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False)
            )
        
        # Phase 2.2.2: Show resume dialog on app load (before other load handlers)
        # This runs first to check for saved sessions
        demo.load(
            show_resume_dialog,
            inputs=[],
            outputs=[resume_session_section, resume_prompt, resume_btn, start_new_btn]
        )
        
        # Wire resume buttons
        resume_btn.click(
            handle_resume_session,
            inputs=[s],
            outputs=[s, resume_session_section, resume_btn, start_new_btn]
        )
        
        start_new_btn.click(
            handle_start_new_session,
            inputs=[s],
            outputs=[s, resume_session_section, resume_btn, start_new_btn]
        )
        # Hidden audio output component (kept for wiring compatibility)
        audio_out = gr.Audio(visible=False)  # Hidden - prevents users from seeing/editing recorded audio

        def handle_parse_and_show_chatbot(url, current_state):
            """Wrapper for handle_parse_and_show_chatbot from exam.ui.handlers"""
            dependencies = {
                "parse_professor_link_and_setup": parse_professor_link_and_setup,
                "ensure_state": ensure_state,
                "validate_chunks_available": validate_chunks_available,
                "get_chunks": get_chunks,
                "get_n_questions": get_n_questions,
                "get_followups_max": get_followups_max,
                "get_max_answer_timeout_sec": get_max_answer_timeout_sec,
            }
            # Call imported version - returns 11 values including step_indicator
            result = handle_parse_and_show_chatbot_handler(url, current_state, gr, dependencies)
            # Drop step_indicator (last value) to match call site expectations (10 outputs)
            return result[:-1]
        
        def handle_consent_checkbox(checked, current_state):
            """Wrapper for handle_consent_checkbox from exam.ui.handlers"""
            result = handle_consent_checkbox_handler(checked, current_state, gr)
            # Return only consent_section and student_id_section (drop step_indicator and verification_section)
            return (result[0], result[1])
        
        def handle_student_id_verify(checked, student_id_value, current_state):
            """Wrapper for handle_student_id_verify from exam.ui.handlers"""
            result = handle_student_id_verify_handler(checked, student_id_value, current_state, gr, ensure_state)
            # Return only the 7 values expected by call site (drop step_indicator which is last)
            return result[:-1]
        
        def handle_webcam_consent_checkbox(checked, current_state):
            """Wrapper for handle_webcam_consent_checkbox from exam.ui.handlers"""
            dependencies = {
                "ensure_state": ensure_state,
                "validate_chunks_available": validate_chunks_available,
                "ProctorState": ProctorState,
                "_HAS_PROCTOR": _HAS_PROCTOR,
                "mp": mp if _HAS_PROCTOR else None,
            }
            result = handle_webcam_consent_checkbox_handler(checked, current_state, gr, dependencies)
            # Return only the 3 values expected by call site (drop step_indicator which is last)
            return result[:-1]
        
        def _calculate_progress(s):
            """Wrapper for _calculate_progress from exam.ui.helpers"""
            return _calculate_progress_helper(s, gr, MAX_ANSWER_TIMEOUT_SEC, get_n_questions, get_followups_max)
        
        def _calculate_processing_status(s, gr_module=None):
            """Wrapper for _calculate_processing_status from exam.ui.helpers"""
            # Use gr_module if provided, otherwise fallback to global gr
            gr_to_use = gr_module if gr_module is not None else gr
            return _calculate_processing_status_helper(s, gr_to_use)
        
        def _calculate_connection_status(s):
            """Wrapper for _calculate_connection_status from exam.ui.helpers"""
            return _calculate_connection_status_helper(s, gr)
        
        def handle_start_exam(current_state):
            """Wrapper for handle_start_exam from exam.ui.handlers"""
            # Build full flow dependencies (required by ask_main_question_flow)
            dependencies = _build_flow_dependencies()
            # Add handler-specific dependencies
            dependencies["validate_chunks_available"] = validate_chunks_available
            dependencies["client"] = client  # Required by handle_start_exam_handler
            
            # Log wrapper call for debugging Railway issues
            log_msg = f"[HANDLE_START_EXAM_CALLED] session={current_state.get('session_id', 'unknown')}, has_client={client is not None}, has_validate={validate_chunks_available is not None}"
            print(log_msg, flush=True)  # Print for Railway visibility
            logger.info(
                "handle_start_exam_wrapper_called",
                session_id=current_state.get("session_id", "unknown"),
                has_client=client is not None,
                has_validate_chunks=validate_chunks_available is not None,
                message=log_msg
            )
            
            return handle_start_exam_handler(current_state, gr, dependencies)
        
        def _stream_proctor(frame, sdict):
            """Wrapper for _stream_proctor from exam.ui.helpers"""
            dependencies = {
                "MAX_SESSION_DURATION_SEC": MAX_SESSION_DURATION_SEC,
                "_HAS_PROCTOR": _HAS_PROCTOR,
                "mp": mp if _HAS_PROCTOR else None,
                "_proctor_end_updates": _proctor_end_updates,
                "_calculate_timeout_status": lambda s: _calculate_timeout_status(s, gr, get_max_answer_timeout_sec),
                "_calculate_progress": _calculate_progress_helper,  # Use helper directly, not wrapper
                "_calculate_connection_status": _calculate_connection_status_helper,  # Use helper directly
                "_calculate_processing_status": _calculate_processing_status_helper,  # Use helper directly
                "_calculate_queue_status": _calculate_queue_status_helper,  # Phase 2.2.3: Queue status
                "handle_start_exam": handle_start_exam,
                "MAX_ANSWER_TIMEOUT_SEC": MAX_ANSWER_TIMEOUT_SEC,
                "get_n_questions": get_n_questions,
                "get_followups_max": get_followups_max,
                "get_max_answer_timeout_sec": get_max_answer_timeout_sec,
            }
            
            # Log dependency setup for debugging Railway issues
            # Commented out for clarity - too verbose
            # log_msg = f"[STREAM_PROCTOR_DEPS] handle_start_exam={'present' if handle_start_exam else 'MISSING'}, type={type(handle_start_exam).__name__ if handle_start_exam else None}"
            # print(log_msg, flush=True)  # Print for Railway visibility
            log_msg = f"handle_start_exam={'present' if handle_start_exam else 'MISSING'}, type={type(handle_start_exam).__name__ if handle_start_exam else None}"
            logger.info(
                "stream_proctor_dependencies",
                session_id=sdict.get("session_id", "unknown") if isinstance(sdict, dict) else "unknown",
                has_handle_start_exam=handle_start_exam is not None,
                handle_start_exam_type=type(handle_start_exam).__name__ if handle_start_exam else None,
                message=log_msg
            )
            
            return _stream_proctor_helper(frame, sdict, gr, dependencies)
        
        def handle_mic_wrapper(audio_path, current_state, status_md, progress=None):
            """Wrapper for handle_mic - processes answer recording and queued answers"""
            current_state = ensure_state(current_state)
            
            # Check for queued answers and process them if network is available
            from exam.state.network import process_queued_answers, check_network_status
            if check_network_status():
                processed_count, queued_answers = process_queued_answers(current_state, clear_after_processing=False)
                if processed_count > 0:
                    logger.info(
                        "processing_queued_answers",
                        session_id=current_state.get("session_id", "unknown"),
                        count=processed_count,
                        message=f"Found {processed_count} queued answers to process"
                    )
                    # Process queued answers through normal flow
                    # Process each queued answer as if it was just recorded
                    for queued_answer in queued_answers:
                        queued_audio_path = queued_answer.get("audio_path")
                        queued_text = queued_answer.get("text", "")
                        
                        # If we have audio, process it through handle_mic
                        # Otherwise, if we have text, process it directly
                        if queued_audio_path and os.path.exists(queued_audio_path):
                            try:
                                # Process queued audio through normal flow
                                current_state, _, _, _, _, _, _, _, _ = handle_mic(
                                    queued_audio_path, current_state, gr, progress=progress
                                )
                            except Exception as e:
                                logger.warning(
                                    "queued_answer_processing_failed",
                                    session_id=current_state.get("session_id", "unknown"),
                                    audio_path=queued_audio_path,
                                    error=str(e)[:200],
                                    message="Failed to process queued answer"
                                )
                        elif queued_text and queued_text != "(Audio recorded offline - will process when connection restored)":
                            # If we only have text (no audio), add it to history and continue flow
                            # This handles cases where transcription was done but processing failed
                            current_state.setdefault("history", []).append({"role": "user", "content": queued_text})
                            # Continue with normal flow (ask followup or grade)
                            # The flow will handle this based on current phase
                    
                    # Clear queued answers after processing
                    current_state["queued_answers"] = []
                    save_state_to_disk(current_state)
                    
                    # Add notification to history
                    current_state["history"].append({
                        "role": "assistant",
                        "content": f"🌐 Back online! Processed {processed_count} pending answer(s)."
                    })
            
            # Extract audio_path from dict if needed (Gradio Microphone can return dict)
            # Otherwise pass through as-is
            audio_path_str = audio_path
            if isinstance(audio_path, dict):
                audio_path_str = audio_path.get('name', audio_path.get('path', None))
            
            # Normalize empty strings to None for consistent handling
            if audio_path_str == "":
                audio_path_str = None
            
            # OBSERVABILITY: Log audio path for debugging (Principle #13)
            logger.info(
                "handle_mic_wrapper_audio_path_received",
                session_id=current_state.get('session_id', 'unknown'),
                audio_path_type=type(audio_path).__name__ if audio_path else "None",
                audio_path_value=str(audio_path)[:200] if audio_path else None,
                audio_path_str=audio_path_str,
                gradio_temp_dir_env=os.environ.get("GRADIO_TEMP_DIR"),
                gradio_temp_dir_var=GRADIO_TEMP_DIR,
                base_temp_dir=BASE_TEMP_DIR,
                message=f"handle_mic_wrapper received audio_path: {audio_path_str}"
            )
            
            # IMPORTANT: Wait for audio file to be saved (Gradio may call stop_recording before file is ready)
            # Even if audio_path is None initially, Gradio might still be saving the file asynchronously
            if audio_path_str:
                max_wait_seconds = 5.0  # Increased from 2.0 to 5.0 for slower systems/platforms
                wait_interval = 0.1  # Check every 100ms
                waited = 0.0
                while not os.path.exists(audio_path_str) and waited < max_wait_seconds:
                    time.sleep(wait_interval)
                    waited += wait_interval
                
                if not os.path.exists(audio_path_str):
                    logger.warning(
                        "audio_file_not_ready",
                        session_id=current_state.get("session_id", "unknown"),
                        audio_path=audio_path_str,
                        waited_seconds=waited,
                        parent_dir=os.path.dirname(audio_path_str) if audio_path_str else None,
                        parent_dir_exists=os.path.exists(os.path.dirname(audio_path_str)) if audio_path_str else False,
                        message=f"Audio file not ready after {waited:.2f}s: {audio_path_str}"
                    )
                    # Set to None so handle_mic can handle it gracefully
                    audio_path_str = None
                else:
                    # Comprehensive file validation
                    file_size = os.path.getsize(audio_path_str)
                    file_size_mb = file_size / (1024 * 1024)
                    is_readable = os.access(audio_path_str, os.R_OK)
                    
                    # Check WAV file header (should start with "RIFF")
                    is_valid_wav = False
                    try:
                        with open(audio_path_str, 'rb') as f:
                            header = f.read(12)
                            is_valid_wav = header.startswith(b'RIFF') if len(header) >= 4 else False
                    except Exception as header_error:
                        logger.warning(
                            "audio_file_header_read_error",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            error=str(header_error)[:200],
                            message="Could not read audio file header"
                        )
                    
                    # Check file size limits
                    from shared.constants import MAX_REQUEST_BODY_SIZE
                    exceeds_size_limit = file_size > MAX_REQUEST_BODY_SIZE
                    
                    logger.info(
                        "audio_file_validation",
                        session_id=current_state.get("session_id", "unknown"),
                        audio_path=audio_path_str,
                        waited_seconds=waited,
                        file_size_bytes=file_size,
                        file_size_mb=round(file_size_mb, 2),
                        is_readable=is_readable,
                        is_valid_wav=is_valid_wav,
                        exceeds_size_limit=exceeds_size_limit,
                        max_size_mb=MAX_REQUEST_BODY_SIZE / (1024 * 1024),
                        message=f"Audio file validated: {file_size} bytes ({file_size_mb:.2f}MB), valid_wav={is_valid_wav}"
                    )
                    
                    # Early validation failures
                    if file_size == 0:
                        logger.error(
                            "zero_length_audio_file",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            message="Audio file exists but is zero-length (empty recording or permission issue)"
                        )
                        audio_path_str = None  # Will trigger "No audio recorded" error
                    elif not is_readable:
                        logger.error(
                            "audio_file_not_readable",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            message="Audio file exists but is not readable (permission issue)"
                        )
                        audio_path_str = None
                    elif exceeds_size_limit:
                        logger.error(
                            "audio_file_too_large",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            file_size_mb=round(file_size_mb, 2),
                            max_size_mb=MAX_REQUEST_BODY_SIZE / (1024 * 1024),
                            message=f"Audio file too large: {file_size_mb:.2f}MB exceeds {MAX_REQUEST_BODY_SIZE / (1024 * 1024):.2f}MB limit"
                        )
                        audio_path_str = None  # Will trigger error in handle_mic
                    elif not is_valid_wav:
                        logger.warning(
                            "audio_file_invalid_format",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            message="Audio file may be corrupted - doesn't start with RIFF header"
                        )
                        # Continue anyway - let transcription handle it
                    else:
                        logger.debug(
                            "audio_file_ready",
                            session_id=current_state.get("session_id", "unknown"),
                            audio_path=audio_path_str,
                            waited_seconds=waited,
                            message=f"Audio file ready and validated after {waited:.2f}s"
                        )
            else:
                # audio_path is None - Gradio might still be saving the file
                # Wait for Gradio to finish saving, then check if audio_path was updated
                logger.info(
                    "audio_path_none_waiting",
                    session_id=current_state.get("session_id", "unknown"),
                    message="audio_path is None, waiting for Gradio to save file"
                )
                
                # Wait up to 5 seconds for Gradio to save the file (increased from 1.0 for slower systems/platforms)
                max_wait_seconds = 5.0
                wait_interval = 0.1
                waited = 0.0
                
                # Also check if Gradio temp directory has any recent files
                gradio_temp_dir = os.environ.get("GRADIO_TEMP_DIR", GRADIO_TEMP_DIR)
                recent_files = []
                if os.path.exists(gradio_temp_dir):
                    try:
                        current_time = time.time()
                        # Look for files created in the last 10 seconds
                        for root, dirs, files in os.walk(gradio_temp_dir):
                            for file in files:
                                if file.endswith(('.wav', '.webm', '.mp3')):
                                    file_path = os.path.join(root, file)
                                    try:
                                        file_mtime = os.path.getmtime(file_path)
                                        if current_time - file_mtime < 10:  # Created in last 10 seconds
                                            recent_files.append(file_path)
                                    except Exception:
                                        pass
                    except Exception as e:
                        logger.debug(
                            "recent_files_check_error",
                            session_id=current_state.get("session_id", "unknown"),
                            error=str(e)[:200],
                            message="Could not check for recent files in Gradio temp directory"
                        )
                
                while waited < max_wait_seconds:
                    time.sleep(wait_interval)
                    waited += wait_interval
                    
                    # Re-check audio_path in case Gradio updated it
                    # Note: We can't directly access the mic component value here,
                    # but we wait in case the file is being saved and will be available
                    # The actual file check will happen in handle_mic if audio_path_str is still None
                
                if not audio_path_str:
                    # FALLBACK: If audio_path is None but we found recent files, use the most recent one
                    # This handles the case where Gradio saves the file but doesn't return the path
                    if recent_files:
                        logger.info(
                            "audio_path_fallback_attempt",
                            session_id=current_state.get("session_id", "unknown"),
                            recent_files_count=len(recent_files),
                            recent_files=recent_files[:3],  # Log first 3 for debugging
                            message=f"Attempting fallback: found {len(recent_files)} recent file(s)"
                        )
                        
                        # Sort by modification time (most recent first)
                        recent_files_with_mtime = []
                        for file_path in recent_files:
                            try:
                                if os.path.exists(file_path):  # Double-check file still exists
                                    mtime = os.path.getmtime(file_path)
                                    file_size = os.path.getsize(file_path)
                                    recent_files_with_mtime.append((mtime, file_path, file_size))
                            except Exception as e:
                                logger.debug(
                                    "fallback_file_check_error",
                                    session_id=current_state.get("session_id", "unknown"),
                                    file_path=file_path,
                                    error=str(e)[:200],
                                    message="Error checking fallback file"
                                )
                        
                        if recent_files_with_mtime:
                            recent_files_with_mtime.sort(reverse=True)  # Most recent first
                            most_recent_file = recent_files_with_mtime[0][1]
                            file_size = recent_files_with_mtime[0][2]
                            
                            # Verify the file exists and is readable (check again right before using)
                            if os.path.exists(most_recent_file):
                                if os.access(most_recent_file, os.R_OK):
                                    if file_size > 0:
                                        audio_path_str = most_recent_file
                                        logger.info(
                                            "audio_path_fallback_success",
                                            session_id=current_state.get("session_id", "unknown"),
                                            waited_seconds=waited,
                                            fallback_file=most_recent_file,
                                            file_size_bytes=file_size,
                                            file_size_mb=round(file_size / (1024 * 1024), 2),
                                            total_recent_files=len(recent_files),
                                            message=f"✅ Using fallback: most recent file found in Gradio temp directory ({most_recent_file})"
                                        )
                                    else:
                                        logger.warning(
                                            "audio_path_fallback_zero_size",
                                            session_id=current_state.get("session_id", "unknown"),
                                            fallback_file=most_recent_file,
                                            file_size=file_size,
                                            message="Fallback file exists but is zero-length"
                                        )
                                else:
                                    logger.warning(
                                        "audio_path_fallback_not_readable",
                                        session_id=current_state.get("session_id", "unknown"),
                                        fallback_file=most_recent_file,
                                        exists=True,
                                        readable=False,
                                        message="Fallback file exists but is not readable (permission issue)"
                                    )
                            else:
                                logger.warning(
                                    "audio_path_fallback_file_deleted",
                                    session_id=current_state.get("session_id", "unknown"),
                                    fallback_file=most_recent_file,
                                    message="Fallback file was deleted between detection and use (race condition)"
                                )
                        else:
                            logger.warning(
                                "audio_path_fallback_no_valid_files",
                                session_id=current_state.get("session_id", "unknown"),
                                recent_files_count=len(recent_files),
                                message="Found recent files but none were valid (deleted or unreadable)"
                            )
                    
                    if not audio_path_str:
                        logger.warning(
                            "audio_path_still_none",
                            session_id=current_state.get("session_id", "unknown"),
                            waited_seconds=waited,
                            gradio_temp_dir=gradio_temp_dir,
                            gradio_temp_dir_exists=os.path.exists(gradio_temp_dir),
                            recent_files_found=len(recent_files),
                            recent_files=recent_files[:5] if recent_files else None,  # Log first 5 recent files
                            message=f"audio_path is still None after waiting {waited:.2f}s - recording may have failed or user didn't record"
                        )
            
            # Process answer recording directly (first question is auto-triggered by webcam)
            s, audio, status_upd, mic_upd, chatbot_history, cam_upd, cam_status_upd, finish_upd, timeout_upd = handle_mic(
                audio_path_str, current_state, gr, progress=progress
            )
            
            # Extract audio from dict if needed (TTS audio for examiner)
            # Otherwise pass through as-is
            audio_out_valid = audio
            if isinstance(audio, dict):
                audio_out_valid = audio.get('name', audio.get('path', None))
            
            # Return student's recorded audio path for audio_out, TTS audio for examiner_audio
            # Use processing status instead of static status messages
            processing_status_upd = _calculate_processing_status(s)
            
            # Return audio paths as-is (Gradio handles None and invalid paths gracefully)
            return s, audio_path_str, processing_status_upd, mic_upd, chatbot_history, cam_upd, cam_status_upd, finish_upd, audio_out_valid, timeout_upd
        
        # Wire events
        parse_link_btn.click(handle_parse_and_show_chatbot, inputs=[professor_link_input, s],
                            outputs=[s, chatbot, professor_link_input, parse_link_btn, professor_link_section,
                                    verification_section, verification_status, consent_section, student_id_section,
                                    webcam_consent_section, exam_layout], 
                            concurrency_limit=2, concurrency_id=cpu_q)
        
        consent_checkbox.change(handle_consent_checkbox, inputs=[consent_checkbox, s],
                               outputs=[consent_section, student_id_section])
        
        student_id_verify_checkbox.change(handle_student_id_verify,
                                         inputs=[student_id_verify_checkbox, student_id_input, s],
                                         outputs=[s, student_id_input, student_id_verify_checkbox, 
                                                student_id_section, webcam_consent_section, exam_layout, student_id_status])
        
        # Wire webcam consent checkbox
        webcam_consent_checkbox.change(handle_webcam_consent_checkbox,
                                     inputs=[webcam_consent_checkbox, s],
                                     outputs=[s, webcam_consent_section, exam_layout])
        
        # Wire webcam stream
        proctor_cam.stream(_stream_proctor, inputs=[proctor_cam, s], 
                          outputs=[s, proctor_cam, proctor_status, connection_status, chatbot, mic, examiner_audio, progress_info, timeout_countdown, unified_status, queue_status])
        
        # Wire microphone recording - when Record is clicked, handle_mic processes answer
        mic.stop_recording(
            handle_mic_wrapper,
            inputs=[mic, s, unified_status],
            outputs=[
                s,
                audio_out,
                unified_status,
                mic,
                chatbot,
                proctor_cam,
                proctor_status,
                finish_btn,
                examiner_audio,
                timeout_countdown
            ],
            concurrency_limit=2,
            concurrency_id=cpu_q
        )

        # Finish & Download handler
        def _after_finish_ui(s, file_path, status_msg):
            """Wrapper for _after_finish_ui from exam.ui.handlers"""
            # Extract file path from Gradio File component input
            # Gradio File components can return dict with 'name' key or just a string path
            file_path_str = ''
            if isinstance(file_path, dict):
                file_path_str = file_path.get('name', file_path.get('path', ''))
            elif isinstance(file_path, str):
                file_path_str = file_path
            elif file_path is not None:
                file_path_str = str(file_path)
            
            # Validate file exists if path is provided
            if file_path_str and not os.path.exists(file_path_str):
                # If file doesn't exist, clear the path to prevent HTTP errors
                file_path_str = ''
            
            dependencies = {
                "ensure_state": ensure_state,
                "_calculate_processing_status": _calculate_processing_status,
            }
            return _after_finish_ui_handler(s, file_path_str, status_msg, gr, dependencies)

        finish_btn.click(
            finalize_and_export_encrypted,
            inputs=[s],
            outputs=[file_out, unified_status],
            concurrency_limit=4,
            concurrency_id=cpu_q
        ).then(
            _after_finish_ui,
            inputs=[s, file_out, unified_status],
            outputs=[proctor_cam, proctor_status, file_out, unified_status, file_integrity_checkbox],
            concurrency_limit=2,
            concurrency_id=cpu_q
        )
        
        # Handler for file integrity checkbox - show file only when checked
        def handle_file_integrity_checkbox(checked, current_state):
            """Wrapper for handle_file_integrity_checkbox from exam.ui.handlers"""
            return handle_file_integrity_checkbox_handler(checked, current_state, gr, ensure_state)
        
        # Wire checkbox change event
        file_integrity_checkbox.change(
            handle_file_integrity_checkbox,
            inputs=[file_integrity_checkbox, s],
            outputs=[s, file_out, finish_btn],  # Added finish_btn to keep it disabled
            concurrency_limit=1,
            concurrency_id=cpu_q
        )

# =========================
# Launch Configuration for Railway
# =========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 7860))
    demo.queue(default_concurrency_limit=16, max_size=256)
    
    # Set platform_provider here if we couldn't do it at import time
    if _PLATFORM_PROVIDER_SET_LATER:
        try:
            from shared.platform import set_default_platform_provider, RealPlatformProvider, get_default_platform_provider
            
            class ConfiguredPlatformProvider(RealPlatformProvider):
                def get_temp_dir(self) -> str:
                    return BASE_TEMP_DIR
            
            set_default_platform_provider(ConfiguredPlatformProvider())
        except Exception as e:
            logging.warning(
                f"Could not set platform_provider: {e}. "
                "Session temp dirs may use system temp instead of BASE_TEMP_DIR"
            )
    
    # VERIFICATION: Ensure platform_provider uses BASE_TEMP_DIR
    platform_provider_temp = None
    try:
        from shared.platform import get_default_platform_provider
        platform_provider_temp = get_default_platform_provider().get_temp_dir()
        if platform_provider_temp != BASE_TEMP_DIR:
            logging.warning(
                f"Platform provider temp dir ({platform_provider_temp}) != BASE_TEMP_DIR ({BASE_TEMP_DIR}). "
                "Session directories may use wrong base path."
            )
    except Exception as e:
        logging.warning(f"Could not verify platform_provider: {e}")
    
    # Use BASE_TEMP_DIR (SSOT) in allowed_paths
    # This covers all subdirectories: gradio/, vivaai/, vivaai_pdf_cache/
    allowed_paths = [os.path.abspath(BASE_TEMP_DIR)]
    
    # VERIFICATION: Ensure GRADIO_TEMP_DIR is in allowed_paths (it should be, as it's under BASE_TEMP_DIR)
    abs_gradio = os.path.abspath(GRADIO_TEMP_DIR)
    abs_allowed = os.path.abspath(allowed_paths[0])
    if not abs_gradio.startswith(abs_allowed):
        raise ValueError(
            f"GRADIO_TEMP_DIR ({abs_gradio}) is not under allowed_paths ({abs_allowed}). "
            f"This will cause file access issues."
        )
    
    # Log worker/process information for multi-worker debugging
    worker_info = {
        "pid": os.getpid(),
        "platform": "Railway" if os.getenv("RAILWAY_ENVIRONMENT") else ("HuggingFace" if os.getenv("SPACE_ID") else "Unknown"),
        "is_railway": bool(os.getenv("RAILWAY_ENVIRONMENT")),
        "is_huggingface": bool(os.getenv("SPACE_ID")),
    }
    
    logger.info(
        "gradio_launch_config",
        base_temp_dir=BASE_TEMP_DIR,
        gradio_temp_dir=GRADIO_TEMP_DIR,
        allowed_paths=allowed_paths,
        platform_provider_temp_dir=platform_provider_temp or "N/A",
        worker_pid=worker_info["pid"],
        platform=worker_info["platform"],
        is_railway=worker_info["is_railway"],
        is_huggingface=worker_info["is_huggingface"],
        gradio_temp_dir_in_allowed_paths=abs_gradio.startswith(abs_allowed),
        message="Launching Gradio with configured temp directory"
    )
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        max_threads=64,
        allowed_paths=allowed_paths
    )