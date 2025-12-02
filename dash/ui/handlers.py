"""
UI event handlers for dash.ipynb.

This module contains all Gradio event handlers for the instructor dashboard UI.
All handlers use dependency injection pattern for testability and reusability.
"""

import os
import json
import time
import threading
from typing import Tuple, Dict, Any, List, Optional, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, as_completed

if TYPE_CHECKING:
    import gradio as gr

import pandas as pd
import numpy as np
from cryptography.exceptions import InvalidTag

from dash.config import logger
from dash.cache import (
    get_cache_entry, set_cache_entry, _is_cache_entry_valid,
    _cleanup_expired_cache, _obfuscate_session_id
)
from shared.pii_obfuscation import decrypt_receipt_core
from dash.grade_adjustment import apply_grade_adjustments
from dash.ui.helpers import convert_csv_to_excel, get_csv_column_list
from shared.handler_configs import BatchDecryptConfig
from shared.validation import validate_files_uploaded, validate_passphrase, validate_url
from shared.error_formatter import format_user_error, format_status_message
from shared.error_info import (
    invalid_path_error, file_not_found_error, file_too_large_error,
    file_size_error, decryption_failed_error, decryption_error,
    invalid_file_format_error, parsing_error, unexpected_error
)

# Module-level variable to store the current batch decrypt results dataframe
# This is needed because Gradio's .select() event doesn't reliably pass the dataframe value
_current_batch_decrypt_df = None


def handle_parse_instructor_passphrase(
    gr_module,
    dependencies: Dict[str, Any],
    url: str
) -> Tuple:
    """
    Handle parsing passphrase from professor's link.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with parse_professor_link_and_setup
        url: Professor's link URL
        
    Returns:
        Tuple of Gradio updates for all UI components
    """
    from shared.validation import validate_url
    
    parse_professor_link_and_setup = dependencies["parse_professor_link_and_setup"]
    
    # Use standardized validation
    url_validation = validate_url(url, url_type="professor's link")
    if not url_validation.is_valid:
        return (
            gr_module.update(value=""),  # pass_in_shared
            gr_module.update(value=""),  # exam_info_display
            gr_module.update(visible=True),  # setup_passphrase_section
            gr_module.update(visible=False),  # exam_info_section
            gr_module.update(visible=False),  # upload_section
            gr_module.update(value=f"### {url_validation.to_formatted_message()}", visible=True),  # instructor_parse_status
            gr_module.update(),  # instructor_link_input (keep as is)
            gr_module.update(interactive=True)  # instructor_parse_btn (keep enabled)
        )
    
    # Use parse_professor_link_and_setup to get full exam info
    success, status_msg, state_updates = parse_professor_link_and_setup(url)
    
    if success:
        # Extract values from state_updates
        course_id = state_updates.get("course_id", "")
        exam_id = state_updates.get("exam_id", "")
        section_id = state_updates.get("section_id", "UNKNOWN")
        passphrase = state_updates.get("passphrase", "")
        
        # Build exam info display
        exam_info_text = f"""### ✓ **Exam Configured**
- **Course ID:** `{course_id}`
- **Exam ID:** `{exam_id}`
- **Section:** `{section_id}`
"""
        
        return (
            gr_module.update(value=passphrase),  # Populate pass_in_shared
            gr_module.update(value=exam_info_text),  # Show exam info
            gr_module.update(visible=False),  # Hide setup_passphrase_section
            gr_module.update(visible=True),  # Show exam_info_section
            gr_module.update(visible=True),  # Show upload_section
            gr_module.update(value="✅ " + status_msg, visible=True),  # Show success status
            gr_module.update(value=""),  # Clear instructor_link_input
            gr_module.update(interactive=False)  # Disable instructor_parse_btn
        )
    else:
        # On error, keep setup visible
        return (
            gr_module.update(value=""),  # Keep passphrase field empty on error
            gr_module.update(value=""),  # Clear exam_info_display
            gr_module.update(visible=True),  # Keep setup_passphrase_section visible
            gr_module.update(visible=False),  # Keep exam_info_section hidden
            gr_module.update(visible=False),  # Keep upload_section hidden
            gr_module.update(value=status_msg, visible=True),  # Show error status
            gr_module.update(),  # Keep instructor_link_input (for user to fix)
            gr_module.update(interactive=True)  # Keep instructor_parse_btn enabled
        )


def handle_file_upload(
    gr_module,
    dependencies: Dict[str, Any],
    files: List
) -> Any:
    """
    Show tabs when files are uploaded.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary (unused but kept for consistency)
        files: List of uploaded files
        
    Returns:
        Gradio update to show/hide tabs container
    """
    if files and len(files) > 0:
        return gr_module.update(visible=True)
    else:
        return gr_module.update(visible=False)


