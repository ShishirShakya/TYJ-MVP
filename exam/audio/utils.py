"""
Audio utility functions for exam.ipynb.

This module contains utility functions for audio processing:
- Audio duration calculation
- Temporary file cleanup
"""

import os
from typing import Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

# Optional mutagen import for MP3 duration
try:
    from mutagen.mp3 import MP3
    _HAS_MUTAGEN = True
except ImportError:
    _HAS_MUTAGEN = False


def get_audio_duration(audio_path: str) -> float:
    """
    Get audio duration in seconds from MP3 file.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Duration in seconds, or 0.0 if unable to determine
    """
    if not audio_path or not os.path.exists(audio_path):
        return 0.0
    
    try:
        if _HAS_MUTAGEN:
            audio_file = MP3(audio_path)
            return audio_file.info.length
        else:
            # Fallback: estimate based on file size (rough estimate)
            # MP3 files are typically ~1MB per minute at 128kbps
            file_size = os.path.getsize(audio_path)
            estimated_duration = (file_size / (1024 * 1024)) * 60  # Rough estimate
            return estimated_duration
    except Exception:
        # Fallback: return 0 if we can't determine duration
        return 0.0


def cleanup_session_tmp(s: Dict[str, Any], force: bool = False) -> None:
    """
    Clean up temporary files created during session.
    
    FERPA COMPLIANCE: Video, Audio, and Biometric Data (high sensitivity) - Mandate #11
    - Remote processing must be encrypted, non-persistent, with deletion post-analysis
    - NO reuse of media for model training unless legally exempted and approved
    
    This function ensures that all temporary audio/video files are deleted
    after processing to prevent unauthorized access or reuse.
    
    **SAFETY GUARD**: Only cleans up when exam phase is "complete" (successful completion
    or termination) unless `force=True` is specified. This prevents premature cleanup
    during active exam flow when audio files may still be needed for retries or analysis.
    
    Args:
        s: State dictionary containing _tmp_files list and phase field
        force: If True, cleanup even if phase != "complete" (for FERPA erasure scenarios)
    
    Note:
        Audio files are tracked in `_tmp_files` during the exam and only cleaned up
        when the exam completes successfully or terminates (errors/violations).
        This ensures files remain available for voiceprint analysis, retries, and
        error recovery during the active exam.
    """
    # Guard: Only cleanup when exam is complete (unless forced)
    phase = s.get("phase")
    if not force and phase != "complete":
        logger.warning(
            "cleanup_called_during_active_exam",
            session_id=s.get("session_id", "unknown"),
            phase=phase,
            force=force,
            tmp_files_count=len(s.get("_tmp_files", [])),
            message="cleanup_session_tmp called during active exam - skipping cleanup to preserve audio files"
        )
        return
    
    # Proceed with cleanup
    tmp_files = s.get("_tmp_files", [])
    cleaned_count = 0
    for pth in tmp_files:
        try:
            if os.path.exists(pth):
                os.remove(pth)
                cleaned_count += 1
        except Exception as e:
            logger.debug(
                "cleanup_file_failed",
                session_id=s.get("session_id", "unknown"),
                file_path=pth,
                error_type=type(e).__name__,
                error_message=str(e)[:200],
                message="Failed to delete temporary file (non-critical)"
            )
    
    s["_tmp_files"] = []
    
    # FERPA COMPLIANCE: Explicitly ensure no audio data remains in memory
    # Clear any audio data stored in state to prevent accidental persistence
    if "audio_data" in s:
        s["audio_data"] = None
    if "audio_features" in s:
        s["audio_features"] = None
    
    logger.debug(
        "cleanup_session_tmp_completed",
        session_id=s.get("session_id", "unknown"),
        phase=phase,
        force=force,
        files_cleaned=cleaned_count,
        message="Session temporary files cleaned up successfully"
    )

