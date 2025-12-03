# -*- coding: utf-8 -*-
# VivaAI Secure — Instructor Dashboard
# Decrypt and analyze encrypted exam transcripts (.enc files)

import os
from typing import Optional, Tuple, Dict, Any, List
from contextvars import ContextVar
from dotenv import load_dotenv
import structlog
import gradio as gr

# Load environment variables BEFORE importing modules that use VIVA_HMAC_SECRET
# This ensures .env file is loaded before shared.cryptography, shared.url_encoding,
# and other modules try to read VIVA_HMAC_SECRET at import time
load_dotenv()

# =========================
# Startup Validation
# =========================
# Validate required environment variables (fail fast in production)
environment = os.getenv("ENVIRONMENT", "development").lower()
if environment == "production":
    from shared.config_validation import validate_required_env_vars
    is_valid, error = validate_required_env_vars(["VIVA_HMAC_SECRET"])
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
    if missing:
        print(f"⚠️  Warning: Missing environment variables: {', '.join(missing)}")
        print("   Set them in .env file for full functionality.")
        print("   See .env.example for a template.")

# =========================
# Shared Module Imports
# =========================
# Import shared utilities (cryptography, URL encoding, file utilities)
from shared.cryptography import decrypt_bytes
from shared.file_utils import _lock_file, _unlock_file
from shared.config_parsing import (
    parse_professor_link_and_setup as _parse_professor_link_and_setup_shared,
    parse_passphrase_from_url,
)
from dash.decryption import instructor_decrypt, _check_and_mark_otet
from dash.parsing import _grab, _parse_plaintext_fields, _parse_rubric_scores
from dash.csv_export import _safe_path, batch_csv_summarize

# =========================
# Module Imports (Refactored)
# =========================
# Import configuration and logging
from dash.config import logger, TRANSCRIPT_CACHE_TIMEOUT_SECONDS

# Import cache management
from dash.cache import (
    get_cache_entry, set_cache_entry, _is_cache_entry_valid,
    _cleanup_expired_cache, _obfuscate_session_id
)

# Import grade adjustment functions
from dash.grade_adjustment import (
    _calculate_confidence_score, _statistical_normalization,
    _percentile_curving, _confidence_adjustment
)

# Import UI helpers and handlers
from dash.ui.helpers import convert_csv_to_excel, get_csv_column_list
from dash.ui.handlers import (
    handle_parse_instructor_passphrase,
    handle_file_upload,
    handle_do_csv,
    handle_batch_decrypt,
    handle_on_row_select,
)

# Context Variables (Thread-Safe - Isolated per Request)
# These replace global variables to make code thread-safe for concurrent users
course_id_ctx: ContextVar[str] = ContextVar('course_id', default="UNKNOWN")
exam_id_ctx: ContextVar[str] = ContextVar('exam_id', default="UNKNOWN")

# Legacy global variables (fallback defaults)
COURSE_ID = os.getenv("VIVA_COURSE_ID", "UNKNOWN")
EXAM_ID   = os.getenv("VIVA_EXAM_ID",   "UNKNOWN")

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()  # JSON output for production
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Get logger instance
logger = structlog.get_logger()

# HMAC secret for sealing the AES-GCM payload
# Note: load_dotenv() is called earlier (before imports) to ensure .env is loaded
HMAC_SECRET = os.getenv("VIVA_HMAC_SECRET")

# Validate HMAC_SECRET with safe fallback for development
# CONFIGURATION & SECRETS DISCIPLINE: Development fallback meets minimum length (Principle #23)
if not HMAC_SECRET:
    # In development, allow with warning
    if os.getenv("ENVIRONMENT", "development").lower() == "development":
        print("⚠️  WARNING: VIVA_HMAC_SECRET not set. Using development mode.")
        print("⚠️  Set VIVA_HMAC_SECRET in .env for production.")
        logger.warning(
            "hmac_secret_not_set",
            message="VIVA_HMAC_SECRET not set. Using development mode.",
            action="using_default_fallback",
            environment="development"
        )
        # Development-only fallback (meets minimum 32-character requirement for security validation)
        # SECURITY: This fallback is ONLY used in development. Production fails hard if secret is missing.
        HMAC_SECRET = "DEVELOPMENT-ONLY-CHANGE-ME-MIN-32-CHARS-FOR-TESTING"
    else:
        # In production, fail hard
        logger.error(
            "hmac_secret_missing_production",
            message="VIVA_HMAC_SECRET must be set in production",
            environment="production",
            action="failing_hard"
        )
        raise ValueError(
            "VIVA_HMAC_SECRET must be set in production. "
            "Check your .env file or environment variables."
        )

