"""
State persistence functions for exam.ipynb.

This module contains functions for saving and loading state:
- Atomic secure file writing
- State persistence to disk
- Auto-save functionality
- State loading (currently disabled)

Serialization Strategy:
- Large/transient data (chunks, text, proctor_state) is excluded
- Bounded collections (history, answers_tslog_all) are truncated
- Only essential state is serialized to prevent memory growth
- See exam.state.serialization for details
"""

import os
import json
import tempfile
import threading
import time
from typing import Dict, Any, Optional
from collections import deque

# Platform-specific file locking
try:
    import fcntl  # POSIX file locking
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt  # Windows file locking
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

from exam.file_utils import _paths_for_session
from .core import ensure_state
from .serialization import prepare_state_for_serialization
from shared.time_provider import get_default_time_provider

# Per-file locks to prevent concurrent writes to the same session file
_file_locks: Dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()
_file_lock_access_times: Dict[str, float] = {}  # Track last access time for cleanup
_MAX_FILE_LOCKS = 10000  # Maximum number of file locks to keep in memory
_LOCK_CLEANUP_INTERVAL = 3600  # Clean up locks older than 1 hour


# Constants
AUTO_SAVE_INTERVAL_SEC = 30  # Auto-save every 30 seconds

# PERFORMANCE: Batched state save queue to reduce disk I/O (spd.txt #3, #7, cp.txt #9)
# Queue state saves and process them in batches to reduce write operations
_pending_state_saves: Dict[str, Dict[str, Any]] = {}  # session_id -> state dict
_save_queue_lock = threading.Lock()
_save_timer: Optional[threading.Timer] = None
_BATCH_SAVE_DELAY = 0.5  # Batch saves every 500ms (spd.txt #3)
_BATCH_SAVE_MAX_SIZE = 10  # Flush queue when it reaches this size


def _get_file_lock(path: str) -> threading.Lock:
    """
    Get or create a lock for a specific file path.
    
    Uses per-file locks to prevent concurrent writes to the same session file.
    This prevents race conditions when multiple requests try to save state
    for the same session simultaneously.
    
    MEMORY MANAGEMENT: Automatically cleans up old locks to prevent memory leaks.
    
    DETERMINISTIC: Uses TimeProvider for deterministic behavior (Principle #5).
    
    Args:
        path: File path to get lock for
        
    Returns:
        Threading lock for the file
    """
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    time_provider = get_default_time_provider()
    
    with _locks_lock:
        # Cleanup old locks if we have too many
        if len(_file_locks) > _MAX_FILE_LOCKS:
            _cleanup_old_file_locks()
        
        if path not in _file_locks:
            _file_locks[path] = threading.Lock()
        
        # Update access time
        _file_lock_access_times[path] = time_provider.time()
        
        return _file_locks[path]


