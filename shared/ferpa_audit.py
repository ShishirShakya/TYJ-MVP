"""
FERPA-compliant audit logging module.

This module provides audit trail logging for FERPA compliance, tracking
all access to student PII with WHO/WHAT/WHY/WHEN information.

FERPA COMPLIANCE: Every access to student PII must be traceable to:
- WHO accessed it (role/ID)
- WHAT was accessed
- WHY (educational purpose)
- WHEN (timestamp)

**Key Functions**:
- `log_ferpa_access()`: Log access to student data
- `get_audit_log_path()`: Get path for audit log file
- `read_audit_logs()`: Read audit logs (for compliance reviews)

**Usage Example**:
    ```python
    from shared.ferpa_audit import log_ferpa_access
    
    # Log access to student data
    log_ferpa_access(
        who="INSTRUCTOR",
        what="batch_decrypt",
        why="grade_review",
        when=datetime.now(timezone.utc)
    )
    ```

**Storage**:
- Audit logs stored in JSON format
- One log file per day (rotates automatically)
- ~370 bytes per log entry
- Retention: Configurable (default: 7 years for FERPA)
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path


def get_audit_log_dir() -> str:
    """
    Get directory for audit log files.
    
    Returns:
        Path to audit log directory (creates if doesn't exist)
    """
    # Use environment variable if set, otherwise default to ./ferpa_audit_logs
    log_dir = os.getenv("FERPA_AUDIT_LOG_DIR", "./ferpa_audit_logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    return log_dir


def get_audit_log_path(date: Optional[datetime] = None) -> str:
    """
    Get path to audit log file for a specific date.
    
    Args:
        date: Date for log file (defaults to today)
        
    Returns:
        Path to audit log file (e.g., "./ferpa_audit_logs/2024-01-15.json")
    """
    if date is None:
        date = datetime.now(timezone.utc)
    
    log_dir = get_audit_log_dir()
    date_str = date.strftime("%Y-%m-%d")
    return os.path.join(log_dir, f"{date_str}.json")


def log_ferpa_access(
    who: str,
    what: str,
    why: str,
    when: datetime,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log access to student PII for FERPA audit trail.
    
    FERPA COMPLIANCE: Every access to student PII must be traceable to:
    - WHO accessed it (role/ID)
    - WHAT was accessed
    - WHY (educational purpose)
    - WHEN (timestamp)
    
    Args:
        who: Role/user identifier (e.g., "INSTRUCTOR", "ADMIN", "instructor_123")
        what: What was accessed (e.g., "batch_decrypt", "student_exam_data", "grade_export")
        why: Educational purpose (e.g., "grade_review", "exam_taking", "compliance_audit")
        when: Timestamp of access (UTC)
        user_id: Optional user identifier (for audit trail)
        session_id: Optional session identifier (for correlation)
        additional_context: Optional additional context (sanitized, no PII)
        
    Note:
        - All data is sanitized (no student PII in logs)
        - Logs are written atomically (temp file + replace)
        - Logs are rotated daily (one file per day)
    """
    try:
        # Build audit log entry
        log_entry = {
            "who": who,
            "what": what,
            "why": why,
            "when": when.isoformat() + "Z",
        }
        
        # Add optional fields if provided
        if user_id:
            log_entry["user_id"] = user_id
        if session_id:
            # FERPA COMPLIANCE: Obfuscate session ID in audit logs
            log_entry["session_id"] = f"****{session_id[-4:]}" if len(session_id) > 4 else "****"
        
        if additional_context:
            # Sanitize additional context (remove any PII)
            sanitized_context = {}
            for key, value in additional_context.items():
                # Skip any fields that might contain PII
                if key.lower() not in ["student_id", "student_name", "email", "pii"]:
                    sanitized_context[key] = value
            if sanitized_context:
                log_entry["context"] = sanitized_context
        
        # Get log file path
        log_path = get_audit_log_path(when)
        
        # Read existing logs (if file exists)
        existing_logs = []
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    existing_logs = json.load(f)
                    if not isinstance(existing_logs, list):
                        existing_logs = []
            except (json.JSONDecodeError, IOError):
                existing_logs = []
        
        # Append new log entry
        existing_logs.append(log_entry)
        
        # Write logs atomically (temp file + replace)
        import tempfile
        log_dir = os.path.dirname(log_path)
        fd, tmp_path = tempfile.mkstemp(dir=log_dir, prefix="._ferpa_audit.", suffix=".tmp")
        
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(existing_logs, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomically replace
            os.replace(tmp_path, log_path)
            
            # Set file permissions (owner-only read/write)
            try:
                os.chmod(log_path, 0o600)
            except (OSError, AttributeError):
                # Windows doesn't support chmod - ignore
                pass
                
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
            
    except Exception as e:
        # Don't fail the operation if audit logging fails
        # Log error to application log (not audit log)
        import structlog
        logger = structlog.get_logger()
        logger.warning(
            "ferpa_audit_logging_failed",
            error=str(e),
            who=who,
            what=what,
            why=why,
            message="FERPA audit logging failed - operation continues"
        )


def read_audit_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    who: Optional[str] = None,
    what: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Read audit logs for compliance review.
    
    FERPA COMPLIANCE: Allows review of access logs for compliance audits.
    
    Args:
        start_date: Start date for log retrieval (defaults to 30 days ago)
        end_date: End date for log retrieval (defaults to today)
        who: Filter by role/user (optional)
        what: Filter by access type (optional)
        
    Returns:
        List of audit log entries matching criteria
    """
    from datetime import timedelta
    
    if start_date is None:
        start_date = datetime.now(timezone.utc) - timedelta(days=30)
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    
    all_logs = []
    current_date = start_date.date()
    end_date_only = end_date.date()
    
    # Read logs for each day in range
    while current_date <= end_date_only:
        log_path = get_audit_log_path(datetime.combine(current_date, datetime.min.time()).replace(tzinfo=timezone.utc))
        
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    day_logs = json.load(f)
                    if isinstance(day_logs, list):
                        # Filter logs
                        for entry in day_logs:
                            if who and entry.get("who") != who:
                                continue
                            if what and entry.get("what") != what:
                                continue
                            all_logs.append(entry)
            except (json.JSONDecodeError, IOError):
                pass
        
        # Move to next day
        current_date += timedelta(days=1)
    
    return all_logs


__all__ = [
    "log_ferpa_access",
    "get_audit_log_path",
    "read_audit_logs",
]

