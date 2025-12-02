"""
Idempotency and request ID management.

This module provides utilities for making operations idempotent and tracking
request IDs for deduplication and correlation.

IDEMPOTENCY: Operations can be safely retried without creating duplicates (Principle #21).
All request IDs are injected via dependency injection to preserve wiring.

**Key Features**:
- `IdempotencyTracker`: Thread-safe tracker for processed operations
- `generate_idempotency_key()`: Generate stable keys for operations
- `make_idempotent()`: Decorator to make functions idempotent
- Request ID generation and tracking

**Usage Example**:
    ```python
    from shared.idempotency import make_idempotent, IdempotencyTracker
    
    tracker = IdempotencyTracker()
    
    @make_idempotent(idempotency_tracker=tracker)
    def my_operation(s: Dict[str, Any], ...):
        # Operation logic
        return result
    ```

**Idempotency Keys**:
- Format: `{operation}:{session_id}:{hash}`
- Includes: operation name, session_id, operation parameters
- Stable: Same inputs → same key (supports safe retries)

**Request IDs**:
- Generated automatically in `ensure_state()`
- UUID-based (unique per request)
- Used for correlation and deduplication
"""

import uuid
from typing import Dict, Any, Optional, Set, Callable
from datetime import datetime, timezone
from threading import Lock


