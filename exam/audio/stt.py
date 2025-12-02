"""
Speech-to-text (STT) module for exam.ipynb.

This module provides audio transcription functionality, converting spoken audio
recordings into text format for processing and analysis.

**Module Name**: `stt.py` (STT = Speech-To-Text)

**Key Functions**:
- `transcribe()`: Convert audio file to text using OpenAI Whisper API

**Usage Example**:
    ```python
    from exam.audio.stt import transcribe
    from openai import OpenAI
    
    client = OpenAI()
    transcript = transcribe(
        audio_path="/path/to/audio.wav",
        client=client,
        progress=lambda p: print(f"Progress: {p*100}%")
    )
    print(f"Transcribed text: {transcript}")
    ```

**Dependencies**:
- OpenAI client for Whisper API
- Circuit breaker protection (automatic, graceful degradation)

**Error Handling**:
- Raises ValueError if audio file is missing or empty
- Uses circuit breaker for graceful failure when API is unavailable
- Retries with exponential backoff on transient failures
"""

import os
from typing import Optional, Callable

from openai import OpenAI

from exam.utils import with_retry
from exam.config import STT_MODEL

# Constants (imported from exam.config for centralized configuration)
# Kept for backward compatibility


def transcribe(
    audio_path: str,
    client: OpenAI,
    progress: Optional[Callable] = None
) -> str:
    """
    Transcribe audio file to text.
    
    Args:
        audio_path: Path to audio file
        client: OpenAI client instance
        progress: Optional progress callback
        
    Returns:
        Transcribed text
        
    Raises:
        ValueError: If audio file is missing or empty
    """
    if not audio_path or not os.path.exists(audio_path):
        raise ValueError("No audio file provided.")
    if os.path.getsize(audio_path) == 0:
        raise ValueError("Audio file is empty (0 bytes).")
    
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
    
    with open(audio_path, "rb") as f:
        tr = with_retry(
            client.audio.transcriptions.create,
            circuit_breaker=circuit_breaker,
            service_name="openai_audio",
            model=STT_MODEL,
            file=f
        )
    
    if progress:
        progress(1.0)
    
    return tr.text or ""