def handle_do_csv(
    gr_module,
    dependencies: Dict[str, Any],
    files: List,
    passphrase: str,
    export_format: str
) -> Tuple:
    """
    Handle CSV/Excel export from uploaded files.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with batch_csv_summarize, convert_csv_to_excel
        files: List of uploaded files
        passphrase: Decryption passphrase
        export_format: Export format ("CSV" or "Excel (.xlsx)")
        
    Returns:
        Tuple of (status_update, progress_update, file_path)
    """
    batch_csv_summarize = dependencies["batch_csv_summarize"]
    get_csv_column_list_func = dependencies.get("get_csv_column_list", get_csv_column_list)
    
    # CSV Summary always includes all 56 columns regardless of display filters
    # Use standardized validation
    files_validation = validate_files_uploaded(files)
    if not files_validation.is_valid:
        return (
            gr_module.update(value=f"### {files_validation.to_formatted_message()}", visible=True),
            gr_module.update(value="", visible=False),
            None
        )
    
    passphrase_validation = validate_passphrase(passphrase)
    if not passphrase_validation.is_valid:
        return (
            gr_module.update(value=f"### {passphrase_validation.to_formatted_message()}", visible=True),
            gr_module.update(value="", visible=False),
            None
        )
    
    # Show progress
    status_msg = f"⏳ Processing {len(files)} files... Please wait."
    
    # FERPA COMPLIANCE: Build instructor context for audit logging (optional RBAC check)
    instructor_context = None
    require_role_fn = dependencies.get("require_role")
    log_ferpa_access_fn = dependencies.get("log_ferpa_access")
    
    # Try to get instructor identification for audit logging
    if require_role_fn and log_ferpa_access_fn:
        try:
            from shared.ferpa_rbac import UserRole
            # Dashboard is instructor-only, so set default role
            state_for_rbac = {"user_role": "INSTRUCTOR"}
            
            # Verify instructor access (optional check - graceful fallback if fails)
            if require_role_fn(state_for_rbac, UserRole.INSTRUCTOR, "csv_export", log_ferpa_access_fn):
                instructor_context = {
                    "instructor_id": "authenticated_instructor",
                    "role": "INSTRUCTOR"
                }
        except Exception:
            # Graceful fallback: continue without instructor context if RBAC check fails
            # This preserves backward compatibility
            pass
    
    # Process files (generate CSV with all data first)
    # Pass instructor_context for FERPA audit logging (optional parameter)
    path, msg = batch_csv_summarize(files, passphrase, instructor_context=instructor_context)
    
    # Filter columns based on standard column list
    if path:
        try:
            # Read CSV
            df = pd.read_csv(path)
            
            # Include ALL columns by default - all 56 columns from batch_csv_summarize
            all_columns = get_csv_column_list_func()
            
            # Keep only columns that exist in the dataframe (handle missing columns gracefully)
            available_columns = [col for col in all_columns if col in df.columns]
            
            # If some expected columns are missing, add them with empty values
            missing_columns = [col for col in all_columns if col not in df.columns]
            if missing_columns:
                for col in missing_columns:
                    df[col] = ""  # Add missing columns with empty values
                available_columns = all_columns  # Now all columns are available
            
            df_filtered = df[available_columns]
            
            # Write filtered CSV
            df_filtered.to_csv(path, index=False)
            
        except Exception as e:
            # SECURITY: Sanitize error message - don't expose implementation details
            logger.warning(
                "csv_filtering_failed",
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            msg += " (Warning: Column filtering encountered an issue)"
    
    # Convert to Excel if requested
    if export_format == "Excel (.xlsx)" and path:
        try:
            convert_csv_to_excel_func = dependencies.get("convert_csv_to_excel", convert_csv_to_excel)
            path = convert_csv_to_excel_func(path)
            msg = msg.replace("CSV", "Excel file")
        except ImportError:
            msg += " (Excel export requires 'openpyxl' package. Install with: pip install openpyxl)"
        except Exception as e:
            # SECURITY: Sanitize error message - don't expose implementation details
            logger.warning(
                "excel_export_failed",
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            msg += " (Excel export failed. Please try CSV format instead.)"
    
    return (
        gr_module.update(value=msg, visible=True),
        gr_module.update(value="", visible=False),
        path
    )


def _process_single_file(
    fobj,
    passphrase: str,
    dependencies: Dict[str, Any],
    lock=None
) -> Tuple:
    """
    Process a single file with better error handling.
    
    Internal helper function used by handle_batch_decrypt.
    
    Args:
        fobj: File object to process
        passphrase: Decryption passphrase
        dependencies: Dependencies dictionary with required functions
        lock: Optional threading lock for thread safety
        
    Returns:
        Tuple of (filename, plaintext, summary_md, success, error_info, grade)
    """
    _safe_path = dependencies["_safe_path"]
    instructor_decrypt = dependencies["instructor_decrypt"]
    _parse_plaintext_fields = dependencies["_parse_plaintext_fields"]
    
    # FERPA COMPLIANCE: Get RBAC functions if available
    require_role_fn = dependencies.get("require_role")
    state_for_rbac = {"user_role": "INSTRUCTOR"}  # Dashboard is instructor-only
    
    filename = None
    error_info = None
    grade = None
    
    try:
        # Get file path with specific error handling
        fpath = _safe_path(fobj)
        if not fpath:
            error_info = invalid_path_error()
            return (str(fobj), None, None, False, error_info, None)
        
        if not os.path.exists(fpath):
            filename = os.path.basename(fpath) if fpath else str(fobj)
            error_info = file_not_found_error(filename)
            return (filename, None, None, False, error_info, None)
        
        filename = os.path.basename(fpath)
        
        # Check file size before processing
        try:
            from shared.constants import MAX_FILE_SIZE  # SSOT - Principle #2
            file_size = os.path.getsize(fpath)
            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / (1024 * 1024)
                error_info = file_too_large_error(size_mb, max_mb=MAX_FILE_SIZE / (1024 * 1024))
                return (filename, None, None, False, error_info, None)
        except (OSError, IOError) as e:
            # SECURITY: Sanitize error message - don't expose file system details
            logger.warning(
                "file_size_check_failed",
                filename=filename,
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            error_info = file_size_error("File size check failed")
            return (filename, None, None, False, error_info, None)
        
        # Decrypt with specific error handling
        try:
            # FERPA COMPLIANCE: Pass RBAC functions if available
            plaintext, summary_md = instructor_decrypt(
                fpath, 
                passphrase, 
                logger=logger,
                require_role_fn=require_role_fn,
                state=state_for_rbac
            )
        except InvalidTag:
            error_info = decryption_failed_error()
            return (filename, None, None, False, error_info, None)
        except (json.JSONDecodeError, ValueError) as e:
            # SECURITY: Sanitize error message - don't expose parsing details
            logger.warning(
                "file_format_error",
                filename=filename,
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            error_info = invalid_file_format_error("Invalid file format")
            return (filename, None, None, False, error_info, None)
        except Exception as e:
            # SECURITY: Sanitize error message - don't expose decryption details
            logger.warning(
                "decryption_error",
                filename=filename,
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            error_info = decryption_error("Decryption failed")
            return (filename, None, None, False, error_info, None)
        
        # Parse plaintext if decryption successful
        # Check both summary_md and plaintext for error indicators
        # (instructor_decrypt returns error messages in plaintext with empty summary_md when passphrase is wrong)
        if not summary_md.startswith("❌") and not (plaintext and plaintext.startswith("❌")):
            try:
                sid, st, comp, nblocks, avg, dur = _parse_plaintext_fields(plaintext)
                if avg:
                    try:
                        grade = float(avg)
                    except (ValueError, TypeError):
                        # Grade parsing failed, but not critical
                        grade = None
                return (filename, plaintext, summary_md, True, None, grade)
            except Exception as e:
                error_info = parsing_error(type(e).__name__)
                return (filename, plaintext, summary_md, False, error_info, grade)
        else:
            # Decryption returned error message (check both summary_md and plaintext)
            error_info = decryption_failed_error()
            # Use summary_md if available, otherwise use plaintext (which contains the error message)
            error_message = summary_md if summary_md else (plaintext if plaintext else "Decryption failed")
            return (filename, None, error_message, False, error_info, None)
    
    except Exception as e:
        # SECURITY: Unexpected error - log internal details but sanitize user message
        logger.error(
            "unexpected_file_processing_error",
            filename=filename or str(fobj),
            _internal_error_type=type(e).__name__,
            _internal_error_message=str(e)[:200]
        )
        error_info = unexpected_error("Unexpected error processing file")
        return (filename or str(fobj), None, None, False, error_info, None)


def handle_batch_decrypt(
    gr_module,
    dependencies: Dict[str, Any],
    files: List,
    passphrase: str,
    show_verdict: bool,
    show_session_id: bool,
    show_grade: bool,
    show_duration: bool,
    show_rubric_sub_scores: bool,
    show_course_name: bool,
    show_section: bool,
    show_video_enabled: bool,
    show_video_verdict: bool,
    show_video_flags: bool,
    show_audio_enabled: bool,
    show_audio_verdict: bool,
    show_audio_flags: bool,
    show_stylometric: bool,
    show_percentile: bool,
    show_zscore: bool,
    show_flag_extremes: bool,
    enable_adjustment: bool,
    method_statistical: bool,
    method_percentile: bool,
    method_confidence: bool,
    target_mean: float,
    target_std: float,
    top_pct: float,
    range_a: str,
    range_b: str,
    range_c: str,
    conf_threshold: float,
    conf_factor: float
) -> Tuple:
    """
    Handle batch decryption with parallel processing and grade adjustments.
    
    FERPA COMPLIANCE: Only authorized educational personnel may access student data.
    RBAC check is performed if RBAC functions are available in dependencies.
    
    This is a complex handler that processes multiple files in parallel,
    applies grade adjustments, and builds a results table.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary with all required functions
        files: List of files to process
        passphrase: Decryption passphrase
        show_*: Display filter flags
        enable_adjustment: Whether to apply grade adjustments
        method_*: Grade adjustment method flags
        target_mean, target_std: Statistical normalization parameters
        top_pct, range_*: Percentile curving parameters
        conf_threshold, conf_factor: Confidence adjustment parameters
        
    Returns:
        Tuple of (status_update, results_dataframe, selected_file_name_update, transcript_update)
    """
    # FERPA COMPLIANCE: Check role before accessing student data
    require_role_fn = dependencies.get("require_role")
    log_ferpa_access_fn = dependencies.get("log_ferpa_access")
    get_user_role_fn = dependencies.get("get_user_role")
    
    # Build state for RBAC check (if RBAC enabled)
    state_for_rbac = {}
    if get_user_role_fn:
        try:
            # Try to get role from dependencies or set default
            state_for_rbac["user_role"] = "INSTRUCTOR"  # Dashboard is instructor-only
        except Exception:
            pass
    
    # Check RBAC if enabled
    if require_role_fn:
        try:
            from shared.ferpa_rbac import UserRole, format_ferpa_block_error
            
            if not require_role_fn(state_for_rbac, UserRole.INSTRUCTOR, "batch_decrypt", log_ferpa_access_fn):
                # Generate correlation ID for error message
                import uuid
                correlation_id = str(uuid.uuid4())
                error_msg = format_ferpa_block_error(correlation_id)
                return (
                    gr_module.update(value=error_msg, visible=True),  # status_update
                    None,  # results_dataframe
                    gr_module.update(value=""),  # selected_file_name_update
                    gr_module.update(value="")  # transcript_update
                )
        except Exception as e:
            # Don't fail operation if RBAC check fails (backward compatibility)
            logger = dependencies.get("logger")
            if logger:
                logger.warning(
                    "rbac_check_failed",
                    error=str(e),
                    operation="batch_decrypt",
                    action="allowing_access_for_backward_compatibility"
                )
    
    # Create config object from parameters (improves code clarity)
    config = BatchDecryptConfig(
        show_verdict=show_verdict,
        show_session_id=show_session_id,
        show_grade=show_grade,
        show_duration=show_duration,
        show_rubric_sub_scores=show_rubric_sub_scores,
        show_course_name=show_course_name,
        show_section=show_section,
        show_video_enabled=show_video_enabled,
        show_video_verdict=show_video_verdict,
        show_video_flags=show_video_flags,
        show_audio_enabled=show_audio_enabled,
        show_audio_verdict=show_audio_verdict,
        show_audio_flags=show_audio_flags,
        show_stylometric=show_stylometric,
        show_percentile=show_percentile,
        show_zscore=show_zscore,
        show_flag_extremes=show_flag_extremes,
        enable_adjustment=enable_adjustment,
        method_statistical=method_statistical,
        method_percentile=method_percentile,
        method_confidence=method_confidence,
        target_mean=target_mean,
        target_std=target_std,
        top_pct=top_pct,
        range_a=range_a,
        range_b=range_b,
        range_c=range_c,
        conf_threshold=conf_threshold,
        conf_factor=conf_factor
    )
    
    # Validation using standardized helpers
    files_validation = validate_files_uploaded(files)
    if not files_validation.is_valid:
        return (
            gr_module.update(value=f"### {files_validation.to_formatted_message()}"),
            None,
            gr_module.update(visible=False),
            gr_module.update(visible=False)
        )
    
    passphrase_validation = validate_passphrase(passphrase, min_length=4)
    if not passphrase_validation.is_valid:
        return (
            gr_module.update(value=f"### {passphrase_validation.to_formatted_message()}"),
            None,
            gr_module.update(visible=False),
            gr_module.update(visible=False)
        )
    
    # Extract dependencies
    _parse_plaintext_fields = dependencies["_parse_plaintext_fields"]
    _parse_rubric_scores = dependencies["_parse_rubric_scores"]
    _safe_path = dependencies["_safe_path"]
    
    results = []
    all_grades_list = []  # Collect all grades for percentile/z-score calculation
    total = len(files)
    processed = 0
    errors = 0
    detailed_errors = []  # Store detailed error information
    # THREAD-SAFETY: Lock protects shared state in parallel processing
    # See docs/CONCURRENCY_THREAD_SAFETY.md for details
    lock = threading.Lock()
    
    # FERPA COMPLIANCE: Cleanup expired entries before new batch
    _cleanup_expired_cache()
    
    # IMPROVEMENT 1: Parallel batch processing for better performance
    # Use parallel processing for 5+ files, sequential for smaller batches
    use_parallel = total >= 5
    max_workers = min(5, total) if use_parallel else 1
    
    def process_and_collect_grade(fobj):
        """Process file and return grade for statistics"""
        stats = _process_single_file(fobj, passphrase, dependencies, lock)
        return stats
    
    # First pass: collect grades for statistics (parallel if 5+ files)
    if use_parallel:
        # IMPROVEMENT 1: Parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_and_collect_grade, fobj): fobj for fobj in files}
            
            for future in as_completed(futures):
                try:
                    filename, plaintext, summary_md, success, error_info, grade = future.result()
                    if success and grade is not None:
                        with lock:
                            all_grades_list.append(grade)
                except Exception:
                    # Future execution error
                    pass
    else:
        # Sequential processing for small batches
        for fobj in files:
            filename, plaintext, summary_md, success, error_info, grade = _process_single_file(fobj, passphrase, dependencies)
            if success and grade is not None:
                all_grades_list.append(grade)
    
    # Calculate statistics for bias mitigation
    if all_grades_list:
        grades_array = np.array(all_grades_list)
        mean_grade = np.mean(grades_array)
        std_grade = np.std(grades_array) if len(grades_array) > 1 else 1.0
        min_grade = np.min(grades_array)
        max_grade = np.max(grades_array)
        # PERFORMANCE: Sort once for O(n log n) percentile calculation (was O(n²))
        sorted_grades = sorted(all_grades_list)
    else:
        mean_grade = std_grade = min_grade = max_grade = 0
        sorted_grades = []
    
    # PERFORMANCE: Cache receipt data to avoid re-reading files
    # Receipt cache: filename -> receipt dict (cached after first read)
    # RESOURCE MANAGEMENT: Bounded cache to prevent memory growth (max 100 entries, LRU eviction)
    # THREAD-SAFETY: This cache is local to handle_batch_decrypt() and Gradio handlers are single-threaded.
    # If batch processing becomes concurrent in the future, add locks or use thread-safe collections.
    _MAX_RECEIPT_CACHE_SIZE = 100  # Maximum cache entries to prevent memory exhaustion
    receipt_cache: Dict[str, Dict[str, Any]] = {}
    receipt_cache_access_order: List[str] = []  # Track access order for LRU eviction
    
    # Second pass: process files with statistics (parallel if 5+ files)
    def build_result_row(fobj, stats, sorted_grades, mean_grade, std_grade):
        """Build result row from processed file data"""
        filename, plaintext, summary_md, success, error_info, grade = stats
        
        # Initialize row
        if error_info:
            # IMPROVEMENT 3: Better error messages with solutions
            return {
                "Filename": filename,
                "Status": f"❌ {error_info['type']}: {error_info['message']}",
                "Error Details": error_info['solution']
            }
        
        # SIMPLICITY: Use explicit if-else instead of nested ternary (Principle #19)
        if success:
            status = "✅ Success"
        elif summary_md:
            status = f"❌ {summary_md[:100]}"
        else:
            status = "❌ Unknown error"
        
        row = {
            "Filename": filename,
            "Status": status
        }
        
        # Show verdict/integrity summary if filter enabled
        if config.show_verdict:
            if success:
                row["Integrity Summary"] = summary_md if summary_md else "✅ Verified"
            else:
                row["Integrity Summary"] = summary_md if summary_md else "❌ Error"
        
        # FERPA COMPLIANCE: Store transcript in cache with timestamp
        if success and plaintext:
            set_cache_entry(filename, plaintext)
        else:
            set_cache_entry(filename, None)
        
        # Extract data from receipt if decryption successful
        # PERFORMANCE: Use cached receipt if available, otherwise read and cache
        if success and plaintext:
            try:
                fpath = _safe_path(fobj)
                if fpath and os.path.exists(fpath):
                    # Check cache first
                    if fpath in receipt_cache:
                        receipt = receipt_cache[fpath].get("receipt", {})
                        # Update access order for LRU eviction (move to end = most recently used)
                        if fpath in receipt_cache_access_order:
                            receipt_cache_access_order.remove(fpath)
                        receipt_cache_access_order.append(fpath)
                    else:
                        # RESOURCE MANAGEMENT: Use context manager to ensure file handle is closed
                        with open(fpath, "r", encoding="utf-8") as f:
                            outer = json.loads(f.read())
                        receipt = outer.get("receipt", {})
                        
                        # RESOURCE MANAGEMENT: Bounded cache with LRU eviction
                        # Evict oldest entries BEFORE adding new entry to prevent exceeding limit
                        while len(receipt_cache) >= _MAX_RECEIPT_CACHE_SIZE and receipt_cache_access_order:
                            # Remove oldest entry (LRU eviction)
                            oldest_key = receipt_cache_access_order.pop(0)
                            receipt_cache.pop(oldest_key, None)
                        
                        # Cache receipt for future use
                        receipt_cache[fpath] = outer
                        receipt_cache_access_order.append(fpath)
                    
                    core_raw = receipt.get("core", {})
                    
                    # FERPA COMPLIANCE: Decrypt receipt_core if encrypted (new format)
                    # Backward compatibility: if core_raw is already a dict, use as-is
                    try:
                        core = decrypt_receipt_core(core_raw)
                    except ValueError as e:
                        # If decryption fails, skip this file (use empty dict)
                        # Log error for debugging but continue batch processing
                        logger.warning(
                            "receipt_core_decrypt_failed",
                            file_path=fpath,
                            error_type="ValueError",
                            _internal_error_message=str(e)[:200]
                        )
                        core = {}
                    
                    # Parse plaintext for basic info
                    sid, st, comp, nblocks, avg, dur = _parse_plaintext_fields(plaintext)
                    
                    # Extract Student ID from core
                    student_id = core.get("student_id", "")
                    
                    # Basic Info
                    if config.show_session_id:
                        # FERPA COMPLIANCE: Obfuscate Session IDs to protect PII
                        row["Session ID"] = _obfuscate_session_id(sid) if sid else ""
                        # FERPA COMPLIANCE: Obfuscate Student IDs to protect PII
                        row["Student ID"] = _obfuscate_session_id(student_id) if student_id else ""
                    if config.show_grade:
                        row["Grade"] = avg or ""
                    if config.show_duration:
                        # Display duration in human-readable format
                        if dur:
                            try:
                                dur_float = float(dur)
                                hours = int(dur_float // 3600)
                                minutes = int((dur_float % 3600) // 60)
                                seconds = int(dur_float % 60)
                                if hours > 0:
                                    row["Duration"] = f"{hours}h {minutes}m {seconds}s ({int(dur_float)}s)"
                                elif minutes > 0:
                                    row["Duration"] = f"{minutes}m {seconds}s ({int(dur_float)}s)"
                                else:
                                    row["Duration"] = f"{seconds}s"
                            except (ValueError, TypeError):
                                row["Duration"] = str(dur) if dur else ""
                        else:
                            row["Duration"] = ""
                    
                    # BIAS MITIGATION - Percentile Ranking & Z-Score
                    if config.show_grade and avg:
                        try:
                            grade_float = float(avg) if avg else None
                            percentile_val = None
                            
                            if grade_float is not None and sorted_grades:
                                # PERFORMANCE: Use binary search for O(log n) percentile calculation (was O(n))
                                from bisect import bisect_right
                                percentile_val = (bisect_right(sorted_grades, grade_float) / len(sorted_grades)) * 100
                                
                                # Display percentile if enabled
                                if config.show_percentile:
                                    row["Percentile Rank"] = round(percentile_val, 1)
                                
                                # Z-Score Normalization
                                if config.show_zscore and std_grade > 0:
                                    z_score = (grade_float - mean_grade) / std_grade
                                    row["Z-Score"] = round(z_score, 3)
                                
                                # Flag Extremes
                                if config.show_flag_extremes and std_grade > 0:
                                    z_score = (grade_float - mean_grade) / std_grade
                                    if z_score > 2:
                                        row["⚠️ Extreme"] = "HIGH (Review Recommended)"
                                    elif z_score < -2:
                                        row["⚠️ Extreme"] = "LOW (Review Recommended)"
                                    else:
                                        row["⚠️ Extreme"] = ""
                                
                                # GRADE ADJUSTMENT - Delegate to business logic (Principle #3)
                                adjusted_grade, adjustment_methods, conf_score, conf_label = apply_grade_adjustments(
                                    grade_float, plaintext, percentile_val, all_grades_list,
                                    mean_grade, std_grade, config
                                )
                                
                                # Display results if adjustments were applied
                                if adjustment_methods:
                                    method_str = " + ".join(adjustment_methods)
                                    row["Adjusted Grade"] = f"{round(adjusted_grade, 1)} ({method_str})"
                                    row["Original Grade"] = grade_float  # Keep original visible
                                    
                                    # Display confidence if confidence adjustment was applied
                                    if conf_score is not None and conf_label is not None:
                                        row["Confidence"] = f"{round(conf_score, 1)}% ({conf_label})"
                        except (ValueError, TypeError):
                            # Grade parsing failed, continue without grade calculations
                            pass
                    
                    # BIAS MITIGATION - RUBRIC TRANSPARENCY: Show sub-scores separately
                    if config.show_rubric_sub_scores:
                        rubric_avgs = _parse_rubric_scores(plaintext)
                        if rubric_avgs.get("Conceptual") is not None:
                            row["Rubric: Conceptual"] = rubric_avgs["Conceptual"]
                        if rubric_avgs.get("Analytical") is not None:
                            row["Rubric: Analytical"] = rubric_avgs["Analytical"]
                        if rubric_avgs.get("Application") is not None:
                            row["Rubric: Application"] = rubric_avgs["Application"]
                        if rubric_avgs.get("Reflection") is not None:
                            row["Rubric: Reflection"] = rubric_avgs["Reflection"]
                        if rubric_avgs.get("Overall") is not None:
                            row["Rubric: Overall"] = rubric_avgs["Overall"]
                    
                    # Course/Exam Info
                    course_id = core.get("course_id", "")
                    exam_id = core.get("exam_id", "")
                    section_id = core.get("section_id", "")
                    
                    if config.show_course_name:
                        row["Course ID"] = course_id or ""
                        row["Exam ID"] = exam_id or ""
                    if config.show_section:
                        row["Section ID"] = section_id or ""
                    
                    # Proctor Info
                    proctor = core.get("proctor", {})
                    if proctor:
                        if config.show_video_enabled:
                            row["Proctor Enabled"] = proctor.get("enabled", False)
                        if config.show_video_verdict:
                            row["Proctor Verdict"] = proctor.get("verdict", "")
                            row["Proctor Reason"] = proctor.get("reason", "")
                        
                        if config.show_video_flags and proctor.get("enabled"):
                            g = proctor.get("global", {})
                            fc = g.get("flag_counts", {}) or {}
                            row["Face Present Ratio"] = round(g.get("face_present_ratio", 0), 3) if g.get("face_present_ratio") else ""
                            row["Away Ratio"] = round(g.get("away_ratio", 0), 3) if g.get("away_ratio") else ""
                            row["Multi Face Ratio"] = round(g.get("multi_face_ratio", 0), 3) if g.get("multi_face_ratio") else ""
                            row["Video Flags Total"] = g.get("flags_total", 0)
                            row["Flag: AWAY_BURST"] = fc.get("AWAY_BURST", 0)
                            row["Flag: MULTI_FACE"] = fc.get("MULTI_FACE", 0)
                            row["Flag: NO_FACE"] = fc.get("NO_FACE", 0)
                            row["Flag: EXTREME_GAZE"] = fc.get("EXTREME_GAZE", 0)
                    
                    # Audio Analysis
                    audio_analysis = core.get("audio_analysis", {})
                    if audio_analysis:
                        if config.show_audio_enabled:
                            row["Audio Analysis Enabled"] = audio_analysis.get("enabled", False)
                        
                        if config.show_audio_verdict:
                            row["Audio Verdict"] = audio_analysis.get("verdict", "")
                            row["Audio Reason"] = audio_analysis.get("reason", "")
                        
                        if config.show_audio_flags or config.show_stylometric:
                            afc = audio_analysis.get("flag_counts", {}) or {}
                            if config.show_audio_flags:
                                row["Audio Flags Total"] = audio_analysis.get("flags_total", 0)
                                row["Flag: VOICEPRINT_MISMATCH"] = afc.get("VOICEPRINT_MISMATCH", 0)
                                row["Flag: UNNATURAL_SPEECH_RATE"] = afc.get("UNNATURAL_SPEECH_RATE", 0)
                                row["Flag: PROFANITY"] = afc.get("PROFANITY_DETECTED", 0)
                                row["Flag: ANSWER_REUSE"] = afc.get("ANSWER_REUSE_DETECTED", 0)
                                row["Flag: SESSION_TIMEOUT"] = afc.get("SESSION_TIMEOUT", 0)
                                row["Flag: ANSWER_TIMEOUT"] = afc.get("ANSWER_TIMEOUT", 0)
                            
                            if config.show_stylometric:
                                row["Flag: NO_HESITATION"] = afc.get("NO_HESITATION_PATTERN", 0)
                                row["Flag: LEXICAL_INCONSISTENCY"] = afc.get("LEXICAL_INCONSISTENCY", 0)
                                row["Flag: ZERO_PAUSE"] = afc.get("ZERO_PAUSE_DELIVERY", 0)
            except (json.JSONDecodeError, ValueError, IOError, KeyError, AttributeError):
                # If receipt parsing fails or data is missing, just use basic info
                pass
        return row
    
    # IMPROVEMENT 1 & 2: Parallel processing with progress tracking
    # Process files in parallel (if 5+ files) or sequentially (if <5 files)
    file_results = {}  # Store results by index for ordering
    
    if use_parallel:
        # IMPROVEMENT 1: Parallel processing for 5+ files
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_process_single_file, fobj, passphrase, dependencies, lock): i
                      for i, fobj in enumerate(files)}
            
            for future in as_completed(futures):
                i = futures[future]
                try:
                    stats = future.result()
                    file_results[i] = (files[i], stats)
                except Exception:
                    # Future execution error
                    file_results[i] = (files[i], (str(files[i]), None, None, False,
                        {"type": "EXECUTION_ERROR", "message": "Execution error",
                         "solution": "Please try again or contact support"}, None))
    else:
        # Sequential processing for small batches (<5 files)
        for i, fobj in enumerate(files):
            stats = _process_single_file(fobj, passphrase, dependencies)
            file_results[i] = (fobj, stats)
    
    # Build results in order
    for i in sorted(file_results.keys()):
        fobj, stats = file_results[i]
        filename, plaintext, summary_md, success, error_info, grade = stats
        
        # Build result row
        row = build_result_row(fobj, stats, sorted_grades, mean_grade, std_grade)
        results.append(row)
        
        if success:
            processed += 1
        else:
            errors += 1
            if error_info:
                detailed_errors.append({
                    "file": filename,
                    "type": error_info.get("type", "UNKNOWN"),
                    "message": error_info.get("message", ""),
                    "solution": error_info.get("solution", "")
                })
    
    # Cleanup expired entries periodically
    if processed % 10 == 0:
        _cleanup_expired_cache()
    
    # IMPROVEMENT 3: Build detailed status message with better error reporting
    status_msg = f"✅ Processed: {processed}/{total} files successfully"
    if errors > 0:
        status_msg += f" | ❌ Errors: {errors}"
    
    # IMPROVEMENT 3: Add detailed error summary if errors occurred
    if detailed_errors:
        error_summary = "\n\n### ❌ Error Summary:\n\n"
        # Group errors by type
        error_types = {}
        for err in detailed_errors[:10]:  # Show first 10 errors
            err_type = err.get("type", "UNKNOWN")
            if err_type not in error_types:
                error_types[err_type] = []
            error_types[err_type].append(err)
        
        for err_type, errs in error_types.items():
            count = len(errs)
            error_summary += f"**{err_type}**: {count} file(s)\n"
            if count <= 3:
                # Show solutions for small error counts
                for err in errs:
                    error_summary += f"  - {err['file']}: {err.get('solution', 'No solution available')}\n"
            error_summary += "\n"
        
        if len(detailed_errors) > 10:
            error_summary += f"*... and {len(detailed_errors) - 10} more errors. Check results table for details.*\n"
        
        status_msg += error_summary
    
    # Add bias mitigation statistics to status
    if all_grades_list:
        status_msg += f"\n\n📊 **Batch Statistics**: Mean={mean_grade:.1f}, Std={std_grade:.1f}, Range=[{min_grade:.1f}, {max_grade:.1f}]"
        
        # Add adjustment method info if enabled
        if enable_adjustment:
            methods = []
            if method_statistical:
                methods.append(f"Normalization (μ={target_mean or 75.0}, σ={target_std or 12.0})")
            if method_percentile:
                methods.append(f"Curving (Top {top_pct or 10.0}%)")
            if method_confidence:
                methods.append(f"Confidence (Threshold={conf_threshold or 70.0}%)")
            if methods:
                status_msg += f"\n🔧 **Adjustment Methods**: {' + '.join(methods)}"
    
    # Add processing mode info
    if use_parallel:
        status_msg += f"\n⚡ **Processing**: Parallel ({max_workers} workers)"
    else:
        status_msg += f"\n⚡ **Processing**: Sequential"
    
    # FERPA COMPLIANCE: Final cleanup of expired cache entries
    _cleanup_expired_cache()
    
    df = pd.DataFrame(results)
    
    # Store dataframe globally so select handler can access it
    global _current_batch_decrypt_df
    _current_batch_decrypt_df = df
    
    return (
        gr_module.update(value=status_msg),
        df,
        gr_module.update(visible=False),
        gr_module.update(visible=False)
    )


def handle_on_row_select(
    gr_module,
    dependencies: Dict[str, Any],
    evt: Any,
    df: Optional[pd.DataFrame] = None
) -> Tuple:
    """
    Handle row selection to show transcript from cache.
    
    Args:
        gr_module: Gradio module
        dependencies: Dependencies dictionary (unused but kept for consistency)
        evt: Gradio SelectData event
        df: Results dataframe (optional - can be None if not passed from Gradio)
        
    Returns:
        Tuple of (selected_file_name_update, transcript_update)
    """
    global _current_batch_decrypt_df  # Access module-level variable
    
    if evt.index is None:
        return gr_module.update(visible=False), gr_module.update(visible=False)
    
    try:
        # Get selected row index
        selected_idx = evt.index[0]
        
        # Get filename from dataframe if available, otherwise try to get from event
        filename = None
        
        # Convert df to DataFrame if it's not already one (Gradio may pass list/dict)
        if df is not None:
            if not isinstance(df, pd.DataFrame):
                try:
                    # Handle list of dicts (common Gradio format)
                    if isinstance(df, list) and len(df) > 0:
                        df = pd.DataFrame(df)
                    else:
                        df = pd.DataFrame(df)
                except Exception:
                    df = None
        
        # Try to extract filename from dataframe
        if df is not None and len(df) > 0:
            try:
                # Check bounds
                if selected_idx < len(df):
                    # Try "Filename" column (case-sensitive)
                    if "Filename" in df.columns:
                        filename = str(df.iloc[selected_idx]["Filename"]).strip()
                    # Try lowercase as fallback
                    elif "filename" in df.columns:
                        filename = str(df.iloc[selected_idx]["filename"]).strip()
            except (KeyError, IndexError, AttributeError) as e:
                filename = None
        
        # SECOND: Try the global stored dataframe (most reliable)
        if (not filename or filename == "None" or filename == "") and _current_batch_decrypt_df is not None:
            try:
                if selected_idx < len(_current_batch_decrypt_df):
                    if "Filename" in _current_batch_decrypt_df.columns:
                        filename = str(_current_batch_decrypt_df.iloc[selected_idx]["Filename"]).strip()
                    elif "filename" in _current_batch_decrypt_df.columns:
                        filename = str(_current_batch_decrypt_df.iloc[selected_idx]["filename"]).strip()
            except (KeyError, IndexError, AttributeError):
                pass
        
        # THIRD: Try evt.value as fallback
        if (not filename or filename == "None" or filename == "") and hasattr(evt, 'value') and evt.value is not None:
            try:
                event_df = None
                if isinstance(evt.value, pd.DataFrame):
                    event_df = evt.value
                elif isinstance(evt.value, (list, dict)):
                    event_df = pd.DataFrame(evt.value)
                elif isinstance(evt.value, list) and len(evt.value) > 0:
                    event_df = pd.DataFrame(evt.value)
                
                if event_df is not None and isinstance(event_df, pd.DataFrame) and len(event_df) > 0:
                    if selected_idx < len(event_df):
                        if "Filename" in event_df.columns:
                            filename = str(event_df.iloc[selected_idx]["Filename"]).strip()
                        elif "filename" in event_df.columns:
                            filename = str(event_df.iloc[selected_idx]["filename"]).strip()
            except Exception:
                pass
        
        # FOURTH: Try evt.target.value (component's current value) as last resort
        if (not filename or filename == "None" or filename == "") and hasattr(evt, 'target'):
            try:
                if hasattr(evt.target, 'value') and evt.target.value is not None:
                    target_value = evt.target.value
                    target_df = None
                    if isinstance(target_value, pd.DataFrame):
                        target_df = target_value
                    elif isinstance(target_value, (list, dict)):
                        target_df = pd.DataFrame(target_value)
                    
                    if target_df is not None and isinstance(target_df, pd.DataFrame) and len(target_df) > 0:
                        if selected_idx < len(target_df):
                            if "Filename" in target_df.columns:
                                filename = str(target_df.iloc[selected_idx]["Filename"]).strip()
                            elif "filename" in target_df.columns:
                                filename = str(target_df.iloc[selected_idx]["filename"]).strip()
            except Exception:
                pass
        
        # Final check - if still no filename, log debug info and return error
        if not filename or filename == "None" or filename == "":
            # Log debug information for troubleshooting
            logger.debug(
                "filename_extraction_failed",
                row_index=selected_idx,
                dataframe_provided=df is not None,
                dataframe_type=str(type(df)) if df is not None else None,
                dataframe_length=len(df) if df is not None and hasattr(df, '__len__') else None,
                dataframe_columns=list(df.columns) if df is not None and hasattr(df, 'columns') else None,
                event_value_type=str(type(evt.value)) if hasattr(evt, 'value') else None,
                event_value_length=len(evt.value) if hasattr(evt, 'value') and evt.value is not None and hasattr(evt.value, '__len__') else None,
                event_target_exists=hasattr(evt, 'target'),
                event_target_value_type=str(type(evt.target.value)) if hasattr(evt, 'target') and hasattr(evt.target, 'value') else None,
                message="Could not determine filename from selection - debug info logged"
            )
            
            return gr_module.update(visible=False), gr_module.update(
                value="❌ Could not determine filename from selection. Please try selecting a different row or contact support.",
                visible=True
            )
        
        # FERPA COMPLIANCE: Retrieve transcript from cache with validation
        cache_entry = get_cache_entry(filename)
        
        # Check if entry exists and is valid (not expired)
        if cache_entry and _is_cache_entry_valid(cache_entry):
            transcript = cache_entry.get("transcript", "")
            return (
                gr_module.update(value=f"📄 {filename}", visible=True),
                gr_module.update(value=transcript, visible=True)
            )
        elif cache_entry is None:
            return (
                gr_module.update(value=f"📄 {filename}", visible=True),
                gr_module.update(value="❌ No transcript available for this file.", visible=True)
            )
        else:
            # Cache entry expired
            return (
                gr_module.update(value=f"📄 {filename}", visible=True),
                gr_module.update(value="⚠️ Transcript cache expired. Please decrypt again.", visible=True)
            )
    except Exception as e:
        # SECURITY: Sanitize error message - don't expose implementation details
        logger.error(
            "transcript_load_error",
            _internal_error_type=type(e).__name__,
            _internal_error_message=str(e)[:100]
        )
        return (
            gr_module.update(visible=False),
            gr_module.update(value="Error loading transcript. Please try selecting again.", visible=True)
        )