def _cleanup_old_file_locks() -> None:
    """
    Clean up old file locks that haven't been accessed recently.
    
    This prevents memory leaks from accumulating locks for sessions that are no longer active.
    
    THREAD-SAFETY: This function assumes _locks_lock is already held by the caller.
    It should NOT acquire the lock itself to avoid deadlocks when called from _get_file_lock().
    
    DETERMINISTIC: Uses TimeProvider for deterministic behavior (Principle #5).
    """
    import os
    
    # DETERMINISTIC: Use time_provider instead of time.time() (Principle #5)
    time_provider = get_default_time_provider()
    current_time = time_provider.time()
    
    # RESOURCE MANAGEMENT: Configurable minimum locks to avoid thrashing
    # Read once at function start to avoid repeated env lookups
    _MIN_FILE_LOCKS = int(os.getenv("MIN_FILE_LOCKS", "1000"))  # Configurable minimum
    
    # THREAD-SAFETY: Assume lock is already held (called from _get_file_lock which holds the lock)
    # This prevents deadlock when cleanup is called while lock is held
    locks_to_remove = []
    
    # Find locks that haven't been accessed in the cleanup interval
    for path, last_access in list(_file_lock_access_times.items()):  # Use list() to avoid modification during iteration
        if current_time - last_access > _LOCK_CLEANUP_INTERVAL:
            locks_to_remove.append(path)
    
    # RESOURCE MANAGEMENT: If we exceed MAX_FILE_LOCKS, also remove oldest locks
    # This handles the case where many locks are created quickly (all with current timestamps)
    if len(_file_locks) > _MAX_FILE_LOCKS:
        # Sort all locks by access time (oldest first)
        all_locks_sorted = sorted(
            _file_lock_access_times.items(),
            key=lambda x: x[1]  # Sort by access time
        )
        # Remove oldest locks until we're below MAX_FILE_LOCKS
        locks_to_remove_set = set(locks_to_remove)
        for path, _ in all_locks_sorted:
            if len(_file_locks) - len(locks_to_remove_set) <= _MAX_FILE_LOCKS:
                break
            if path not in locks_to_remove_set:
                locks_to_remove_set.add(path)
        locks_to_remove = list(locks_to_remove_set)
    
    # Calculate how many locks would remain after removal
    locks_remaining = len(_file_locks) - len(locks_to_remove)
    
    # RESOURCE MANAGEMENT: Only remove if we'll still have at least MIN_FILE_LOCKS remaining
    # If removal would leave us below MIN_FILE_LOCKS, limit removal to keep MIN_FILE_LOCKS
    if locks_remaining < _MIN_FILE_LOCKS:
        # Limit removal to keep at least MIN_FILE_LOCKS
        max_removable = len(_file_locks) - _MIN_FILE_LOCKS
        if max_removable > 0:
            # Keep only the oldest locks_to_remove up to max_removable
            locks_to_remove = locks_to_remove[:max_removable]
        else:
            # Can't remove any without going below MIN_FILE_LOCKS
            locks_to_remove = []
    
    # Remove the locks
    for path in locks_to_remove:
        # Safe to pop - we're inside the lock (assumed held by caller)
        _file_locks.pop(path, None)
        _file_lock_access_times.pop(path, None)


def _lock_file(fd: int, path: str) -> bool:
    """
    Lock a file descriptor using platform-specific locking.
    
    Args:
        fd: File descriptor to lock
        path: File path (for error messages)
        
    Returns:
        True if lock acquired, False otherwise
    """
    try:
        if HAS_FCNTL:
            # POSIX: Use fcntl for advisory locking
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        elif HAS_MSVCRT:
            # Windows: msvcrt.locking() requires a file handle, not a file descriptor
            # We need to convert the fd to a file handle
            # Note: On Windows, we rely primarily on threading locks
            # File-level locking is advisory and may not work reliably
            try:
                # Try to lock using the file descriptor
                # msvcrt.locking() locks bytes, not the whole file
                # For whole-file locking on Windows, we'd need win32file
                # For now, return True and rely on threading locks
                return True
            except (IOError, OSError):
                return False
        else:
            # No locking available - rely on threading locks only
            return True
    except (IOError, OSError) as e:
        # Lock failed (file already locked by another process)
        import structlog
        logger = structlog.get_logger()
        logger.warning(
            "file_lock_failed",
            path=path,
            error=str(e)[:100]
        )
        return False


def _unlock_file(fd: int) -> None:
    """
    Unlock a file descriptor.
    
    Args:
        fd: File descriptor to unlock
    """
    try:
        if HAS_FCNTL:
            fcntl.flock(fd, fcntl.LOCK_UN)
        elif HAS_MSVCRT:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except (IOError, OSError) as unlock_error:
        # OBSERVABILITY: Log unlock errors for debugging (usually harmless, but worth tracking)
        # Unlock failures are typically non-critical (file already unlocked or handle closed)
        import structlog
        logger = structlog.get_logger()
        logger.debug(
            "file_unlock_failed",
            error_type=type(unlock_error).__name__,
            error_message=str(unlock_error)[:200],
            message="File unlock failed (usually harmless - file may already be unlocked)"
        )