# Validate secret strength
if HMAC_SECRET and len(HMAC_SECRET) < 32:
    print("⚠️  WARNING: VIVA_HMAC_SECRET should be at least 32 characters for security.")
    logger.warning(
        "hmac_secret_weak",
        message="VIVA_HMAC_SECRET should be at least 32 characters for security",
        secret_length=len(HMAC_SECRET),
        action="warn_user"
    )

def parse_professor_link_and_setup(url: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Parse professor's link URL and automatically set up the examination.
    Returns: (success: bool, status_message: str, state_updates: dict)
    Uses context variables (thread-safe) instead of global variables.
    
    This is a wrapper around the shared parse_professor_link_and_setup function
    that provides dash-specific configuration (PDF optional, no PDF loading, minimal context).
    """
    # Define callbacks for dash-specific operations
    def set_context_callback(config_dict):
        """Set minimal context variables (only course_id and exam_id for dash)"""
        course_id_ctx.set(config_dict["course_id"])
        exam_id_ctx.set(config_dict["exam_id"])
    
    def set_globals_callback(config_dict):
        """Set global variables for backward compatibility"""
        global COURSE_ID, EXAM_ID
        COURSE_ID = config_dict["course_id"]
        EXAM_ID = config_dict["exam_id"]
    
    # Call shared function with dash mode parameters and callbacks
    return _parse_professor_link_and_setup_shared(
        url,
        require_pdf=False,  # PDF is optional for dash
        load_pdf=False,  # Don't load PDF in dash mode
        set_exam_context=False,  # Don't set full exam context in dash mode
        default_decryption="sonic",  # Default decryption for dash
        set_context_callback=set_context_callback,
        set_globals_callback=set_globals_callback
    )

# =========================
# Dependency Injection System
# =========================

def _build_dash_dependencies():
    """
    Build dependencies dictionary for dash UI handlers.
    This function collects all dependencies needed by the extracted handler functions.
    """
    return {
        # Core business logic functions
        "parse_professor_link_and_setup": parse_professor_link_and_setup,
        "batch_csv_summarize": batch_csv_summarize,
        "instructor_decrypt": instructor_decrypt,
        "_parse_plaintext_fields": _parse_plaintext_fields,
        "_parse_rubric_scores": _parse_rubric_scores,
        "_safe_path": _safe_path,
        
        # Grade adjustment functions
        "_statistical_normalization": _statistical_normalization,
        "_percentile_curving": _percentile_curving,
        "_confidence_adjustment": _confidence_adjustment,
        "_calculate_confidence_score": _calculate_confidence_score,
        
        # Cache management functions
        "_cleanup_expired_cache": _cleanup_expired_cache,
        "_is_cache_entry_valid": _is_cache_entry_valid,
        "_obfuscate_session_id": _obfuscate_session_id,
        "get_cache_entry": get_cache_entry,
        "set_cache_entry": set_cache_entry,
        
        # Helper functions
        "convert_csv_to_excel": convert_csv_to_excel,
        "get_csv_column_list": get_csv_column_list,
        
        # Logger
        "logger": logger,
        
        # Constants
        "TRANSCRIPT_CACHE_TIMEOUT_SECONDS": TRANSCRIPT_CACHE_TIMEOUT_SECONDS,
    }
    
    # FERPA COMPLIANCE: Add RBAC functions if enabled (optional - preserves backward compatibility)
    if os.getenv("FERPA_RBAC_ENABLED", "false").lower() == "true":
        try:
            from shared.ferpa_rbac import require_role, get_user_role, can_access_student_data
            from shared.ferpa_audit import log_ferpa_access
            deps["require_role"] = require_role
            deps["get_user_role"] = get_user_role
            deps["can_access_student_data"] = can_access_student_data
            deps["log_ferpa_access"] = log_ferpa_access
        except ImportError:
            # RBAC modules not available - continue without RBAC (backward compatibility)
            pass
    
    return deps

# =========================
# Wrapper Functions (Dependency Injection)
# =========================

def handle_parse_instructor_wrapper(url):
    """Wrapper for handle_parse_instructor_passphrase with dependency injection."""
    dependencies = _build_dash_dependencies()
    return handle_parse_instructor_passphrase(gr, dependencies, url)

def handle_file_upload_wrapper(files):
    """Wrapper for handle_file_upload with dependency injection."""
    dependencies = _build_dash_dependencies()
    return handle_file_upload(gr, dependencies, files)

def handle_do_csv_wrapper(files, passphrase, export_format):
    """Wrapper for handle_do_csv with dependency injection."""
    dependencies = _build_dash_dependencies()
    return handle_do_csv(gr, dependencies, files, passphrase, export_format)

def handle_batch_decrypt_wrapper(files, passphrase,
                                  show_verdict, show_session_id, show_grade, show_duration, 
                                  show_rubric_sub_scores, show_course_name, show_section,
                                  show_video_enabled, show_video_verdict, show_video_flags,
                                  show_audio_enabled, show_audio_verdict, show_audio_flags, show_stylometric,
                                  show_percentile, show_zscore, show_flag_extremes,
                                  enable_adjustment, method_statistical, method_percentile, method_confidence,
                                  target_mean, target_std, top_pct, range_a, range_b, range_c,
                                  conf_threshold, conf_factor):
    """Wrapper for handle_batch_decrypt with dependency injection."""
    dependencies = _build_dash_dependencies()
    return handle_batch_decrypt(gr, dependencies, files, passphrase,
                                show_verdict, show_session_id, show_grade, show_duration,
                                show_rubric_sub_scores, show_course_name, show_section,
                                show_video_enabled, show_video_verdict, show_video_flags,
                                show_audio_enabled, show_audio_verdict, show_audio_flags, show_stylometric,
                                show_percentile, show_zscore, show_flag_extremes,
                                enable_adjustment, method_statistical, method_percentile, method_confidence,
                                target_mean, target_std, top_pct, range_a, range_b, range_c,
                                conf_threshold, conf_factor)

def handle_on_row_select_wrapper(evt, df=None):
    """Wrapper for handle_on_row_select with dependency injection."""
    dependencies = _build_dash_dependencies()
    # Gradio's .select() passes the event, and if dataframe is in inputs, passes its value
    # Handle case where df might be None or in wrong format
    import pandas as pd
    
    # If df is None, try to get from event
    if df is None:
        if hasattr(evt, 'value'):
            df = evt.value
        elif hasattr(evt, 'data'):
            df = evt.data
        elif hasattr(evt, 'target') and hasattr(evt.target, 'value'):
            df = evt.target.value
    
    # Convert to DataFrame if it's not already one (Gradio may pass list/dict)
    if df is not None and not isinstance(df, pd.DataFrame):
        try:
            # Handle list of dicts (common Gradio format for Dataframe)
            if isinstance(df, list) and len(df) > 0:
                df = pd.DataFrame(df)
            else:
                df = pd.DataFrame(df)
        except Exception:
            df = None
    
    return handle_on_row_select(gr, dependencies, evt, df)

# =========================
# UI (Instructor Dashboard)
# =========================
# Shared concurrency bucket
cpu_q = "cpu"

with gr.Blocks(title="VivaAI Secure - Instructor Dashboard") as demo:
    with gr.Tab("Instructor Dashboard"):
        gr.Markdown("### 📊 Instructor Dashboard")
        gr.Markdown("Upload and process encrypted viva transcripts (.enc files) for analysis and grading.")
        
        # Setup Passphrase Section (Phase 1: Link Parsing) - Initially visible
        with gr.Column(visible=True) as setup_passphrase_section:
            with gr.Accordion("🔑 Setup Passphrase", open=True):
                with gr.Row():
                    # Column 1: Professor's Link
                    with gr.Column(scale=3):
                        instructor_link_input = gr.Textbox(
                            label="Professor's Link",
                            placeholder="Paste exam configuration URL here...",
                            lines=2,
                            value="",
                            info="Paste the professor's exam link to automatically extract the decryption passphrase"
                        )
                    
                    # Column 2: Parse & Set Button
                    with gr.Column(scale=1):
                        instructor_parse_btn = gr.Button("🔗 Parse & Set Passphrase", variant="primary")
                        instructor_parse_status = gr.Markdown("", visible=True)
        
        # Exam Info Display Section (Phase 2: After Parse) - Initially hidden
        with gr.Column(visible=False) as exam_info_section:
            exam_info_display = gr.Markdown(
                value="",
                visible=True
            )
        
        # Upload Section (Phase 2: After Parse) - Initially hidden
        with gr.Column(visible=False) as upload_section:
            gr.Markdown("---")
            enc_multi_shared = gr.Files(
                label="Upload .enc files", 
                file_count="multiple",
                height=200
            )
        
        # Hidden passphrase field (internal use only, not displayed for security)
        pass_in_shared = gr.Textbox(
            label="",
            type="password", 
            value="", 
            visible=False,
            interactive=False
        )
        
        # Tabs Container (Phase 3: After File Upload) - Initially hidden
        with gr.Tabs(visible=False) as tabs_container:
                # Batch CSV Summary Tab
                with gr.Tab("📄 CSV Summary"):
                    gr.Markdown("**Generate CSV/Excel summary from uploaded encrypted files.**")
                    with gr.Row():
                        make_csv = gr.Button("📄 Build Summary", variant="primary")
                        export_format_csv = gr.Dropdown(
                            choices=["CSV", "Excel (.xlsx)"],
                            value="CSV",
                            label="Export Format",
                            interactive=True
                        )
                    csv_status = gr.Markdown("")
                    csv_progress = gr.Markdown("", visible=False)
                    csv_file = gr.File(label="Download Summary File", interactive=False)
                    
                    make_csv.click(
                        handle_do_csv_wrapper,
                        inputs=[enc_multi_shared, pass_in_shared, export_format_csv],
                        outputs=[csv_status, csv_progress, csv_file],
                        concurrency_limit=2,
                        concurrency_id=cpu_q
                    )

                # Batch Decryption Tab
                with gr.Tab("🔓 Batch Decrypt"):
                    # FERPA COMPLIANCE: Display compliance notice in collapsed accordion
                    with gr.Accordion("⚠️ FERPA Compliance Notice", open=False):
                        gr.Markdown("""
                        **You are accessing student educational records.**
                        - Only access records for students in courses you teach
                        - Session IDs are obfuscated to protect privacy (showing only last 4 characters)
                        - Transcript cache expires after 1 hour to limit data retention
                        - Do not share or export data to unauthorized parties
                        - All access should be logged for compliance purposes (recommended)
                        
                        **By proceeding, you acknowledge:**
                        - You have legitimate educational interest in this data
                        - You will comply with FERPA regulations
                        - You understand unauthorized access is prohibited
                        """)
                    
                    # Display Filters (inside Batch Decrypt tab) - Organized with sub-accordions
                    with gr.Accordion("🔍 Display Filters", open=False):
                        gr.Markdown("Select columns to display. CSV Summary always includes all 46 columns.")
                        
                        with gr.Row():
                            # Column 1: Basic Info & Rubric (grouped)
                            with gr.Column():
                                with gr.Accordion("📋 Basic Information", open=True):
                                    filter_show_verdict = gr.Checkbox(label="Verdict", value=True, interactive=True)
                                    filter_show_session_id = gr.Checkbox(label="Session ID", value=True, interactive=True)
                                    filter_show_grade = gr.Checkbox(label="Grade", value=True, interactive=True)
                                    filter_show_duration = gr.Checkbox(label="Duration", value=False, interactive=True)
                                    filter_show_course_name = gr.Checkbox(label="Course/Exam ID", value=True, interactive=True)
                                    filter_show_section = gr.Checkbox(label="Section ID", value=True, interactive=True)
                                
                                with gr.Accordion("📊 Rubric & Analysis", open=False):
                                    filter_show_rubric_sub_scores = gr.Checkbox(label="Rubric Sub-Scores", value=False, interactive=True)
                                    filter_show_percentile = gr.Checkbox(label="Percentile Rank", value=False, interactive=True)
                                    filter_show_zscore = gr.Checkbox(label="Z-Score", value=False, interactive=True)
                                    filter_show_flag_extremes = gr.Checkbox(label="Flag Extremes", value=True, interactive=True)
                            
                            # Column 2: Proctoring (grouped)
                            with gr.Column():
                                with gr.Accordion("📹 Video Proctoring", open=False):
                                    filter_show_video_enabled = gr.Checkbox(label="Enabled", value=False, interactive=True)
                                    filter_show_video_verdict = gr.Checkbox(label="Verdict", value=True, interactive=True)
                                    filter_show_video_flags = gr.Checkbox(label="Flags (AWAY, MULTI_FACE, etc.)", value=False, interactive=True)
                                
                                with gr.Accordion("🎤 Audio Analysis", open=False):
                                    filter_show_audio_enabled = gr.Checkbox(label="Enabled", value=False, interactive=True)
                                    filter_show_audio_verdict = gr.Checkbox(label="Verdict", value=True, interactive=True)
                                    filter_show_audio_flags = gr.Checkbox(label="Flags (Voiceprint, Speech Rate, etc.)", value=False, interactive=True)
                                    filter_show_stylometric = gr.Checkbox(label="Stylometric Flags", value=False, interactive=True)
                    
                    # Grade Adjustment Settings (inside Batch Decrypt tab) - Compact layout
                    with gr.Accordion("📊 Grade Adjustment Settings", open=False):
                        gr.Markdown("Apply statistical adjustments to AI-generated grades. Original grades are preserved.")
                        
                        enable_grade_adjustment = gr.Checkbox(
                            label="Enable Grade Adjustment", 
                            value=False, 
                            interactive=True
                        )
                        
                        with gr.Row():
                            with gr.Column():
                                gr.Markdown("**Methods**")
                                adjustment_method_statistical = gr.Checkbox(
                                    label="Statistical Normalization", 
                                    value=False, 
                                    interactive=True
                                )
                                adjustment_method_percentile = gr.Checkbox(
                                    label="Percentile-Based Curving", 
                                    value=False, 
                                    interactive=True
                                )
                                adjustment_method_confidence = gr.Checkbox(
                                    label="Confidence-Based Adjustment", 
                                    value=False, 
                                    interactive=True
                                )
                            
                            with gr.Column():
                                gr.Markdown("**Statistical Normalization**")
                                normalize_target_mean = gr.Number(
                                    label="Target Mean",
                                    value=75.0,
                                    minimum=0,
                                    maximum=100,
                                    step=0.5,
                                    interactive=True
                                )
                                normalize_target_std = gr.Number(
                                    label="Target Std Dev",
                                    value=12.0,
                                    minimum=1,
                                    maximum=50,
                                    step=0.5,
                                    interactive=True
                                )
                                
                                gr.Markdown("**Percentile Curving**")
                                curve_top_pct = gr.Number(
                                    label="Top %",
                                    value=10.0,
                                    minimum=0,
                                    maximum=50,
                                    step=1,
                                    interactive=True
                                )
                                
                                with gr.Row():
                                    curve_grade_range_a = gr.Textbox(
                                        label="A Range",
                                        value="90-100",
                                        interactive=True,
                                        scale=1
                                    )
                                    curve_grade_range_b = gr.Textbox(
                                        label="B Range",
                                        value="80-89",
                                        interactive=True,
                                        scale=1
                                    )
                                    curve_grade_range_c = gr.Textbox(
                                        label="C Range",
                                        value="70-79",
                                        interactive=True,
                                        scale=1
                                    )
                            
                            with gr.Column():
                                gr.Markdown("**Confidence Adjustment**")
                                confidence_threshold = gr.Number(
                                    label="Low Confidence Threshold (%)",
                                    value=70.0,
                                    minimum=0,
                                    maximum=100,
                                    step=1,
                                    interactive=True
                                )
                                confidence_adjustment_factor = gr.Number(
                                    label="Adjustment Factor",
                                    value=0.95,
                                    minimum=0.5,
                                    maximum=1.0,
                                    step=0.01,
                                    interactive=True
                                )
                    
                    batch_decrypt_btn = gr.Button("🔓 Decrypt All Files", variant="primary")
                    batch_decrypt_status = gr.Markdown("")
                    batch_decrypt_results = gr.Dataframe(
                        label="Decryption Results (Read-Only)",
                        interactive=False,  # Security: Prevent accidental modification of decryption results
                        wrap=True,
                        type="pandas"
                    )
                    gr.Markdown("**💡 Tip:** Click on a row in the results table to view the decrypted transcript below.")
                    selected_file_name = gr.Textbox(label="Selected File", visible=False)
                    batch_decrypt_transcript = gr.Code(
                        label="Decrypted Transcript",
                        language="markdown",
                        visible=False,
                        interactive=False
                    )
                    
                    batch_decrypt_btn.click(
                        handle_batch_decrypt_wrapper,
                        inputs=[
                            enc_multi_shared, pass_in_shared,
                            filter_show_verdict, filter_show_session_id, filter_show_grade, 
                            filter_show_duration, filter_show_rubric_sub_scores, filter_show_course_name, filter_show_section,
                            filter_show_video_enabled, filter_show_video_verdict, filter_show_video_flags,
                            filter_show_audio_enabled, filter_show_audio_verdict, filter_show_audio_flags, filter_show_stylometric, 
                            filter_show_percentile, filter_show_zscore, 
                            filter_show_flag_extremes,
                            enable_grade_adjustment, adjustment_method_statistical, adjustment_method_percentile, 
                            adjustment_method_confidence,
                            normalize_target_mean, normalize_target_std, curve_top_pct, 
                            curve_grade_range_a, curve_grade_range_b, curve_grade_range_c,
                            confidence_threshold, confidence_adjustment_factor
                        ],
                        outputs=[batch_decrypt_status, batch_decrypt_results, selected_file_name, batch_decrypt_transcript],
                        concurrency_limit=2,
                        concurrency_id=cpu_q
                    )
                    
                    # Handle row selection to show transcript
                    batch_decrypt_results.select(
                        handle_on_row_select_wrapper,
                        inputs=[batch_decrypt_results],
                        outputs=[selected_file_name, batch_decrypt_transcript]
                    )
        
        # Wire the parse button
        instructor_parse_btn.click(
            handle_parse_instructor_wrapper,
            inputs=[instructor_link_input],
            outputs=[
                pass_in_shared,  # Set passphrase internally
                exam_info_display,  # Show exam info
                setup_passphrase_section,  # Hide setup section
                exam_info_section,  # Show exam info section
                upload_section,  # Show upload section
                instructor_parse_status,  # Show status message
                instructor_link_input,  # Clear input
                instructor_parse_btn  # Disable button
            ],
            concurrency_limit=2,
            concurrency_id=cpu_q
        )
        
        # Wire file upload change event
        enc_multi_shared.change(
            handle_file_upload_wrapper,
            inputs=[enc_multi_shared],
            outputs=[tabs_container],
            concurrency_limit=2,
            concurrency_id=cpu_q
        )

# Launch
if __name__ == "__main__":
    # =========================
    # Launch Configuration for Railway
    # =========================
    port = int(os.getenv("PORT", 7862))  # Default port 7862 for dash.py
    
    # Configure file upload settings for Railway deployment
    # Create a temp directory for file uploads if it doesn't exist
    upload_dir = os.getenv("GRADIO_TEMP_DIR", os.path.join(os.getcwd(), "gradio_temp"))
    os.makedirs(upload_dir, exist_ok=True)
    
    # Ensure the directory is writable
    if not os.access(upload_dir, os.W_OK):
        logger.warning(f"Upload directory {upload_dir} is not writable, using system temp directory")
        upload_dir = None
    
    demo.queue(default_concurrency_limit=16, max_size=256)
    
    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        share=False,
        show_error=True,
        pwa=True,
        # File upload configuration for Railway
        # Note: In Gradio 5.x, file uploads are handled automatically
        # If you see 502 errors on /gradio_api/upload, it may be due to:
        # 1. Railway reverse proxy timeout (default 60s) - try smaller files
        # 2. Request body size limits - Railway may have limits
        # 3. Insufficient resources - check Railway service limits
        # The upload_dir created above ensures temp files have a writable location
    )