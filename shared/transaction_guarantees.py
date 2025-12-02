"""
Transaction-like guarantees for critical operations.

This module provides transaction-like guarantees for critical write operations,
ensuring atomicity, consistency, and recoverability.

DATA INTEGRITY: Critical writes must be atomic, consistent, and recoverable (Principle #22).
Clearly define transaction boundaries across services and databases.

**Key Functions**:
- `atomic_operation()`: Execute operation with transaction-like guarantees
- `with_transaction()`: Context manager for transaction-like operations
- `rollback_on_error()`: Rollback operation on error

**Usage Example**:
    ```python
    from shared.transaction_guarantees import atomic_operation
    
    def save_exam_results(state, results):
        def operation():
            # Critical write operations
            save_state_to_disk(state)
            save_results_to_file(results)
            return True
        
        def rollback():
            # Rollback operations
            remove_state_file(state)
            remove_results_file(results)
        
        return atomic_operation(operation, rollback)
    ```
"""

import os
from typing import Callable, Optional, Any, Dict
from contextlib import contextmanager
import tempfile
import shutil


@contextmanager
def with_transaction(
    operation: Callable[[], Any],
    rollback: Optional[Callable[[], None]] = None,
    cleanup: Optional[Callable[[], None]] = None
):
    """
    Context manager for transaction-like operations.
    
    DATA INTEGRITY: Ensures atomicity and recoverability (Principle #22).
    
    Args:
        operation: Operation to execute
        rollback: Optional rollback function if operation fails
        cleanup: Optional cleanup function (always called)
        
    Yields:
        Result of operation
        
    Example:
        ```python
        with with_transaction(
            lambda: save_state_to_disk(state),
            rollback=lambda: remove_state_file(state)
        ) as result:
            # Operation succeeded
            pass
        ```
    """
    result = None
    error = None
    
    try:
        result = operation()
        yield result
    except Exception as e:
        error = e
        if rollback:
            try:
                rollback()
            except Exception as rollback_error:
                # OBSERVABILITY: Log rollback errors for debugging (Principle #13)
                # Rollback failures are logged but don't fail the transaction
                import structlog
                logger = structlog.get_logger()
                logger.warning(
                    "rollback_failed",
                    error_type=type(rollback_error).__name__,
                    error_message=str(rollback_error)[:200],
                    message="Rollback operation failed (non-critical)"
                )
        raise
    finally:
        if cleanup:
            try:
                cleanup()
            except Exception as cleanup_error:
                # OBSERVABILITY: Log cleanup errors for debugging (Principle #13)
                # Cleanup failures are logged but don't fail the transaction
                import structlog
                logger = structlog.get_logger()
                logger.warning(
                    "cleanup_failed",
                    error_type=type(cleanup_error).__name__,
                    error_message=str(cleanup_error)[:200],
                    message="Cleanup operation failed (non-critical)"
                )


def atomic_operation(
    operation: Callable[[], Any],
    rollback: Optional[Callable[[], None]] = None
) -> Any:
    """
    Execute an operation with transaction-like guarantees.
    
    DATA INTEGRITY: Ensures atomicity and recoverability (Principle #22).
    If operation fails, rollback is called to restore previous state.
    
    Args:
        operation: Operation to execute
        rollback: Optional rollback function if operation fails
        
    Returns:
        Result of operation
        
    Raises:
        Exception: If operation fails (after rollback if provided)
    """
    try:
        return operation()
    except Exception as e:
        if rollback:
            try:
                rollback()
            except Exception as rollback_error:
                # OBSERVABILITY: Log rollback errors for debugging (Principle #13)
                # Rollback failures are logged but don't fail the transaction
                import structlog
                logger = structlog.get_logger()
                logger.warning(
                    "rollback_failed",
                    error_type=type(rollback_error).__name__,
                    error_message=str(rollback_error)[:200],
                    message="Rollback operation failed (non-critical)"
                )
        raise


def atomic_file_write(
    file_path: str,
    content: str,
    backup: bool = True
) -> None:
    """
    Atomically write content to file with backup support.
    
    DATA INTEGRITY: Ensures atomic writes with backup for recovery (Principle #22).
    
    Args:
        file_path: Path to file
        content: Content to write
        backup: Whether to create backup before write
        
    Raises:
        IOError: If write fails
    """
    backup_path = None
    
    try:
        # Create backup if requested
        if backup and os.path.exists(file_path):
            backup_path = file_path + ".backup"
            shutil.copy2(file_path, backup_path)
        
        # Write to temp file first
        temp_path = file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomically replace
        os.replace(temp_path, file_path)
        
    except Exception as e:
        # Restore backup if write failed
        if backup_path and os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, file_path)
            except Exception:
                pass
        raise


def verify_operation_integrity(
    operation: Callable[[], Any],
    verification: Callable[[Any], bool],
    rollback: Optional[Callable[[], None]] = None
) -> Any:
    """
    Execute operation and verify integrity of result.
    
    DATA INTEGRITY: Verifies operation integrity before committing (Principle #22).
    
    Args:
        operation: Operation to execute
        verification: Function to verify operation result
        rollback: Optional rollback function if verification fails
        
    Returns:
        Result of operation
        
    Raises:
        ValueError: If verification fails
    """
    result = operation()
    
    if not verification(result):
        if rollback:
            try:
                rollback()
            except Exception as rollback_error:
                # OBSERVABILITY: Log rollback errors for debugging (Principle #13)
                import structlog
                logger = structlog.get_logger()
                logger.warning(
                    "rollback_failed",
                    error_type=type(rollback_error).__name__,
                    error_message=str(rollback_error)[:200],
                    message="Rollback operation failed during integrity verification (non-critical)"
                )
        raise ValueError("Operation integrity verification failed")
    
    return result


__all__ = [
    "with_transaction",
    "atomic_operation",
    "atomic_file_write",
    "verify_operation_integrity",
]

