"""
FERPA-compliant role-based access control (RBAC) module.

This module provides role-based access control for FERPA compliance, ensuring
only authorized educational personnel can access student data.

FERPA COMPLIANCE: Only authorized educational personnel may access identifiable student data.
Code must enforce role-based conditional logic—not rely solely on front-end or API gateway.

**Key Functions**:
- `UserRole`: Enum defining user roles (STUDENT, INSTRUCTOR, ADMIN)
- `get_user_role()`: Extract role from state/session
- `require_role()`: Validate role before accessing student data
- `has_instructor_access()`: Convenience function for instructor access

**Usage Example**:
    ```python
    from shared.ferpa_rbac import require_role, UserRole
    
    # In a handler function
    def handle_decrypt(state, dependencies):
        # Check role before accessing student data
        require_role_fn = dependencies.get("require_role")
        if require_role_fn and not require_role_fn(state, UserRole.INSTRUCTOR, "grade_review"):
            return error("Access restricted under student privacy safeguards.")
        
        # Proceed with decryption...
    ```

**Safety**:
- All functions use safe defaults (allow access if RBAC disabled)
- Can be enabled/disabled via FERPA_RBAC_ENABLED environment variable
- Non-breaking: Existing code works without RBAC
"""

import os
from enum import Enum
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone


class UserRole(Enum):
    """
    User roles for FERPA-compliant access control.
    
    FERPA COMPLIANCE: Only authorized educational personnel may access 
    identifiable student data.
    """
    STUDENT = "STUDENT"
    INSTRUCTOR = "INSTRUCTOR"
    ADMIN = "ADMIN"


def is_rbac_enabled() -> bool:
    """
    Check if RBAC is enabled via environment variable.
    
    Returns:
        True if RBAC is enabled, False otherwise
    """
    return os.getenv("FERPA_RBAC_ENABLED", "false").lower() == "true"


def get_user_role(state: Dict[str, Any]) -> Optional[UserRole]:
    """
    Extract user role from state/session dictionary.
    
    FERPA COMPLIANCE: Determines WHO is accessing student data.
    
    Args:
        state: State dictionary (may contain user_role)
        
    Returns:
        UserRole enum value if found, None otherwise
        
    Note:
        Role can be set in state by:
        - Environment variable (for dash.ipynb → INSTRUCTOR)
        - Session context (for exam.ipynb → STUDENT)
        - External auth system (future)
    """
    if not state:
        return None
    
    role_str = state.get("user_role")
    if not role_str:
        return None
    
    try:
        return UserRole(role_str)
    except (ValueError, TypeError):
        return None


def require_role(
    state: Dict[str, Any],
    required_role: UserRole,
    educational_purpose: str,
    log_ferpa_access_fn: Optional[Callable] = None
) -> bool:
    """
    Check if user has required role for accessing student data.
    
    FERPA COMPLIANCE: Validates explicit authorization before accessing student PII.
    Every action involving student data must have a clear educational purpose.
    
    Args:
        state: State dictionary (must contain user_role)
        required_role: Required role (UserRole enum)
        educational_purpose: Educational purpose for access (e.g., "grade_review", "exam_taking")
        log_ferpa_access_fn: Optional function to log FERPA access (for audit trail)
        
    Returns:
        True if user has required role, False otherwise
        
    Note:
        - If RBAC is disabled (FERPA_RBAC_ENABLED=false), always returns True (backward compatibility)
        - If role cannot be determined, returns False (fail-safe)
        - Logs access for audit trail if log_ferpa_access_fn provided
    """
    # Backward compatibility: Allow access if RBAC disabled
    if not is_rbac_enabled():
        return True
    
    # Get user role from state
    user_role = get_user_role(state)
    
    # Fail-safe: If role cannot be determined, deny access
    if user_role is None:
        return False
    
    # Check if role matches required role
    has_access = user_role == required_role
    
    # Log access for audit trail (FERPA Mandate #15)
    if log_ferpa_access_fn and has_access:
        try:
            log_ferpa_access_fn(
                who=user_role.value,
                what="student_data_access",
                why=educational_purpose,
                when=datetime.now(timezone.utc)
            )
        except Exception:
            # Don't fail access check if logging fails
            pass
    
    return has_access


