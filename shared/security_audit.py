"""
Security audit logging for compliance and monitoring.

Phase 3.4: Enhanced security audit logging for FERPA/GDPR compliance.

This module provides:
- Comprehensive audit logging for all security events
- User action tracking
- Data access logging
- Compliance reporting
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)

# Audit log directory
AUDIT_LOG_DIR = Path(os.getenv("AUDIT_LOG_DIR", "ferpa_audit_logs"))
AUDIT_LOG_DIR.mkdir(exist_ok=True, parents=True)


def log_security_event(
    event_type: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None
):
    """
    Log a security event for audit trail.
    
    Phase 3.4: Enhanced security audit logging.
    
    Args:
        event_type: Type of event (e.g., "LOGIN", "DATA_ACCESS", "CONFIG_CHANGE")
        user_id: User identifier (if available)
        session_id: Session identifier
        action: Action performed
        resource: Resource accessed/modified
        details: Additional event details
        ip_address: Client IP address
        user_agent: Client user agent
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "user_id": user_id,
        "session_id": session_id,
        "action": action,
        "resource": resource,
        "details": details or {},
        "ip_address": ip_address,
        "user_agent": user_agent
    }
    
    # Write to daily log file
    today = datetime.now(timezone.utc).date()
    log_file = AUDIT_LOG_DIR / f"{today.isoformat()}.json"
    
    # Append to log file (thread-safe append)
    try:
        # Read existing events
        events = []
        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                try:
                    events = json.load(f)
                except json.JSONDecodeError:
                    events = []
        
        # Append new event
        events.append(event)
        
        # Write back (atomic write)
        temp_file = log_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2, ensure_ascii=False)
        
        # Atomic rename
        temp_file.replace(log_file)
        
        # Also log to structured logger
        logger.info(
            "security_event_logged",
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            action=action,
            resource=resource
        )
        
    except Exception as e:
        logger.error(
            "audit_log_error",
            error=str(e),
            event_type=event_type,
            message="Failed to write audit log"
        )


def log_data_access(
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None
):
    """
    Log data access for compliance tracking.
    
    Phase 3.4: GDPR/FERPA compliance logging.
    
    Args:
        user_id: User identifier
        resource_type: Type of resource accessed (e.g., "exam", "transcript")
        resource_id: Resource identifier
        action: Action performed (e.g., "VIEW", "DOWNLOAD", "DELETE")
        session_id: Session identifier
        ip_address: Client IP address
    """
    log_security_event(
        event_type="DATA_ACCESS",
        user_id=user_id,
        session_id=session_id,
        action=action,
        resource=f"{resource_type}:{resource_id}",
        ip_address=ip_address
    )


def log_authentication_event(
    user_id: str,
    event_type: str,
    success: bool,
    ip_address: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
):
    """
    Log authentication events (login, logout, failed attempts).
    
    Phase 3.4: Security audit logging.
    
    Args:
        user_id: User identifier
        event_type: Event type (e.g., "LOGIN", "LOGOUT", "LOGIN_FAILED")
        success: Whether authentication succeeded
        ip_address: Client IP address
        details: Additional details
    """
    log_security_event(
        event_type=event_type,
        user_id=user_id,
        action="AUTHENTICATION",
        details={
            "success": success,
            **(details or {})
        },
        ip_address=ip_address
    )


def get_audit_logs(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    event_type: Optional[str] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve audit logs for compliance reporting.
    
    Phase 3.4: Compliance reporting.
    
    Args:
        start_date: Start date for log retrieval
        end_date: End date for log retrieval
        event_type: Filter by event type
        user_id: Filter by user ID
        
    Returns:
        List of audit log events
    """
    events = []
    
    # Determine date range
    if start_date is None:
        start_date = datetime.now(timezone.utc).replace(day=1)  # Start of month
    if end_date is None:
        end_date = datetime.now(timezone.utc)
    
    # Iterate through date range
    current_date = start_date.date()
    end_date_only = end_date.date()
    
    while current_date <= end_date_only:
        log_file = AUDIT_LOG_DIR / f"{current_date.isoformat()}.json"
        
        if log_file.exists():
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    day_events = json.load(f)
                    
                    # Filter events
                    for event in day_events:
                        event_dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
                        
                        if start_date <= event_dt <= end_date:
                            if event_type and event.get("event_type") != event_type:
                                continue
                            if user_id and event.get("user_id") != user_id:
                                continue
                            
                            events.append(event)
            except Exception as e:
                logger.warning(
                    "audit_log_read_error",
                    log_file=str(log_file),
                    error=str(e),
                    message="Failed to read audit log file"
                )
        
        # Move to next day
        from datetime import timedelta
        current_date += timedelta(days=1)
    
    # Sort by timestamp
    events.sort(key=lambda x: x.get("timestamp", ""))
    
    return events

