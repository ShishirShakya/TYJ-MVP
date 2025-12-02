"""
CSV export utilities for dash.ipynb - batch CSV summarization.

This module contains CSV export functions used only by dash.ipynb.
Functions used by multiple apps are in shared/.
"""

import os
import json
import csv
import tempfile
from typing import Tuple, Optional, List, Any, Dict
from datetime import datetime, timezone

from dash.decryption import instructor_decrypt, _check_and_mark_otet
from dash.parsing import _parse_plaintext_fields, _parse_rubric_scores
from shared.pii_obfuscation import decrypt_receipt_core


def _safe_path(obj: Any) -> Optional[str]:
    """
    Safely extract file path from object (handles Gradio File objects).
    
    Args:
        obj: File object (may have .name attribute)
        
    Returns:
        File path string, or None if obj is None
    """
    if obj is None:
        return None
    return getattr(obj, "name", obj)


# =========================
# Batch CSV summarization
# =========================

def batch_csv_summarize(
    files: List[Any], 
    passphrase: str,
    instructor_context: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[str], str]:
    """
    Batch CSV summarization with extended telemetry and FERPA-compliant audit logging.
    
    Processes multiple encrypted exam transcript files and generates a CSV summary
    with all available telemetry data (proctor, audio analysis, rubric scores, etc.).
    
    FERPA COMPLIANCE: Logs CSV exports containing student PII for audit trail.
    Adds FERPA notice header to exported CSV files.
    
    Args:
        files: List of file objects (Gradio File objects or file paths)
        passphrase: Decryption passphrase
        instructor_context: Optional dict with instructor_id for FERPA audit logging.
                          If provided, enables audit logging and adds FERPA notice to CSV.
        
    Returns:
        (csv_path: Optional[str], status_message: str)
        - csv_path: Path to generated CSV file, or None on error
        - status_message: Status message describing the operation result
    """
    if not files:
        return None, "Please upload one or more .enc files."
    if not passphrase.strip():
        return None, "Please enter the passphrase."
    
    # FERPA COMPLIANCE: Log CSV export initiation if instructor context provided
    if instructor_context:
        try:
            from shared.ferpa_audit import log_ferpa_access
            log_ferpa_access(
                who=f"INSTRUCTOR:{instructor_context.get('instructor_id', 'unknown')}",
                what="csv_export_initiated",
                why="LMS_grade_import",
                when=datetime.now(timezone.utc),
                additional_context={
                    "num_files": len(files),
                    "export_type": "CSV",
                    "contains_pii": True
                }
            )
        except Exception:
            # Don't fail CSV generation if audit logging fails (graceful degradation)
            pass
    
    # Extended columns to capture proctor telemetry + audio analysis + token usage & cost tracking
    rows = [(
        "filename", "integrity_summary", "verdict_duplicate",
        "session_id", "student_id", "started_at", "completed_at",
        "num_blocks", "avg_overall", "duration_sec",
        # --- Exam metadata ---
        "course_id", "exam_id", "section_id", "start_date", "end_date",
        # --- Rubric Sub-Scores ---
        "rubric_conceptual", "rubric_analytical", "rubric_application", "rubric_reflection",
        # --- Grade Adjustments ---
        "original_grade", "adjusted_grade", "adjustment_methods",
        # --- Proctor telemetry ---
        "proctor_enabled", "proctor_verdict", "proctor_reason",
        "face_present_ratio", "away_ratio", "multi_face_ratio",
        "flags_total", "flag_AWAY_BURST", "flag_MULTI_FACE", "flag_NO_FACE", "flag_EXTREME_GAZE",
        # --- Audio analysis telemetry ---
        "audio_analysis_enabled", "audio_verdict", "audio_reason", "audio_flags_total",
        "flag_VOICEPRINT_MISMATCH", "flag_UNNATURAL_SPEECH_RATE",
        "flag_NO_HESITATION_PATTERN", "flag_LEXICAL_INCONSISTENCY", "flag_ZERO_PAUSE_DELIVERY",
        "flag_PROFANITY_DETECTED", "flag_ANSWER_REUSE_DETECTED",
        # --- Session control telemetry ---
        "flag_SESSION_TIMEOUT", "flag_ANSWER_TIMEOUT"
    )]
    
    ok = 0
    
    for fobj in files:
        try:
            fpath = _safe_path(fobj)
            if not fpath or not os.path.exists(fpath):
                rows.append((str(fpath), "FILE_NOT_FOUND", "",
                             "", "", "", "", "", "", "",  # session_id, student_id, started_at, completed_at, num_blocks, avg_overall, duration_sec
                             "", "", "", "", "",  # course_id, exam_id, section_id, start_date, end_date
                             "", "", "", "",  # rubric_sub_scores
                             "", "", "",  # original_grade, adjusted_grade, adjustment_methods
                             "", "", "", "", "", "", "", "", "",  # proctor fields
                             "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""))  # audio, flags, tokens, costs
                continue
            
            from shared.constants import MAX_FILE_SIZE  # SSOT - Principle #2
            if os.path.getsize(fpath) > MAX_FILE_SIZE:
                rows.append((os.path.basename(fpath), "FILE_TOO_LARGE", "",
                             "", "", "", "", "", "", "",  # session_id, student_id, started_at, completed_at, num_blocks, avg_overall, duration_sec
                             "", "", "", "", "",  # course_id, exam_id, section_id, start_date, end_date
                             "", "", "", "",  # rubric_sub_scores
                             "", "", "",  # original_grade, adjusted_grade, adjustment_methods
                             "", "", "", "", "", "", "", "", "",  # proctor fields
                             "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""))  # audio, flags, tokens, costs
                continue
            
            # Decrypt file
            plaintext, summary_md = instructor_decrypt(fpath, passphrase)
            # SIMPLICITY: Use explicit if-else instead of nested ternary (Principle #19)
            summary_safe = summary_md or ""
            plaintext_safe = plaintext or ""
            
            if "DUPLICATE" in summary_safe:
                verdict_dup = "DUPLICATE"
            elif "FIRST_USE" in summary_safe:
                verdict_dup = "FIRST_USE"
            else:
                verdict_dup = ""
            
            if summary_safe.startswith("❌") or "Tamper detected" in summary_safe or plaintext_safe.startswith("❌"):
                rows.append((os.path.basename(fpath), summary_md or "Decrypt/verify error",
                             verdict_dup, "", "", "", "", "", "", "",  # session_id, student_id, started_at, completed_at, num_blocks, avg_overall, duration_sec
                             "", "", "", "", "",  # course_id, exam_id, section_id, start_date, end_date
                             "", "", "", "",  # rubric_sub_scores
                             "", "", "",  # original_grade, adjusted_grade, adjustment_methods
                             "", "", "", "", "", "", "", "", "",  # proctor fields
                             "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""))  # audio, flags, tokens, costs
                continue
            
            # Initialize all new variables BEFORE parsing (ensures they exist even if extraction fails)
            student_id_val = ""
            rubric_conceptual = rubric_analytical = rubric_application = rubric_reflection = ""
            original_grade = adjusted_grade = adjustment_methods = ""
            
            # Parse main info
            sid, st, comp, nblocks, avg, dur = _parse_plaintext_fields(plaintext)
            
            # Extract rubric sub-scores from plaintext (BIAS MITIGATION - RUBRIC TRANSPARENCY)
            try:
                rubric_avgs = _parse_rubric_scores(plaintext)
                if rubric_avgs:
                    rubric_conceptual = rubric_avgs.get("Conceptual", "") if rubric_avgs.get("Conceptual") is not None else ""
                    rubric_analytical = rubric_avgs.get("Analytical", "") if rubric_avgs.get("Analytical") is not None else ""
                    rubric_application = rubric_avgs.get("Application", "") if rubric_avgs.get("Application") is not None else ""
                    rubric_reflection = rubric_avgs.get("Reflection", "") if rubric_avgs.get("Reflection") is not None else ""
            except Exception:
                pass  # If rubric parsing fails, keep empty values
            
            # Calculate grade adjustments (if avg_overall is available and numeric)
            try:
                if avg and isinstance(avg, (int, float)):
                    original_grade = float(avg)
                    adjusted_grade = original_grade
                    applied_methods = []
                    
                    # DESIGN DECISION: Batch-level grade adjustments (statistical normalization, percentile curving,
                    # confidence-based adjustment) are not calculated here because they require batch statistics from
                    # all files. Individual file adjustments are available in the batch decrypt UI.
                    # Batch-level adjustments can be applied in post-processing if needed.
                    # See TD-002: Batch-level grade adjustment placeholder (deferred by design)
                    
                    adjustment_methods = ""  # Empty - batch-level adjustments deferred by design
                else:
                    original_grade = avg if avg else ""
                    adjusted_grade = ""
                    adjustment_methods = ""
            except Exception:
                original_grade = avg if avg else ""
                adjusted_grade = ""
                adjustment_methods = ""
            
            # --- Parse proctor summary if available ---
            proctor_enabled = ""
            proctor_verdict = ""
            proctor_reason = ""
            face_ratio = away_ratio = multi_ratio = ""
            flags_total = flag_away = flag_multi = flag_no_face = flag_extreme_gaze = ""
            
            # --- Parse audio analysis summary if available ---
            audio_analysis_enabled = ""
            audio_verdict = ""
            audio_reason = ""
            audio_flags_total = ""
            flag_voiceprint = flag_speech_rate = flag_hesitation = flag_lexical = flag_pause = flag_profanity = flag_reuse = ""
            flag_session_timeout = flag_answer_timeout = ""
            
            # --- Extract exam metadata from core ---
            course_id_val = exam_id_val = section_id_val = start_date_val = end_date_val = ""
            # Note: student_id_val, rubric variables, and grade variables are already initialized above
            
            try:
                # Load outer JSON to inspect receipt directly
                # RESOURCE MANAGEMENT: Use context manager to ensure file handle is closed
                with open(fpath, "r", encoding="utf-8") as f:
                    outer = json.loads(f.read())
                receipt = outer.get("receipt", {})
                core_raw = receipt.get("core", {})
                
                # FERPA COMPLIANCE: Decrypt receipt_core if encrypted (new format)
                # Backward compatibility: if core_raw is already a dict, use as-is
                try:
                    core = decrypt_receipt_core(core_raw)
                except ValueError as e:
                    # If decryption fails, skip this file (log error but continue)
                    # This can happen with corrupted files or wrong encryption key
                    core = {}
                    # Note: Error is silently handled to allow batch processing to continue
                    # Individual file errors don't stop the entire batch operation
                
                # Extract exam metadata
                course_id_val = core.get("course_id", "")
                exam_id_val = core.get("exam_id", "")
                section_id_val = core.get("section_id", "")
                start_date_val = core.get("start_date", "")
                end_date_val = core.get("end_date", "")
                
                # Extract Student ID from core (Critical for LMS grade merging)
                student_id_val = core.get("student_id", "")
                
                proctor = core.get("proctor", {})
                if proctor:
                    proctor_enabled = proctor.get("enabled", "")
                    proctor_verdict = proctor.get("verdict", "")
                    proctor_reason = proctor.get("reason", "")
                    g = proctor.get("global", {})
                    face_ratio = g.get("face_present_ratio", "")
                    away_ratio = g.get("away_ratio", "")
                    multi_ratio = g.get("multi_face_ratio", "")
                    flags_total = g.get("flags_total", "")
                    fc = g.get("flag_counts", {}) or {}
                    flag_away = fc.get("AWAY_BURST", 0)
                    flag_multi = fc.get("MULTI_FACE", 0)
                    flag_no_face = fc.get("NO_FACE", 0)
                    flag_extreme_gaze = fc.get("EXTREME_GAZE", 0)
                
                # Parse audio analysis flags
                audio_analysis = core.get("audio_analysis", {})
                if audio_analysis:
                    audio_analysis_enabled = audio_analysis.get("enabled", "")
                    audio_verdict = audio_analysis.get("verdict", "")
                    audio_reason = audio_analysis.get("reason", "")
                    audio_flags_total = audio_analysis.get("flags_total", "")
                    afc = audio_analysis.get("flag_counts", {}) or {}
                    flag_voiceprint = afc.get("VOICEPRINT_MISMATCH", 0)
                    flag_speech_rate = afc.get("UNNATURAL_SPEECH_RATE", 0)
                    flag_hesitation = afc.get("NO_HESITATION_PATTERN", 0)
                    flag_lexical = afc.get("LEXICAL_INCONSISTENCY", 0)
                    flag_pause = afc.get("ZERO_PAUSE_DELIVERY", 0)
                    flag_profanity = afc.get("PROFANITY_DETECTED", 0)
                    flag_reuse = afc.get("ANSWER_REUSE_DETECTED", 0)
                    flag_session_timeout = afc.get("SESSION_TIMEOUT", 0)
                    flag_answer_timeout = afc.get("ANSWER_TIMEOUT", 0)
                    
            except Exception:
                pass
            
            rows.append((
                os.path.basename(fpath), summary_md, verdict_dup,
                sid, student_id_val, st, comp, nblocks, avg, dur,
                course_id_val, exam_id_val, section_id_val, start_date_val, end_date_val,
                rubric_conceptual, rubric_analytical, rubric_application, rubric_reflection,
                original_grade, adjusted_grade, adjustment_methods,
                proctor_enabled, proctor_verdict, proctor_reason,
                face_ratio, away_ratio, multi_ratio,
                flags_total, flag_away, flag_multi, flag_no_face, flag_extreme_gaze,
                audio_analysis_enabled, audio_verdict, audio_reason, audio_flags_total,
                flag_voiceprint, flag_speech_rate, flag_hesitation, flag_lexical, flag_pause, flag_profanity, flag_reuse,
                flag_session_timeout, flag_answer_timeout
            ))
            ok += 1
            
        except Exception as e:
            rows.append((str(getattr(fobj, "name", fobj)), f"❌ {type(e).__name__}: {e}",
                         "", "", "", "", "", "", "", "",  # session_id, student_id, started_at, completed_at, num_blocks, avg_overall, duration_sec
                         "", "", "", "", "",  # course_id, exam_id, section_id, start_date, end_date
                         "", "", "", "",  # rubric_sub_scores
                         "", "", "",  # original_grade, adjusted_grade, adjustment_methods
                         "", "", "", "", "", "", "", "", "",  # proctor fields
                         "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""))  # audio, flags, tokens, costs
    
    # Write output CSV with FERPA compliance header
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".csv", mode="w", newline="", encoding="utf-8")
    writer = csv.writer(out)
    
    # FERPA COMPLIANCE: Add FERPA notice header if instructor context provided
    if instructor_context:
        # Add FERPA compliance header rows
        header_cols = len(rows[0]) if rows else 56  # Match number of columns
        empty_row = [""] * header_cols
        
        writer.writerow(["# FERPA-PROTECTED EDUCATIONAL RECORDS"] + [""] * (header_cols - 1))
        writer.writerow(["# For authorized educational use only - Do not share publicly"] + [""] * (header_cols - 1))
        writer.writerow([f"# Exported by: {instructor_context.get('instructor_id', 'unknown')}"] + [""] * (header_cols - 1))
        writer.writerow([f"# Export timestamp: {datetime.now(timezone.utc).isoformat()}"] + [""] * (header_cols - 1))
        writer.writerow(empty_row)  # Empty row separator
    
    # Write actual data rows
    writer.writerows(rows)
    out.close()
    
    # FERPA COMPLIANCE: Log successful CSV export completion
    if instructor_context:
        try:
            from shared.ferpa_audit import log_ferpa_access
            log_ferpa_access(
                who=f"INSTRUCTOR:{instructor_context.get('instructor_id', 'unknown')}",
                what="csv_export_completed",
                why="LMS_grade_import",
                when=datetime.now(timezone.utc),
                additional_context={
                    "num_records": len(rows) - 1,  # Exclude header row
                    "csv_path": out.name,
                    "contains_pii": True
                }
            )
        except Exception:
            # Don't fail if audit logging fails (graceful degradation)
            pass
    
    summary_msg = f"✅ Processed: {ok} files | 📄 CSV built with {len(rows)-1} rows."
    
    return out.name, summary_msg