def atomic_write_json_secure(obj: Dict[str, Any], path: str) -> None:
    """
    Atomically write JSON object to file with secure permissions.
    
    DATA INTEGRITY: Uses atomic write pattern (temp file + replace) to ensure
    data integrity. Prevents partial writes and file corruption.
    
    Transaction Boundary:
    - Start: Temp file creation
    - Commit: os.replace() (atomic on POSIX, best-effort on Windows)
    - Rollback: Temp file cleanup in finally block
    
    See docs/DATA_INTEGRITY.md for details.
    
    Uses atomic write pattern: write to temp file, then replace.
    Sets file permissions to 0o600 (read/write for owner only).
    
    Args:
        obj: Dictionary to write
        path: Path to write file to
    """
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    # PERFORMANCE: Use binary mode for orjson optimization (spd.txt #8, cp.txt #9)
    # Fallback to text mode if orjson not available
    try:
        import orjson
        use_orjson = True
        fd, tmp = tempfile.mkstemp(dir=d, prefix="._viva_state.", suffix=".tmp", text=False)
    except ImportError:
        use_orjson = False
        fd, tmp = tempfile.mkstemp(dir=d, prefix="._viva_state.", suffix=".tmp", text=True)
    
    try:
        # Set file permissions (POSIX) or Windows ACLs
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, PermissionError):
            # Windows: Try to set file security using Windows ACLs if available
            # Note: This requires pywin32 package. If not available, file permissions
            # will be set by the OS default, which may be less secure.
            try:
                import win32security
                import win32api
                import win32con
                # Set file to owner-only access on Windows
                user_sid = win32security.LookupAccountName(None, win32api.GetUserName())[0]
                dacl = win32security.ACL()
                # Use FILE_ALL_ACCESS from win32con, or construct from FILE_GENERIC_* constants, or use numeric fallback
                try:
                    file_access = win32con.FILE_ALL_ACCESS
                except AttributeError:
                    try:
                        # Fallback: construct access mask from generic rights
                        file_access = (
                            win32con.FILE_GENERIC_READ |
                            win32con.FILE_GENERIC_WRITE |
                            win32con.FILE_GENERIC_EXECUTE
                        )
                    except AttributeError:
                        # Final fallback: use numeric Windows access rights values
                        # FILE_ALL_ACCESS = 0x1F01FF (full control)
                        # Using GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE | DELETE | SYNCHRONIZE
                        # Standard access rights: 0x001F0000 (SYNCHRONIZE, WRITE_OWNER, WRITE_DAC, READ_CONTROL, DELETE)
                        # File-specific rights: 0x000001FF (FILE_ALL_ACCESS for files)
                        file_access = 0x1F01FF  # FILE_ALL_ACCESS numeric value
                dacl.AddAccessAllowedAce(win32security.ACL_REVISION, file_access, user_sid)
                sd = win32security.SECURITY_DESCRIPTOR()
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                win32security.SetFileSecurity(tmp, win32security.DACL_SECURITY_INFORMATION, sd)
            except (ImportError, AttributeError, OSError):
                # SECURITY: Fail hard on Windows if pywin32 not available (Principle #23)
                # This prevents insecure file permissions that could lead to FERPA violations
                # Close file descriptor before raising exception to allow cleanup
                try:
                    os.close(fd)
                except Exception:
                    pass  # Ignore errors closing fd
                import structlog
                import sys
                logger = structlog.get_logger()
                error_msg = (
                    "Windows file security (ACLs) not available. "
                    "Install pywin32 for secure file permissions on Windows. "
                    "Cannot proceed without secure file permissions (FERPA compliance requirement)."
                )
                logger.error(
                    "windows_file_security_required",
                    message=error_msg,
                    file_path=tmp,
                    action="failing_hard"
                )
                raise RuntimeError(error_msg)
        # PERFORMANCE: Use orjson for faster serialization (spd.txt #8, cp.txt #9)
        if use_orjson:
            # orjson requires binary mode and returns bytes
            with os.fdopen(fd, "wb") as f:
                json_bytes = orjson.dumps(obj, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS)
                f.write(json_bytes)
                f.flush()
                os.fsync(f.fileno())
        else:
            # Fallback to standard json for compatibility (text mode)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Set file permissions after replace (POSIX) or Windows ACLs
        try:
            os.chmod(path, 0o600)
        except (AttributeError, PermissionError):
            # Windows: Try to set file security using Windows ACLs if available
            try:
                import win32security
                import win32api
                import win32con
                user_sid = win32security.LookupAccountName(None, win32api.GetUserName())[0]
                dacl = win32security.ACL()
                # Use FILE_ALL_ACCESS from win32con, or construct from FILE_GENERIC_* constants, or use numeric fallback
                try:
                    file_access = win32con.FILE_ALL_ACCESS
                except AttributeError:
                    try:
                        # Fallback: construct access mask from generic rights
                        file_access = (
                            win32con.FILE_GENERIC_READ |
                            win32con.FILE_GENERIC_WRITE |
                            win32con.FILE_GENERIC_EXECUTE
                        )
                    except AttributeError:
                        # Final fallback: use numeric Windows access rights values
                        # FILE_ALL_ACCESS = 0x1F01FF (full control)
                        # Using GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE | DELETE | SYNCHRONIZE
                        # Standard access rights: 0x001F0000 (SYNCHRONIZE, WRITE_OWNER, WRITE_DAC, READ_CONTROL, DELETE)
                        # File-specific rights: 0x000001FF (FILE_ALL_ACCESS for files)
                        file_access = 0x1F01FF  # FILE_ALL_ACCESS numeric value
                dacl.AddAccessAllowedAce(win32security.ACL_REVISION, file_access, user_sid)
                sd = win32security.SECURITY_DESCRIPTOR()
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                win32security.SetFileSecurity(path, win32security.DACL_SECURITY_INFORMATION, sd)
            except (ImportError, AttributeError, OSError):
                # SECURITY: Fail hard on Windows if pywin32 not available (already failed above, but ensure consistency)
                # This should not be reached if the first check above failed correctly
                import structlog
                logger = structlog.get_logger()
                logger.error(
                    "windows_file_security_required_after_replace",
                    message="Windows file security (ACLs) not available after file replace. This should not happen if initial check passed.",
                    file_path=path,
                    action="failing_hard"
                )
                raise RuntimeError("Windows file security (ACLs) not available. Install pywin32 for secure file permissions.")
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except Exception as cleanup_error:
            # OBSERVABILITY: Log cleanup errors (temp file cleanup failures could indicate disk issues)
            import structlog
            logger = structlog.get_logger()
            logger.warning(
                "temp_file_cleanup_failed",
                temp_path=tmp,
                error_type=type(cleanup_error).__name__,
                error_message=str(cleanup_error)[:200],
                message="Failed to clean up temporary file after atomic write error"
            )