class IdempotencyTracker:
    """
    Tracks idempotency keys and request IDs to prevent duplicate operations.
    
    THREAD-SAFETY: Thread-safe implementation using locks.
    All operations are safe for concurrent access from multiple threads.
    See docs/CONCURRENCY_THREAD_SAFETY.md for details.
    """
    
    def __init__(self, max_entries: int = 10000):
        """
        Initialize idempotency tracker.
        
        Args:
            max_entries: Maximum number of tracked entries before cleanup
        """
        self._lock = Lock()
        self._processed_keys: Set[str] = set()
        self._request_ids: Dict[str, Dict[str, Any]] = {}
        self._max_entries = max_entries
    
    def generate_request_id(self) -> str:
        """
        Generate a new unique request ID.
        
        Returns:
            UUID string
        """
        return str(uuid.uuid4())
    
    def is_processed(self, idempotency_key: str) -> bool:
        """
        Check if an operation with this idempotency key has been processed.
        
        **Contract**:
        - **Inputs**: Idempotency key string
        - **Outputs**: Boolean indicating if operation was processed
        - **Invariants**: Thread-safe check (atomic operation)
        - **Failure Modes**: Returns False if key not found (safe default)
        
        **Idempotency** (Principle #21):
        - Enables safe retries without duplicate operations
        - Prevents duplicate processing of the same request
        - Thread-safe implementation for concurrent access
        
        Args:
            idempotency_key: Unique key for the operation (must be consistent for same operation)
            
        Returns:
            True if operation was already processed, False otherwise
            
        Example:
            ```python
            key = generate_idempotency_key("create_order", state, order_data)
            if tracker.is_processed(key):
                return cached_result  # Already processed
            # Process operation...
            tracker.mark_processed(key, request_id)
            ```
        """
        with self._lock:
            return idempotency_key in self._processed_keys
    
    def mark_processed(self, idempotency_key: str, request_id: Optional[str] = None) -> None:
        """
        Mark an operation as processed.
        
        Args:
            idempotency_key: Unique key for the operation
            request_id: Optional request ID to associate
        """
        with self._lock:
            self._processed_keys.add(idempotency_key)
            
            if request_id:
                self._request_ids[request_id] = {
                    "idempotency_key": idempotency_key,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }
            
            # Cleanup if too many entries
            if len(self._processed_keys) > self._max_entries:
                self._cleanup_old_entries()
    
    def get_request_info(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a request ID.
        
        Args:
            request_id: Request ID to look up
            
        Returns:
            Dictionary with request info or None if not found
        """
        with self._lock:
            return self._request_ids.get(request_id)
    
    def _cleanup_old_entries(self, keep_ratio: float = 0.5) -> None:
        """
        Clean up old entries to prevent memory growth.
        
        Args:
            keep_ratio: Ratio of entries to keep (default: 0.5 = keep 50%)
        """
        # Remove oldest 50% of entries
        # Simple implementation: clear half the set
        entries_list = list(self._processed_keys)
        entries_to_remove = entries_list[:len(entries_list) // 2]
        
        for key in entries_to_remove:
            self._processed_keys.discard(key)
        
        # Also cleanup request IDs
        request_ids_list = list(self._request_ids.keys())
        ids_to_remove = request_ids_list[:len(request_ids_list) // 2]
        
        for req_id in ids_to_remove:
            self._request_ids.pop(req_id, None)
    
    def reset(self) -> None:
        """Reset tracker (mainly for testing)."""
        with self._lock:
            self._processed_keys.clear()
            self._request_ids.clear()


# Global idempotency tracker instance
# SCALABILITY NOTE: This is a per-instance default. For distributed idempotency tracking,
# inject a database-backed IdempotencyTracker via dependency injection.
# See docs/SCALABILITY_ARCHITECTURE.md for details.
_default_tracker: Optional[IdempotencyTracker] = None


def get_default_idempotency_tracker() -> IdempotencyTracker:
    """
    Get or create default idempotency tracker instance.
    
    SCALABILITY: This returns a per-instance tracker. For horizontal scaling
    with shared idempotency tracking across instances, inject a distributed tracker
    (e.g., database-backed) via dependency injection.
    
    Returns:
        IdempotencyTracker instance
    """
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = IdempotencyTracker()
    return _default_tracker


def create_idempotency_tracker(max_entries: int = 10000) -> IdempotencyTracker:
    """
    Create a new idempotency tracker instance.
    
    Args:
        max_entries: Maximum number of tracked entries
        
    Returns:
        New IdempotencyTracker instance
    """
    return IdempotencyTracker(max_entries)


def generate_idempotency_key(
    operation: str,
    state: Dict[str, Any],
    *args,
    **kwargs
) -> str:
    """
    Generate an idempotency key for an operation.
    
    IDEMPOTENCY: Creates stable keys that support safe retries (Principle #21).
    Same inputs always produce the same key, allowing duplicate detection.
    
    Key Format: `{operation}:{session_id}:{hash}`
    - operation: Operation name (e.g., "ask_main_question")
    - session_id: Session identifier (from state)
    - hash: SHA256 hash of operation parameters
    
    Args:
        operation: Operation name (e.g., "ask_main_question")
        state: State dictionary (must have session_id and optionally request_id)
        *args: Additional arguments to include in key
        **kwargs: Additional keyword arguments to include in key
        
    Returns:
        Unique idempotency key string
        
    Example:
        ```python
        key = generate_idempotency_key(
            "ask_main_question",
            {"session_id": "abc123", "request_id": "req456"},
            ctx_text="Some context"
        )
        # Returns: "ask_main_question:abc123:a1b2c3d4e5f6..."
        ```
    """
    import hashlib
    import json
    
    # Build key components
    # IDEMPOTENCY: Use request_id if available for better deduplication (Principle #21)
    # If request_id exists, use it; otherwise use session_id + operation params
    session_id = state.get("session_id", "unknown")
    request_id = state.get("request_id")
    
    key_parts = [
        operation,
        session_id,
        str(args),
        json.dumps(kwargs, sort_keys=True, default=str)
    ]
    
    # Include request_id in key if available (better deduplication)
    if request_id:
        key_parts.insert(1, request_id)  # Insert after operation, before session_id
    
    # Create hash
    key_string = "|".join(key_parts)
    key_hash = hashlib.sha256(key_string.encode()).hexdigest()
    
    # IDEMPOTENCY: Stable key format supports safe retries (Principle #21)
    # Format: operation:session_id:hash or operation:request_id:session_id:hash
    if request_id:
        return f"{operation}:{request_id}:{key_hash[:16]}"
    else:
        return f"{operation}:{session_id}:{key_hash[:16]}"


def make_idempotent(
    func: Callable,
    idempotency_tracker: Optional[IdempotencyTracker] = None,
    key_generator: Optional[Callable] = None
) -> Callable:
    """
    Decorator to make a function idempotent.
    
    IDEMPOTENCY: Prevents duplicate execution of operations (Principle #21).
    If an operation with the same idempotency key has already been processed,
    returns None (or cached result) instead of executing again.
    
    This enables safe retries without creating duplicates or corruption.
    
    Args:
        func: Function to make idempotent
        idempotency_tracker: IdempotencyTracker instance (defaults to global)
        key_generator: Function to generate idempotency key (defaults to generate_idempotency_key)
        
    Returns:
        Wrapped function that checks idempotency before execution
        
    Example:
        ```python
        @make_idempotent(idempotency_tracker=tracker)
        def ask_main_question(s: Dict[str, Any], ...):
            # This will only execute once per idempotency key
            # Retries return None if already processed
            return result
        ```
        
    Note: Currently returns None for duplicate requests. Future enhancement:
    could return cached result if operation result is stored.
    """
    if idempotency_tracker is None:
        idempotency_tracker = get_default_idempotency_tracker()
    
    if key_generator is None:
        key_generator = generate_idempotency_key
    
    def wrapper(*args, **kwargs):
        # Extract state (first arg is typically state dict)
        state = args[0] if args and isinstance(args[0], dict) else {}
        
        # Generate idempotency key
        operation = func.__name__
        idempotency_key = key_generator(operation, state, *args[1:], **kwargs)
        
        # Check if already processed
        if idempotency_tracker.is_processed(idempotency_key):
            # Return cached result or indicate already processed
            return None  # Or could return cached result
        
        # Execute function
        result = func(*args, **kwargs)
        
        # Mark as processed
        request_id = state.get("request_id")
        idempotency_tracker.mark_processed(idempotency_key, request_id)
        
        return result
    
    return wrapper

