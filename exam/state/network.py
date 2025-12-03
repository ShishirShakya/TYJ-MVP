"""
Network status and offline queue management for exam.ipynb.

This module contains functions for:
- Network status checking
- Offline answer queuing
- Queue processing when connection is restored
"""

import time
import socket
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple

from .core import ensure_state
from .persistence import save_state_to_disk
from shared.time_provider import get_default_time_provider


# Constants
NETWORK_CHECK_INTERVAL_SEC = 15  # Check network every 15 seconds (reduced frequency to reduce false positives)
NETWORK_CHECK_TIMEOUT_SEC = 5  # Socket timeout in seconds (increased from 3 to reduce false positives)

# PORTABILITY: Configurable network check endpoints with defaults (Principle #6)
# Can be overridden via environment variable for restricted networks
DEFAULT_NETWORK_CHECK_ENDPOINTS = [
    ("8.8.8.8", 53),  # Google DNS
    ("www.google.com", 80),  # Google website
    ("1.1.1.1", 53),  # Cloudflare DNS (fallback)
]


def check_network_status(endpoints: Optional[list] = None) -> bool:
    """
    Check if network is available.
    
    PORTABILITY: Uses configurable endpoints with sensible defaults (Principle #6).
    Can be customized via environment variable for restricted networks.
    
    Args:
        endpoints: Optional list of (host, port) tuples to check.
                   If None, uses DEFAULT_NETWORK_CHECK_ENDPOINTS.
    
    Returns:
        True if network is available, False otherwise
    """
    import os
    from typing import List, Tuple
    
    # Get endpoints from environment if available, otherwise use defaults
    if endpoints is None:
        endpoints = DEFAULT_NETWORK_CHECK_ENDPOINTS
        
        # Allow override via environment variable (comma-separated "host:port" pairs)
        env_endpoints = os.getenv("NETWORK_CHECK_ENDPOINTS")
        if env_endpoints:
            try:
                endpoints = []
                for endpoint_str in env_endpoints.split(","):
                    host, port = endpoint_str.strip().split(":")
                    endpoints.append((host, int(port)))
            except (ValueError, AttributeError):
                # Invalid format, use defaults
                pass
    
    # Try each endpoint in order
    for host, port in endpoints:
        try:
            socket.create_connection((host, port), timeout=NETWORK_CHECK_TIMEOUT_SEC)
            return True
        except (socket.error, OSError):
            continue
    
    return False


def update_network_status(s: Dict[str, Any]) -> str:
    """
    Update network status in state and return current status.
    
    Checks network status periodically and updates state accordingly.
    If connection is restored, marks queued answers as ready to process.
    
    Args:
        s: State dictionary
        
    Returns:
        Current network status: "online", "offline", or "checking"
    """
    s = ensure_state(s)
    # DETERMINISTIC: Use time_provider instead of direct time.time() (Principle #5)
    time_provider = get_default_time_provider()
    current_time = time_provider.time()
    last_check = s.get("last_network_check", 0)
    check_interval = s.get("network_check_interval", NETWORK_CHECK_INTERVAL_SEC)
    
    # Check network status periodically
    if current_time - last_check >= check_interval:
        s["network_status"] = "checking"
        s["last_network_check"] = current_time
        
        is_online = check_network_status()
        s["network_status"] = "online" if is_online else "offline"
        
        # If connection restored, try to process queued answers
        if is_online and s.get("queued_answers"):
            # Connection restored - answers will be processed on next interaction
            pass
    
    return s.get("network_status", "online")


def queue_answer_locally(
    s: Dict[str, Any],
    answer_text: str,
    answer_audio_path: Optional[str] = None,
    persist_ok: bool = True,
    question_number: Optional[int] = None,
    priority: int = 0
) -> None:
    """
    Queue answer locally when offline.
    
    Phase 2.2.3: Enhanced with priority queue support.
    
    Args:
        s: State dictionary
        answer_text: Answer text to queue
        answer_audio_path: Optional path to answer audio file
        persist_ok: Whether persistence is enabled (default: True)
        question_number: Optional question number for priority sorting
        priority: Priority level (higher = processed first, default: 0)
    """
    s = ensure_state(s)
    queued_answers = s.get("queued_answers", [])
    
    # DETERMINISTIC: Use time_provider instead of direct time calls (Principle #5)
    time_provider = get_default_time_provider()
    current_time = time_provider.time()
    
    # Phase 2.2.3: Add priority and question number for sorting
    queued_answer = {
        "text": answer_text,
        "audio_path": answer_audio_path,
        "timestamp": current_time,
        "ts_iso": time_provider.utcnow().isoformat(timespec="seconds") + "Z",
        "question_number": question_number or s.get("asked_main", 0),
        "priority": priority
    }
    
    queued_answers.append(queued_answer)
    
    # Phase 2.2.3: Sort by priority (descending), then timestamp (ascending)
    # Higher priority answers processed first, then oldest first within same priority
    queued_answers.sort(key=lambda x: (-x.get("priority", 0), x.get("timestamp", 0)))
    
    s["queued_answers"] = queued_answers
    save_state_to_disk(s, persist_ok=persist_ok)  # Save queued answers to disk


def process_queued_answers(
    s: Dict[str, Any],
    clear_after_processing: bool = True,
    batch_size: Optional[int] = None
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Process queued answers when connection is restored.
    
    Phase 2.2.3: Enhanced with batch processing support.
    
    Args:
        s: State dictionary
        clear_after_processing: Whether to clear queued answers after processing (default: True)
        batch_size: Optional batch size (process N answers at a time, None = all)
        
    Returns:
        Tuple of (processed_count, queued_answers_list)
        - processed_count: Number of queued answers ready to process
        - queued_answers_list: List of queued answers (for actual processing, sorted by priority)
    """
    s = ensure_state(s)
    queued_answers = s.get("queued_answers", [])
    
    if not queued_answers:
        return 0, []
    
    # Check if network is available
    if not check_network_status():
        return 0, []
    
    # Phase 2.2.3: Ensure answers are sorted by priority
    # (should already be sorted when queued, but re-sort for safety)
    queued_answers.sort(key=lambda x: (-x.get("priority", 0), x.get("timestamp", 0)))
    
    # Phase 2.2.3: Batch processing - process N answers at a time
    if batch_size and batch_size > 0:
        answers_to_process = queued_answers[:batch_size]
        processed_count = len(answers_to_process)
        
        # Remove processed answers from queue
        if clear_after_processing:
            s["queued_answers"] = queued_answers[batch_size:]
            save_state_to_disk(s)
    else:
        # Process all answers
        answers_to_process = queued_answers
        processed_count = len(answers_to_process)
        
        # Clear queued answers if requested (they'll be processed now)
        if clear_after_processing:
            s["queued_answers"] = []
            save_state_to_disk(s)
    
    return processed_count, answers_to_process


def get_queue_status(s: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get status of queued answers for UI display.
    
    Phase 2.2.3: Queue status indicator.
    
    Args:
        s: State dictionary
        
    Returns:
        Dictionary with queue status information
    """
    s = ensure_state(s)
    queued_answers = s.get("queued_answers", [])
    network_status = s.get("network_status", "online")
    
    return {
        "queued_count": len(queued_answers),
        "network_status": network_status,
        "oldest_timestamp": queued_answers[0].get("timestamp") if queued_answers else None,
        "newest_timestamp": queued_answers[-1].get("timestamp") if queued_answers else None,
        "has_queued": len(queued_answers) > 0,
        "is_offline": network_status == "offline"
    }

