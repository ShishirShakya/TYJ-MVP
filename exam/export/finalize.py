"""
Finalize and export encrypted exam module for exam.ipynb.

This module contains functions for finalizing and exporting encrypted exam data:
- Finalize and export encrypted exam transcript
"""

import os
import re
import json
import time
import base64
import hashlib
import tempfile
import shutil
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple

from exam.config import (
    APP_VERSION,
    RECEIPT_VERSION,
    RUBRIC_VERSION,
    PROCESSING_BUFFER_SEC,
    SESSION_BUFFER_SEC,
    continuity_mode,
    model_versions,
)
from exam.state import ensure_state, save_state_to_disk
from exam.context_vars import (
    get_course_id,
    get_exam_id,
    get_passphrase,
    get_followups_min,
    get_followups_max,
    get_chunks,
    get_textbook_sha256,
    get_max_answer_timeout_sec,
)
from exam.security import (
    get_otet,
    get_or_create_device_key,
    pubkey_bytes,
    answers_to_merkle,
)
from exam.cryptography import encrypt_bytes
from exam.file_utils import _paths_for_session
from exam.proctor import ProctorState, PROCTOR_RULES, PROCTOR_CONFIG, PROCTOR_FLAG_RULES
from shared.logging_config import get_logger
from shared.pii_obfuscation import encrypt_receipt_core
from shared.constants import FALLBACK_NO_TEXTBOOK_CONTENT
from shared.platform import get_default_platform_provider

logger = get_logger()