def has_instructor_access(
    state: Dict[str, Any],
    educational_purpose: str,
    log_ferpa_access_fn: Optional[Callable] = None
) -> bool:
    """
    Convenience function to check if user has instructor access.
    
    FERPA COMPLIANCE: Only instructors can access student exam data for grading.
    
    Args:
        state: State dictionary
        educational_purpose: Educational purpose (e.g., "grade_review", "batch_decrypt")
        log_ferpa_access_fn: Optional audit logging function
        
    Returns:
        True if user is INSTRUCTOR or ADMIN, False otherwise
    """
    return (
        require_role(state, UserRole.INSTRUCTOR, educational_purpose, log_ferpa_access_fn) or
        require_role(state, UserRole.ADMIN, educational_purpose, log_ferpa_access_fn)
    )


def has_student_access(
    state: Dict[str, Any],
    educational_purpose: str,
    log_ferpa_access_fn: Optional[Callable] = None
) -> bool:
    """
    Convenience function to check if user has student access.
    
    FERPA COMPLIANCE: Students can only access their own exam data.
    
    Args:
        state: State dictionary
        educational_purpose: Educational purpose (e.g., "exam_taking", "view_results")
        log_ferpa_access_fn: Optional audit logging function
        
    Returns:
        True if user is STUDENT, False otherwise
    """
    return require_role(state, UserRole.STUDENT, educational_purpose, log_ferpa_access_fn)


def can_access_student_data(
    state: Dict[str, Any],
    target_student_id: str,
    educational_purpose: str,
    log_ferpa_access_fn: Optional[Callable] = None
) -> bool:
    """
    Check if user can access data for a specific student.
    
    FERPA COMPLIANCE: Minimum Necessary Access (Mandate #2)
    - Access only the student data necessary to perform the approved function
    - Instructors can access any student data (for grading)
    - Students can only access their own data
    - Admins can access any student data
    
    Args:
        state: State dictionary (must contain user_role and optionally student_id)
        target_student_id: Student ID whose data is being accessed
        educational_purpose: Educational purpose (e.g., "grade_review", "exam_taking")
        log_ferpa_access_fn: Optional audit logging function
        
    Returns:
        True if user can access the target student's data, False otherwise
        
    Examples:
        # Instructor accessing any student's data
        instructor_state = {"user_role": "INSTRUCTOR"}
        assert can_access_student_data(instructor_state, "student_123", "grade_review") == True
        
        # Student accessing their own data
        student_state = {"user_role": "STUDENT", "student_id": "student_123"}
        assert can_access_student_data(student_state, "student_123", "exam_taking") == True
        
        # Student trying to access another student's data
        assert can_access_student_data(student_state, "student_456", "exam_taking") == False
    """
    # Get user role
    user_role = get_user_role(state)
    
    if user_role is None:
        return False
    
    # Instructors and Admins can access any student's data
    if user_role in [UserRole.INSTRUCTOR, UserRole.ADMIN]:
        # Log access for audit trail
        if log_ferpa_access_fn:
            try:
                log_ferpa_access_fn(
                    who=user_role.value,
                    what="student_data_access",
                    why=educational_purpose,
                    when=datetime.now(timezone.utc),
                    additional_context={"target_student_id": target_student_id[:4] + "****"}  # Partial ID for audit
                )
            except Exception:
                pass
        return True
    
    # Students can only access their own data
    if user_role == UserRole.STUDENT:
        user_student_id = state.get("student_id")
        if not user_student_id:
            return False
        
        # Check if accessing own data
        can_access = user_student_id == target_student_id
        
        # Log access for audit trail
        if can_access and log_ferpa_access_fn:
            try:
                log_ferpa_access_fn(
                    who=user_role.value,
                    what="own_student_data_access",
                    why=educational_purpose,
                    when=datetime.now(timezone.utc)
                )
            except Exception:
                pass
        
        return can_access
    
    # Unknown role - deny access
    return False


def format_ferpa_block_error(correlation_id: Optional[str] = None) -> str:
    """
    Format FERPA compliance blocking error message.
    
    FERPA COMPLIANCE: Educational-friendly error message with correlation ID.
    
    Args:
        correlation_id: Optional correlation ID for traceability
        
    Returns:
        Formatted error message string
    """
    base_msg = "Access restricted under student privacy safeguards."
    if correlation_id:
        return f"{base_msg} Reference ID: {correlation_id}"
    return base_msg


__all__ = [
    "UserRole",
    "is_rbac_enabled",
    "get_user_role",
    "require_role",
    "has_instructor_access",
    "has_student_access",
    "can_access_student_data",
    "format_ferpa_block_error",
]