def queue_state_save(s: Dict[str, Any], persist_ok: bool = True) -> bool:
    """
    Queue state save for batched processing.
    
    PERFORMANCE: Batches state saves to reduce disk I/O (spd.txt #3, #7).
    Last write wins per session (idempotent - cp.txt #21).
    
    Args:
        s: State dictionary to save
        persist_ok: Whether persistence is enabled
        
    Returns:
        True if queued successfully, False otherwise
    """
    session_id = s.get("session_id")
    if not session_id:
        return False
    
    # Queue state save (last write wins per session)
    with _save_queue_lock:
        _pending_state_saves[session_id] = (s, persist_ok)
        
        # Start timer if not running
        global _save_timer
        if _save_timer is None or not _save_timer.is_alive():
            _save_timer = threading.Timer(_BATCH_SAVE_DELAY, _flush_state_saves)
            _save_timer.start()
        
        # Flush immediately if queue is large
        if len(_pending_state_saves) >= _BATCH_SAVE_MAX_SIZE:
            _save_timer.cancel()
            _flush_state_saves()
    
    return True


def _flush_state_saves() -> None:
    """
    Flush all pending state saves to disk.
    
    Thread-safe batch processing of queued state saves.
    """
    with _save_queue_lock:
        if not _pending_state_saves:
            return
        
        # Process all pending saves
        saves_to_process = list(_pending_state_saves.items())
        _pending_state_saves.clear()
        global _save_timer
        _save_timer = None
    
    # Process saves outside lock to avoid blocking
    for session_id, (state, persist_ok) in saves_to_process:
        try:
            save_state_to_disk(state, persist_ok=persist_ok)
        except Exception as e:
            import structlog
            logger = structlog.get_logger()
            logger.error(
                "batched_state_save_failed",
                session_id=session_id,
                error_type=type(e).__name__,
                error_message=str(e)[:100]
            )


