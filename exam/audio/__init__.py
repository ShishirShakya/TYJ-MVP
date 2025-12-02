"""
Audio processing and analysis module for exam.ipynb.

This package provides comprehensive audio processing capabilities for the exam system:
- **Text-to-speech (TTS)**: Convert written questions to spoken audio
- **Speech-to-text (STT)**: Transcribe student audio responses to text
- **Voiceprint analysis**: Extract and compare voice characteristics
- **Stylometric analysis**: Detect AI-generated speech patterns

**Module Organization**:
- `tts.py`: Text-to-speech conversion (TTS = Text-To-Speech)
- `stt.py`: Speech-to-text transcription (STT = Speech-To-Text)
- `voiceprint.py`: Voiceprint extraction and comparison
- `stylometry.py`: Stylometric analysis for AI detection
- `utils.py`: Audio utility functions (duration, cleanup)

**Usage Example**:
    ```python
    from exam.audio import tts_to_mp3, transcribe
    from openai import OpenAI
    
    client = OpenAI()
    
    # Generate audio for question
    question_audio = tts_to_mp3(
        text="What is the main idea?",
        client=client
    )
    
    # Transcribe student response
    transcript = transcribe(
        audio_path="/path/to/student_response.wav",
        client=client
    )
    ```

**Abbreviations**:
- **TTS**: Text-To-Speech (converting text to audio)
- **STT**: Speech-To-Text (converting audio to text)
"""

from .tts import tts_to_mp3, TTS_MODEL, TTS_VOICE
from .stt import transcribe, STT_MODEL
from .voiceprint import extract_audio_features, compare_voiceprints
from .stylometry import analyze_speech_stylometry
from .utils import get_audio_duration, cleanup_session_tmp

__all__ = [
    # TTS
    "tts_to_mp3",
    "TTS_MODEL",
    "TTS_VOICE",
    # STT
    "transcribe",
    "STT_MODEL",
    # Voiceprint
    "extract_audio_features",
    "compare_voiceprints",
    # Stylometry
    "analyze_speech_stylometry",
    # Utils
    "get_audio_duration",
    "cleanup_session_tmp",
]

