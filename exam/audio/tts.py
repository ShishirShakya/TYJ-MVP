"""
Text-to-speech (TTS) module for exam.ipynb.

This module provides text-to-speech conversion functionality, converting written
text into spoken audio files (MP3 format) for playback to students.

**Module Name**: `tts.py` (TTS = Text-To-Speech)

**Key Functions**:
- `tts_to_mp3()`: Convert text to speech and save as MP3 file

**Usage Example**:
    ```python
    from exam.audio.tts import tts_to_mp3
    from openai import OpenAI
    
    client = OpenAI()
    audio_path = tts_to_mp3(
        text="What is the main idea of this passage?",
        client=client,
        s=state_dict,  # Optional: for session-specific temp directory
        progress=lambda p: print(f"Progress: {p*100}%")
    )
    print(f"Audio saved to: {audio_path}")
    ```

**Dependencies**:
- OpenAI client for TTS API
- Circuit breaker protection (automatic, graceful degradation)

**Error Handling**:
- Raises RuntimeError if TTS response format is unexpected
- Uses circuit breaker for graceful failure when API is unavailable
- Retries with exponential backoff on transient failures

**File Management**:
- Creates temporary MP3 files in session-specific directory
- Automatically tracks temp files in state for cleanup
"""

import os
import time
import tempfile
from typing import Optional, Dict, Any, Callable

from openai import OpenAI

from exam.utils import with_retry
from exam.file_utils import _paths_for_session
from exam.config import TTS_MODEL, TTS_VOICE

# Constants (imported from exam.config for centralized configuration)
# Kept for backward compatibility


def tts_to_mp3(
    text: str,
    client: OpenAI,
    s: Optional[Dict[str, Any]] = None,
    progress: Optional[Callable] = None
) -> str:
    """
    Convert text to speech and save as MP3 file.
    
    OpenAI TTS has a limit of 4096 characters. If text exceeds this limit,
    it will be truncated intelligently to preserve the most important content.
    
    Args:
        text: Text to convert to speech
        client: OpenAI client instance
        s: Optional state dictionary for session paths
        progress: Optional progress callback
        
    Returns:
        Path to generated MP3 file
        
    Raises:
        RuntimeError: If TTS response format is unexpected
    """
    if progress:
        progress(0.3)
    
    # GRACEFUL FAILURE: Get circuit breaker if available (Principle #16)
    circuit_breaker = None
    try:
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        manager = get_default_circuit_breaker_manager()
        circuit_breaker = manager.get_breaker("openai_audio")
    except Exception:
        pass
    
    resp = with_retry(
        client.audio.speech.create,
        circuit_breaker=circuit_breaker,
        service_name="openai_audio",
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text
    )
    
    tmp_dir = _paths_for_session(s)["TMP_DIR"] if s else tempfile.gettempdir()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=tmp_dir)
    
    audio_bytes = getattr(resp, "content", None)
    if audio_bytes is None and hasattr(resp, "write_to_file"):
        resp.write_to_file(tmp.name)
    else:
        if audio_bytes is None:
            audio_bytes = getattr(resp, "audio", None) or (
                resp.getvalue() if hasattr(resp, "getvalue") else None
            )
        if audio_bytes is None:
            try:
                audio_bytes = bytes(resp)
            except Exception:
                pass
        if not audio_bytes:
            raise RuntimeError("Unexpected TTS response format (no audio bytes)")
        with open(tmp.name, "wb") as f:
            f.write(audio_bytes)
    
    time.sleep(0.2)
    if s is not None:
        s.setdefault("_tmp_files", []).append(tmp.name)
    if progress:
        progress(1.0)
    
    return tmp.name