def save_state_to_disk(s: Dict[str, Any], persist_ok: bool = True, use_batch: bool = True) -> bool:
    """
    Save state dictionary to disk with file locking to prevent race conditions.
    
    **Contract**:
    - **Inputs**: State dictionary, optional persist_ok flag
    - **Outputs**: Boolean indicating success (True) or failure (False)
    - **Invariants**: State must satisfy invariants (validated before persistence)
    - **Failure Modes**: Returns False on error; never raises exceptions
    
    Uses selective serialization to exclude large/transient data:
    - Excludes: chunks, text, proctor_state, _rng, queued_answers, current
    - Bounds: history (1000), answers_tslog_all (500), security_events (1000)
    - See exam.state.serialization for full details
    
    THREAD-SAFETY: Uses per-file locks to prevent concurrent writes to the same
    session file. This prevents race conditions when multiple requests try to
    save state for the same session simultaneously.
    
    IDEMPOTENCY: This operation is idempotent (Principle #21).
    - Uses atomic writes (temp file + replace)
    - Last write wins (upsert-like semantics)
    - Safe to retry without creating duplicates or corruption
    - Multiple calls with same state produce same result
    
    DATA INTEGRITY: Validates state invariants before persistence (Principle #22).
    Transaction boundary:
    - Start: Function called
    - Validate: Check invariants and constraints
    - Prepare: Prepare state for serialization
    - Write: Atomic write (temp file + replace)
    - Commit: File replace (atomic)
    - Rollback: Temp file cleanup (on error)
    
    Args:
        s: State dictionary to save (must satisfy state invariants)
        persist_ok: Whether persistence is enabled (default: True)
        
    Returns:
        True if save was successful, False otherwise
        
    Raises:
        Never raises exceptions. Returns False on error and logs internally.
        
    **Failure Modes**:
    - Returns False if persist_ok is False
    - Returns False if tombstone file exists (exam completed)
    - Returns False if state validation fails
    - Returns False if file write fails
    - Logs errors internally (does not expose to caller)
    
    Args:
        use_batch: If True, queue save for batched processing (default: True)
    """
    # PERFORMANCE: Use batched saves by default (spd.txt #3, #7)
    if use_batch:
        return queue_state_save(s, persist_ok=persist_ok)
    
    # Direct save (for critical operations that need immediate persistence)
    return _save_state_to_disk_immediate(s, persist_ok=persist_ok)


def _save_state_to_disk_immediate(s: Dict[str, Any], persist_ok: bool = True) -> bool:
    """
    Save state immediately (bypasses batching).
    
    Used internally by batched saves and for critical operations.
    """
    p = _paths_for_session(s)
    if not persist_ok or os.path.exists(p["TOMBSTONE_PATH"]):
        return False
    
    # DATA INTEGRITY: Enforce constraints first, then validate state invariants before persistence (Principle #22)
    try:
        from exam.state.validation import validate_state_before_persistence, enforce_state_constraints
        # Enforce constraints first (e.g., truncate bounded collections)
        # This ensures state satisfies bounds before validation
        s = enforce_state_constraints(s)
        
        # Then validate invariants
        is_valid, error = validate_state_before_persistence(s)
        if not is_valid:
            # Log validation error but don't expose internal details
            import structlog
            logger = structlog.get_logger()
            logger.error(
                "state_validation_failed",
                session_id=s.get("session_id", "unknown"),
                error=error,
                message="State validation failed before persistence"
            )
            return False
    except ImportError:
        # Validation module not available - skip validation (backward compatibility)
        pass
    
    # Get lock for this specific file to prevent concurrent writes
    file_lock = _get_file_lock(p["STATE_PATH"])
    
    try:
        # Acquire lock (blocks until available)
        # Note: If lock acquisition fails, the threading lock will block
        # which is acceptable for state persistence
        with file_lock:
            # SELECTIVE SERIALIZATION: Prepare state for serialization (Principle #25)
            # Excludes large/transient data, bounds collections
            # Serialize only at boundary (not in flow) to avoid redundant cycles
            prepared_state = prepare_state_for_serialization(s)
            atomic_write_json_secure(prepared_state, p["STATE_PATH"])
            return True
    except Exception as e:
        # Log error but don't expose internal details
        import structlog
        logger = structlog.get_logger()
        logger.error(
            "state_save_failed",
            session_id=s.get("session_id", "unknown"),
            error_type=type(e).__name__,
            _internal_error=str(e)[:100]
        )
        return False