def finalize_and_export_encrypted(
    s: Dict[str, Any],
    ensure_state_fn=None,
    save_state_to_disk_fn=None,
    get_chunks_fn=None,
    get_textbook_sha256_fn=None,
    get_max_answer_timeout_sec_fn=None,
    PERSIST_OK=None,
    CHUNKS=None,
    TEXTBOOK_SHA256=None,
) -> Tuple[str, str]:
    """
    Finalize and export encrypted exam transcript.
    
    This function builds the human-readable plaintext transcript, creates the
    receipt core with all metadata, encrypts the transcript, and exports it
    as an encrypted .enc file.
    
    Args:
        s: State dictionary
        ensure_state_fn: Function to ensure state (default: exam.state.ensure_state)
        save_state_to_disk_fn: Function to save state to disk (default: exam.state.save_state_to_disk)
        get_chunks_fn: Function to get chunks (default: exam.context_vars.get_chunks)
        get_textbook_sha256_fn: Function to get textbook SHA256 (default: exam.context_vars.get_textbook_sha256)
        get_max_answer_timeout_sec_fn: Function to get max answer timeout (default: exam.context_vars.get_max_answer_timeout_sec)
        PERSIST_OK: Persistence gate (default: from exam.config)
        CHUNKS: Global chunks variable (default: None)
        TEXTBOOK_SHA256: Global textbook SHA256 (default: None)
        
    Returns:
        Tuple of (file_path, summary_message)
    """
    # Use default functions if not provided
    if ensure_state_fn is None:
        ensure_state_fn = ensure_state
    if save_state_to_disk_fn is None:
        save_state_to_disk_fn = save_state_to_disk
    if get_chunks_fn is None:
        get_chunks_fn = get_chunks
    if get_textbook_sha256_fn is None:
        get_textbook_sha256_fn = get_textbook_sha256
    if get_max_answer_timeout_sec_fn is None:
        get_max_answer_timeout_sec_fn = get_max_answer_timeout_sec
    if PERSIST_OK is None:
        from exam.config import PERSIST_OK
    
    s = ensure_state_fn(s)

    # Use state values instead of globals for exam configuration
    course_id = s.get("course_id", get_course_id())
    exam_id = s.get("exam_id", get_exam_id())
    section_id = s.get("section_id", "UNKNOWN")
    start_date = s.get("start_date", "")
    end_date = s.get("end_date", "")
    passphrase = s.get("passphrase", get_passphrase())
    followups_min = s.get("followups_min", get_followups_min())
    followups_max = s.get("followups_max", get_followups_max())

    # Validate passphrase is set before encryption
    if not passphrase or not passphrase.strip():
        raise ValueError("❌ Passphrase not set. Please parse professor's link first to set the decryption passphrase.")

    # Ensure one-time token exists
    if not s.get("otet"):
        s["otet"] = get_otet()

    # ----------------------------
    # Build human-readable plaintext
    # ----------------------------
    lines = [
        "=== Viva Metadata ===",
        f"AppVersion: {APP_VERSION}",
        f"SessionID: {s.get('session_id','')}",
        f"StudentID: {s.get('student_id','')}",
        f"StartedAt: {s.get('started_at','')}",
        f"CompletedAt: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "=== Exam Termination Summary ==="
    ]
    
    # Determine termination reason
    if s.get("phase") == "complete":
        flags = s.get("flags", [])
        termination_reason = ""
        termination_flags = []
        
        # Check for critical violations first (highest priority)
        if "VOICEPRINT_MISMATCH" in flags:
            termination_reason = "Critical violation - Voiceprint mismatch detected (different person)"
            termination_flags.append("VOICEPRINT_MISMATCH")
        elif "MULTI_FACE" in flags:
            termination_reason = "Critical violation - Multiple faces detected"
            termination_flags.append("MULTI_FACE")
        elif "PROFANITY_DETECTED" in flags:
            termination_reason = "Critical violation - Profanity detected"
            termination_flags.append("PROFANITY_DETECTED")
        # Check for threshold-exceeded violations
        elif any("_THRESHOLD_EXCEEDED" in flag for flag in flags):
            threshold_violations = [flag.replace("_THRESHOLD_EXCEEDED", "") for flag in flags if "_THRESHOLD_EXCEEDED" in flag]
            if "TAB_BLUR_THRESHOLD_EXCEEDED" in flags:
                termination_reason = f"Violation threshold exceeded - Tab switch violations ({threshold_violations[0]})"
                termination_flags.extend([f for f in threshold_violations if f in ["TAB_BLUR", "CLIPBOARD_PASTE", "CLIPBOARD_COPY", "ANSWER_REUSE_DETECTED"]])
            elif "CLIPBOARD_PASTE_THRESHOLD_EXCEEDED" in flags:
                termination_reason = "Violation threshold exceeded - Paste operation violations"
                termination_flags.append("CLIPBOARD_PASTE")
            elif "CLIPBOARD_COPY_THRESHOLD_EXCEEDED" in flags:
                termination_reason = "Violation threshold exceeded - Copy operation violations"
                termination_flags.append("CLIPBOARD_COPY")
            elif "ANSWER_REUSE_DETECTED_THRESHOLD_EXCEEDED" in flags:
                termination_reason = "Violation threshold exceeded - Answer reuse violations"
                termination_flags.append("ANSWER_REUSE_DETECTED")
            else:
                termination_reason = f"Violation threshold exceeded - {', '.join(threshold_violations)}"
                termination_flags.extend(threshold_violations)
        # Check for timeout violations
        elif "SESSION_TIMEOUT" in flags:
            termination_reason = "Session timeout - Maximum exam duration exceeded"
            termination_flags.append("SESSION_TIMEOUT")
        elif "ANSWER_TIMEOUT" in flags:
            termination_reason = "Answer timeout - Per-question time limit exceeded"
            termination_flags.append("ANSWER_TIMEOUT")
        # Check for normal completion
        elif s.get("asked_main", 0) >= s.get("limit", 0):
            termination_reason = "Normal completion - Question limit reached (all questions answered)"
        else:
            termination_reason = "Normal completion - Exam finished"
        
        lines.append(f"Termination Reason: {termination_reason}")
        if termination_flags:
            lines.append(f"Termination Flags: {', '.join(termination_flags)}")
    else:
        lines.append("Termination Reason: Unknown (exam phase not marked as complete)")
    
    lines.append("")
    lines.append("=== Viva Voce Transcript ===")
    for m in s["history"]:
        role = "Examiner" if m["role"] == "assistant" else "Student"
        lines.append(f"{role}: {m['content']}")
    lines.append("")

    if s["rubrics"]:
        lines.append("=== Per-Block Rubric Scores (Main+Follow-ups) ===")
        for i, rub in enumerate(s["rubrics"], start=1):
            lines.append(f"Q{i} Block:")
            lines.append(f"  Conceptual: {rub.get('Conceptual', 0)}")
            lines.append(f"  Analytical: {rub.get('Analytical', 0)}")
            lines.append(f"  Application: {rub.get('Application', 0)}")
            lines.append(f"  Reflection: {rub.get('Reflection', 0)}")
            lines.append(f"  Overall: {rub.get('Overall', 0)}")
        lines.append("")

    # --- Proctor Summary (human-readable) ---
    st = s.get("proctor_state")
    if isinstance(st, ProctorState):
        lines.append("=== Proctor Summary ===")
        g = s.get("proctor_summary", {}) or {}
        # Ensure flag counts are present in the global summary
        fc = g.get("flag_counts")
        if not fc:
            fc = dict(getattr(st, "flag_counts", {}))
            if fc:
                g = dict(g)
                g["flag_counts"] = fc
                g["flags_total"] = sum(fc.values()) if fc else 0

        lines.append(
            f"Frames: {g.get('frames','?')}, "
            f"Face%: {int(100*(g.get('face_present_ratio',0) or 0))}%, "
            f"Away%: {int(100*(g.get('away_ratio',0) or 0))}%, "
            f"Multi-face%: {int(100*(g.get('multi_face_ratio',0) or 0))}%"
        )
        if fc:
            lines.append("Flags: " + ", ".join([f"{k}={v}" for k, v in fc.items()]) + f" (total={sum(fc.values())})")
        else:
            lines.append("Flags: none")
        # Include a bounded sample of events for readability
        ev_sample = getattr(st, "flags", [])[:50]
        if ev_sample:
            lines.append("Flag Events:")
            for ev in ev_sample:
                detail_str = json.dumps(ev.get("detail", {}), separators=(",", ":"))
                lines.append(f"- {ev.get('ts_iso','?')} {ev.get('tag','?')} {detail_str}")
        lines.append("")

    # --- Audio Analysis Summary (human-readable) ---
    audio_flags_list = s.get("flags", [])
    audio_flag_counts = {}
    for flag in audio_flags_list:
        if flag in ("VOICEPRINT_MISMATCH", "UNNATURAL_SPEECH_RATE", "NO_HESITATION_PATTERN", 
                    "LEXICAL_INCONSISTENCY", "ZERO_PAUSE_DELIVERY", "PROFANITY_DETECTED", 
                    "ANSWER_REUSE_DETECTED", "SESSION_TIMEOUT", "ANSWER_TIMEOUT"):
            audio_flag_counts[flag] = audio_flag_counts.get(flag, 0) + 1
    
    # Audio analysis is always enabled by default
    lines.append("=== Audio Analysis Summary ===")
    lines.append("Audio Analysis: Enabled")
    if audio_flag_counts:
        lines.append("Flags: " + ", ".join([f"{k}={v}" for k, v in audio_flag_counts.items()]) + f" (total={sum(audio_flag_counts.values())})")
    else:
        lines.append("Flags: none")
    lines.append("")

    # --- Timing & Performance Summary (human-readable) ---
    session_start_time = s.get("session_start_time", 0)
    if session_start_time:
        total_duration_seconds = time.time() - session_start_time
        minutes = int(total_duration_seconds // 60)
        seconds = int(total_duration_seconds % 60)
        lines.append("=== Timing & Performance Summary ===")
        lines.append(f"Total Duration: {minutes}m {seconds}s ({total_duration_seconds:.2f}s)")
        
        # Calculate MAX_SESSION_DURATION_SEC dynamically
        max_timeout = get_max_answer_timeout_sec_fn()  # Use helper function for thread safety
        n_questions = s.get("limit", len([m for m in s.get("history", []) if m.get("role") == "assistant"]))
        followups_max = s.get("followups_max", get_followups_max())
        max_session_duration = (max_timeout + PROCESSING_BUFFER_SEC + SESSION_BUFFER_SEC) * (n_questions + (n_questions * followups_max))
        lines.append(f"Session Timeout Limit: {max_session_duration // 60} minutes")
        lines.append(f"Answer Timeout Limit: {max_timeout // 60} minutes")
        
        # Calculate average response time
        n_questions_asked = len([m for m in s.get("history", []) if m.get("role") == "assistant"])
        if n_questions_asked > 0:
            avg_time = round(total_duration_seconds / n_questions_asked, 2)
            avg_min = int(avg_time // 60)
            avg_sec = int(avg_time % 60)
            if avg_min > 0:
                lines.append(f"Average Response Time: {avg_min}m {avg_sec}s per question")
            else:
                lines.append(f"Average Response Time: {avg_sec}s per question")
        
        answers_count = len(s.get("answers_tslog_all", []))
        if answers_count > 0:
            lines.append(f"Total Answers Provided: {answers_count}")
        
        lines.append("")

    plaintext = "\n".join(lines).encode("utf-8")
    transcript_sha256 = hashlib.sha256(plaintext).hexdigest()

    # Prepare answer timestamps for Merkle root
    answers = s.get("answers_tslog_all", []) or []
    if not answers:
        # Build synthetic timestamps from chat history if needed
        base = datetime.now(timezone.utc).replace(microsecond=0)
        idx = 0
        for m in s["history"]:
            if m["role"] == "user":
                idx += 1
                answers.append({"ts_iso": (base + timedelta(seconds=idx)).isoformat() + "Z", "text": m["content"]})
    merkle_root_bytes = answers_to_merkle(answers)
    merkle_root_b64 = base64.urlsafe_b64encode(merkle_root_bytes).decode().rstrip("=")

    # Device key (Ed25519) used for signing the receipt core
    priv = get_or_create_device_key(s)
    device_pubkey_b64 = base64.urlsafe_b64encode(pubkey_bytes(priv)).decode().rstrip("=")

    # ----------------------------
    # Build receipt core (machine-readable)
    # ----------------------------
    receipt_core = {
        "session_id": s.get("session_id", ""),
        "student_id": s.get("student_id", ""),
        "started_at": s.get("started_at", ""),
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "course_id": course_id,      # Use state value
        "exam_id": exam_id,          # Use state value
        "section_id": section_id,    # Use state value
        "start_date": start_date,    # Use state value
        "end_date": end_date,        # Use state value
        "followups_min": followups_min,  # Use state value
        "followups_max": followups_max,  # Use state value
        "receipt_version": RECEIPT_VERSION,
        "app_version": APP_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "models": model_versions(),
        "otet": s["otet"],
        "device_pubkey": device_pubkey_b64,
        "merkle_root": merkle_root_b64,
        "transcript_sha256": transcript_sha256,
        "continuity_mode": continuity_mode(),
        "context_strategy": "random_chunk",
        "chunks_total": len(get_chunks_fn()),
        # Textbook integrity verification (FERPA-compliant: hash of textbook content, not student data)
        "textbook_sha256": get_textbook_sha256_fn(),
        # Question provenance tracking for auditability (FERPA-compliant: only cryptographic hashes, no PII)
        "questions_provenance": s.get("questions_meta", []),
    }

    # Attach proctor summary + thresholds + flag telemetry
    st = s.get("proctor_state")
    if isinstance(st, ProctorState):
        global_stats = s.get("proctor_summary", {}) or {}
        blocks = s.get("proctor_blocks", []) or []

        # Normalize flag counts into global_stats if missing
        if "flag_counts" not in global_stats:
            global_stats = dict(global_stats)
            global_stats["flag_counts"] = dict(getattr(st, "flag_counts", {}))
            global_stats["flags_total"] = sum(global_stats["flag_counts"].values()) if global_stats["flag_counts"] else 0

        away = float(global_stats.get("away_ratio", 0.0) or 0.0)
        multi = float(global_stats.get("multi_face_ratio", 0.0) or 0.0)

        # Get away_ratio_threshold from PROCTOR_CONFIG (default to 0.5 if not set)
        away_ratio_threshold = PROCTOR_CONFIG.get("away_ratio_threshold", 0.5)
        
        if multi > 0.02 and not PROCTOR_RULES["allow_multi_face"]:
            verdict, reason = "FAIL", "Multiple faces detected"
        elif away > away_ratio_threshold:
            verdict, reason = "WARN", "Frequent looking away"
        else:
            verdict, reason = "OK", "Within thresholds"

        # SIMPLICITY: Handle optional import gracefully (Principle #19)
        # PROCTOR_FLAG_RULES may not be imported in all contexts
        try:
            flag_rules = PROCTOR_FLAG_RULES
        except NameError:
            # Fallback to empty dict if PROCTOR_FLAG_RULES not available
            flag_rules = {}

        receipt_core["proctor"] = {
            "enabled": True,
            "global": global_stats,
            "blocks": blocks,
            "rules": {
                "yaw_max_deg": PROCTOR_RULES["yaw_max_deg"],
                "pitch_max_deg": PROCTOR_RULES["pitch_max_deg"],
                "away_min_consec_frames": PROCTOR_RULES["away_min_consec_frames"],
                "allow_multi_face": PROCTOR_RULES["allow_multi_face"],
                "flag_rules": flag_rules,
            },
            # Compact telemetry for audits (no frames stored)
            "flags": {
                "counts": dict(getattr(st, "flag_counts", {})),
                "events_sample": getattr(st, "flags", [])[:50],
            },
            "verdict": verdict,
            "reason": reason,
        }
    else:
        receipt_core["proctor"] = {"enabled": False}

    # Attach audio analysis flags (voiceprint + stylometric + session control)
    audio_flags = s.get("flags", [])
    audio_flag_counts = {}
    for flag in audio_flags:
        if flag in ("VOICEPRINT_MISMATCH", "UNNATURAL_SPEECH_RATE", "NO_HESITATION_PATTERN", 
                    "LEXICAL_INCONSISTENCY", "ZERO_PAUSE_DELIVERY", "PROFANITY_DETECTED",
                    "ANSWER_REUSE_DETECTED", "SESSION_TIMEOUT", "ANSWER_TIMEOUT"):
            audio_flag_counts[flag] = audio_flag_counts.get(flag, 0) + 1
    
    # Calculate audio verdict and reason from flag counts
    audio_flags_total = sum(audio_flag_counts.values())
    audio_verdict = ""
    audio_reason = ""
    
    if audio_flags_total > 0:
        # Determine severity based on flag types
        high_severity_flags = ["VOICEPRINT_MISMATCH", "ANSWER_REUSE_DETECTED"]
        has_high_severity = any(audio_flag_counts.get(flag, 0) > 0 for flag in high_severity_flags)
        
        if has_high_severity:
            audio_verdict = "FAIL"
            audio_reason = "High severity anomalies detected"
        else:
            audio_verdict = "WARN"
            audio_reason = "Anomalies detected"
        
        # Build detailed reason from flags
        detected_flags = [flag for flag, count in audio_flag_counts.items() if count > 0]
        if detected_flags:
            audio_reason = f"Anomalies: {', '.join(detected_flags)}"
    else:
        audio_verdict = "OK"
        audio_reason = "No anomalies detected"
    
    # Audio analysis is always enabled by default
    receipt_core["audio_analysis"] = {
        "enabled": True,
        "flag_counts": audio_flag_counts,
        "flags_total": audio_flags_total,
        "verdict": audio_verdict,
        "reason": audio_reason,
    }

    # ----------------------------
    # SECURITY EVENTS: Log security events for audit trail
    # ----------------------------
    security_events = s.get("security_events", [])
    tab_focus_events = s.get("tab_focus_events", [])
    clipboard_events = s.get("clipboard_events", [])
    ip_address = s.get("ip_address", "UNKNOWN")
    
    receipt_core["security"] = {
        "ip_address": ip_address,
        "security_events_count": len(security_events),
        "security_events_sample": security_events[:50],  # Sample of first 50 events
        "tab_focus_events_count": len(tab_focus_events),
        "tab_focus_events_sample": tab_focus_events[:20],  # Sample of first 20 events
        "clipboard_events_count": len(clipboard_events),
        "clipboard_events_sample": clipboard_events[:20],  # Sample of first 20 events
    }
    
    # ----------------------------
    # TIMING & PERFORMANCE METRICS: Add timing data for anomaly detection
    # ----------------------------
    session_start_time = s.get("session_start_time", 0)
    if session_start_time:
        total_duration_seconds = time.time() - session_start_time
        
        # Calculate MAX_SESSION_DURATION_SEC dynamically
        max_timeout = get_max_answer_timeout_sec_fn()
        n_questions = s.get("limit", len([m for m in s.get("history", []) if m.get("role") == "assistant"]))
        followups_max = s.get("followups_max", get_followups_max())
        max_session_duration = (max_timeout + PROCESSING_BUFFER_SEC + SESSION_BUFFER_SEC) * (n_questions + (n_questions * followups_max))
        
        receipt_core["timing"] = {
            "total_duration_seconds": round(total_duration_seconds, 2),
            "session_timeout_limit_seconds": max_session_duration,
            "answer_timeout_limit_seconds": max_timeout,
            "answers_count": len(answers) if answers else 0,
        }
        
        # Calculate average response time if we have answers
        if answers and len(answers) > 0:
            # Estimate avg response time from total duration divided by number of questions
            n_questions_asked = len([m for m in s.get("history", []) if m.get("role") == "assistant"])
            if n_questions_asked > 0:
                avg_response_time = round(total_duration_seconds / n_questions_asked, 2)
                receipt_core["timing"]["avg_response_time_seconds"] = avg_response_time

    # ----------------------------
    # RUBRIC SCORES: Add numeric scores to receipt_core for encrypted export
    # FERPA COMPLIANCE: Numeric scores are included in encrypted export (.enc file)
    # but hidden from students during exam (only qualitative assessment shown)
    # ----------------------------
    if s.get("rubrics"):
        # Include all rubric scores (Conceptual, Analytical, Application, Reflection, Overall)
        # These are stored in encrypted receipt_core for instructor access after decryption
        receipt_core["rubrics"] = s["rubrics"]
    
    # ----------------------------
    # EXAM CONFIGURATION: Add exam settings for audit compliance
    # ----------------------------
    receipt_core["exam_config"] = {
        "followups_min": followups_min,
        "followups_max": followups_max,
    }

    # ----------------------------
    # FERPA COMPLIANCE: Encrypt entire receipt_core JSON blob
    # Signature and AAD are computed from plaintext before encryption
    # ----------------------------
    # Compute signature and AAD from plaintext receipt_core (before encryption)
    core_bytes = json.dumps(receipt_core, sort_keys=True, separators=(",", ":")).encode("utf-8")
    aad = hashlib.sha256(core_bytes).digest()
    signature_b64 = base64.urlsafe_b64encode(priv.sign(hashlib.sha256(core_bytes).digest())).decode().rstrip("=")
    
    # Encrypt entire receipt_core JSON blob
    core_encrypted = encrypt_receipt_core(receipt_core)
    
    receipt = {"algo": "Ed25519-SHA256", "core": core_encrypted, "signature": signature_b64}

    # Seal transcript with AES-GCM (AAD-bound to receipt core)
    sealed = encrypt_bytes(plaintext, passphrase, aad=aad)  # Use state value

    outer = {
        "magic": "VIVA2",
        "sealed_blob_b64": base64.b64encode(sealed).decode("ascii"),
        "receipt": receipt
    }

    # Write the encrypted bundle to a temp file first
    enc_tmp = None
    custom_filepath = None
    try:
        # Use platform provider to get proper temp directory (avoids /app directory issue)
        platform_provider = get_default_platform_provider()
        temp_dir = platform_provider.get_temp_dir()
        enc_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".enc", mode="w", encoding="utf-8", dir=temp_dir)
        json.dump(outer, enc_tmp, ensure_ascii=False, separators=(",", ":"))
        enc_tmp.close()

        # Helper function to sanitize filename components
        def sanitize_filename(text):
            """Remove invalid filename characters"""
            if not text:
                return "UNKNOWN"
            # Replace invalid chars with underscore
            text = re.sub(r'[<>:"/\\|?*]', '_', str(text))
            # Remove leading/trailing spaces and dots
            text = text.strip('. ')
            return text if text else "UNKNOWN"

        # Generate custom filename: CourseID_ExamID_Section_random.enc
        # FERPA COMPLIANCE: student_id removed from filename to protect PII
        # Student ID remains accessible in encrypted transcript and receipt_core after decryption
        course_id_clean = sanitize_filename(s.get("course_id", "UNKNOWN"))
        exam_id_clean = sanitize_filename(s.get("exam_id", "UNKNOWN"))
        section_id_clean = sanitize_filename(s.get("section_id", "UNKNOWN"))
        random_suffix = hashlib.sha256(os.urandom(16)).hexdigest()[:8]  # 8-char random suffix

        custom_filename = f"{course_id_clean}_{exam_id_clean}_{section_id_clean}_{random_suffix}.enc"

        # Get directory of temp file
        temp_dir = os.path.dirname(enc_tmp.name)
        custom_filepath = os.path.join(temp_dir, custom_filename)

        # Rename temp file to custom filename
        try:
            os.rename(enc_tmp.name, custom_filepath)
        except OSError as rename_error:
            # If rename fails (e.g., file system doesn't support rename, or file exists)
            # Try to copy instead
            try:
                shutil.copy2(enc_tmp.name, custom_filepath)
                # Remove original temp file only if copy succeeds
                try:
                    os.remove(enc_tmp.name)
                except Exception:
                    pass  # Ignore cleanup errors
            except Exception as copy_error:
                # If copy also fails, use original temp filename
                logger.warning(
                    "enc_file_rename_failed",
                    session_id=s.get("session_id", "unknown"),
                    temp_path=enc_tmp.name,
                    target_path=custom_filepath,
                    error_type=type(copy_error).__name__,
                    error_message=str(copy_error)[:200]
                )
                custom_filepath = enc_tmp.name
        
        # Validate file was created successfully
        if not os.path.exists(custom_filepath):
            raise FileNotFoundError(f"Failed to create .enc file at {custom_filepath}")
        
        # Validate file is readable and not empty
        try:
            with open(custom_filepath, "rb") as f:
                file_size = len(f.read())
            if file_size == 0:
                raise ValueError(f".enc file is empty: {custom_filepath}")
        except Exception as validation_error:
            logger.error(
                "enc_file_validation_failed",
                session_id=s.get("session_id", "unknown"),
                file_path=custom_filepath,
                error_type=type(validation_error).__name__,
                error_message=str(validation_error)[:200]
            )
            raise
        
    except Exception as file_error:
        # Log error and return error message instead of raising (for better UX)
        logger.error(
            "enc_file_creation_failed",
            session_id=s.get("session_id", "unknown"),
            error_type=type(file_error).__name__,
            error_message=str(file_error)[:200]
        )
        # Clean up temp file if it exists
        if enc_tmp and os.path.exists(enc_tmp.name):
            try:
                os.unlink(enc_tmp.name)
            except Exception:
                pass
        # Return error message instead of raising (for better UX)
        return "", f"❌ Failed to create encrypted file: {str(file_error)[:200]}"

    # Average score for quick summary
    avg = round(sum(s["scores"]) / len(s["scores"])) if s["scores"] else 0

    # ----------------------------
    # Mark complete & stop proctor; then wipe local state
    # ----------------------------
    s["phase"] = "complete"
    st = s.get("proctor_state")
    if isinstance(st, ProctorState):
        try:
            st.stop()
        except Exception:
            pass
    s["proctor_summary"] = {"status": "ended"}

    # Import wipe function
    from exam.export.wipe import auto_wipe_local_after_export
    
    removed = auto_wipe_local_after_export(s)
    
    # FERPA COMPLIANCE: Explicitly delete video/audio files after analysis
    # Video, Audio, and Biometric Data (high sensitivity) - Mandate #11
    # Remote processing must be encrypted, non-persistent, with deletion post-analysis
    from shared.ferpa_data_erasure import erase_media_files
    try:
        media_erased = erase_media_files(
            session_id=s.get("session_id", ""),
            student_id=s.get("student_id")
        )
        if media_erased:
            removed.extend([f"media:{os.path.basename(f)}" for f in media_erased])
    except Exception:
        # Don't fail export if media deletion fails
        pass
    
    summary_md = f"Exam completed. Local state removed: {', '.join(removed) if removed else 'none'}"

    # This will no-op after seal due to tombstone/PERSIST_OK
    save_state_to_disk_fn(s)
    
    # Clear auto-saved state on exam completion to prevent resume
    # This ensures the exam cannot be resumed after completion
    try:
        p = _paths_for_session(s)
        if os.path.exists(p["STATE_PATH"]):
            # Remove auto-saved state file to prevent resume
            try:
                os.remove(p["STATE_PATH"])
            except Exception:
                pass  # Ignore errors when removing state file
    except Exception:
        pass  # Ignore errors if paths don't exist

    # Graceful failure: Validate file path before returning (Principle #16)
    # Prevents Gradio from trying to process invalid paths like '/app' directory
    if not custom_filepath:
        logger.error(
            "invalid_file_path_returned",
            session_id=s.get("session_id", "unknown"),
            message="File path is None or empty - returning empty string to prevent Gradio error"
        )
        return "", f"❌ Failed to create encrypted file: File path not set"
    
    if not os.path.exists(custom_filepath):
        logger.error(
            "file_path_does_not_exist",
            session_id=s.get("session_id", "unknown"),
            file_path=custom_filepath,
            message="File path does not exist - returning empty string to prevent Gradio error"
        )
        return "", f"❌ Failed to create encrypted file: File does not exist"
    
    if not os.path.isfile(custom_filepath):
        logger.error(
            "file_path_is_not_file",
            session_id=s.get("session_id", "unknown"),
            file_path=custom_filepath,
            is_directory=os.path.isdir(custom_filepath) if os.path.exists(custom_filepath) else False,
            message="File path is not a file (possibly a directory) - returning empty string to prevent Gradio error"
        )
        return "", f"❌ Failed to create encrypted file: Path is not a valid file"

    return custom_filepath, summary_md


__all__ = ["finalize_and_export_encrypted"]