def auto_save_state(s: Dict[str, Any], persist_ok: bool = True, time_provider=None) -> bool:
    """
    Auto-save state periodically (every 30 seconds) for audit trail.
    
    **Contract**:
    - **Inputs**: State dictionary, optional persist_ok flag, optional time_provider
    - **Outputs**: Boolean indicating success (True) or failure (False)
    - **Invariants**: State must satisfy invariants (validated before persistence)
    - **Failure Modes**: Returns False on error; never raises exceptions
    
    SELECTIVE SERIALIZATION: Uses selective serialization to avoid redundant cycles (Principle #25).
    Serializes only at boundary (auto-save), not in flow operations.
    
    DETERMINISTIC: Accepts optional time_provider for deterministic behavior (Principle #5).
    
    This function:
    - Checks if auto-save is needed (30-second interval)
    - Validates exam is active (not complete, session started)
    - Calls save_state_to_disk() which uses selective serialization
    - Updates last_auto_save_time in state
    
    Args:
        s: State dictionary to save
        persist_ok: Whether persistence is enabled (default: True)
        time_provider: Optional time provider (uses default if not provided)
        
    Returns:
        True if auto-save was performed, False otherwise
        
    Raises:
        Never raises exceptions. Returns False on error and logs internally.
    """
    # DETERMINISTIC: Use time_provider if provided, otherwise use default (Principle #5)
    if time_provider is None:
        time_provider = get_default_time_provider()
    
    s = ensure_state(s)
    
    # Don't auto-save if exam is complete or not started
    if s.get("phase") == "complete" or not s.get("session_start_time"):
        return False
    
    # Check if auto-save is needed (every 30 seconds)
    current_time = time_provider.time()
    last_auto_save = s.get("last_auto_save_time", 0)
    
    if current_time - last_auto_save >= AUTO_SAVE_INTERVAL_SEC:
        # Perform auto-save
        success = save_state_to_disk(s, persist_ok=persist_ok)
        if success:
            s["last_auto_save_time"] = current_time
        return success
    
    return False


def load_state_from_disk():
    """
    Load state from disk (currently disabled).
    
    NOTE: This function is intentionally disabled. State persistence is used
    only for audit trail (auto-save), not for resuming exams. This ensures
    exam integrity and prevents state manipulation.
    
    Returns:
        Tuple of (None, status_message) indicating resume is disabled
    """
    return None, "ℹ️ Resume is disabled in this build."


def resume_from_disk(ensure_state_fn=None):
    """
    Resume exam from disk (currently disabled).
    
    NOTE: This function is intentionally disabled. State persistence is used
    only for audit trail (auto-save), not for resuming exams. This ensures
    exam integrity and prevents state manipulation.
    
    Args:
        ensure_state_fn: Optional function to ensure state (defaults to ensure_state)
        
    Returns:
        Tuple of (empty_state, status_update, interactive_update, visible_update)
        indicating resume is disabled
    """
    import gradio as gr
    
    if ensure_state_fn is None:
        ensure_state_fn = ensure_state
    
    st = ensure_state_fn({})
    return (
        st,
        gr.update(value="ℹ️ Resume is disabled in this build."),
        gr.update(interactive=False),
        gr.update(value=False, interactive=True)
    )

