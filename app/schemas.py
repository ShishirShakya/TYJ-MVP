"""
Pydantic models for FastAPI request/response validation.

This module provides type-safe request and response models for all API endpoints.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl, validator


class GenerateQuestionRequest(BaseModel):
    """Request model for question generation endpoint."""
    session_id: str = Field(..., description="Student session ID", min_length=1, max_length=255)
    course_id: str = Field(..., description="Course identifier", min_length=1, max_length=255)
    exam_id: str = Field(..., description="Exam identifier", min_length=1, max_length=255)
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context for question generation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_12345",
                "course_id": "CS101",
                "exam_id": "exam_001",
                "context": {"topic": "algorithms", "difficulty": "medium"}
            }
        }


class GenerateQuestionResponse(BaseModel):
    """Response model for question generation endpoint."""
    question: str = Field(..., description="Generated question text")
    question_id: str = Field(..., description="Unique question identifier")
    context_chunk: Optional[Dict[str, Any]] = Field(None, description="Context chunk used for question")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "Explain the time complexity of quicksort algorithm.",
                "question_id": "q_12345",
                "context_chunk": {"text": "Quicksort is a divide-and-conquer algorithm...", "page": 42}
            }
        }


class GradeAnswerRequest(BaseModel):
    """Request model for grading endpoint."""
    session_id: str = Field(..., description="Student session ID", min_length=1, max_length=255)
    answer: str = Field(..., description="Student's answer text", min_length=1)
    question_id: str = Field(..., description="Question identifier", min_length=1, max_length=255)
    audio_path: Optional[str] = Field(None, description="Path to audio recording")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_12345",
                "answer": "Quicksort has average time complexity of O(n log n)...",
                "question_id": "q_12345",
                "audio_path": "/path/to/audio.wav"
            }
        }


class RubricBreakdown(BaseModel):
    """Rubric breakdown for grading response."""
    criterion: str = Field(..., description="Grading criterion")
    score: float = Field(..., ge=0.0, le=1.0, description="Score for this criterion")
    feedback: str = Field(..., description="Feedback for this criterion")


class GradeAnswerResponse(BaseModel):
    """Response model for grading endpoint."""
    score: float = Field(..., ge=0.0, le=1.0, description="Overall score (0.0-1.0)")
    feedback: str = Field(..., description="Grading feedback")
    rubric: List[RubricBreakdown] = Field(..., description="Rubric breakdown")
    
    class Config:
        json_schema_extra = {
            "example": {
                "score": 0.85,
                "feedback": "Good understanding of the algorithm. Consider explaining the worst-case scenario.",
                "rubric": [
                    {
                        "criterion": "Correctness",
                        "score": 0.9,
                        "feedback": "Correct explanation of average case complexity"
                    },
                    {
                        "criterion": "Completeness",
                        "score": 0.8,
                        "feedback": "Missing discussion of worst-case complexity"
                    }
                ]
            }
        }


class ProcessAudioRequest(BaseModel):
    """Request model for audio processing endpoint."""
    session_id: str = Field(..., description="Student session ID", min_length=1, max_length=255)
    # Note: audio_file is handled as multipart/form-data, not JSON
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_12345"
            }
        }


class ProcessAudioResponse(BaseModel):
    """Response model for audio processing endpoint."""
    transcript: str = Field(..., description="Speech-to-text transcript")
    features: Dict[str, Any] = Field(..., description="Audio features extracted")
    
    class Config:
        json_schema_extra = {
            "example": {
                "transcript": "The quicksort algorithm has an average time complexity of O(n log n)...",
                "features": {
                    "duration": 5.2,
                    "voiceprint_match": 0.95,
                    "stylometry_score": 0.88
                }
            }
        }


class AnalyzeProctorRequest(BaseModel):
    """Request model for proctoring analysis endpoint."""
    session_id: str = Field(..., description="Student session ID", min_length=1, max_length=255)
    frame_data: str = Field(..., description="Base64-encoded video frame", min_length=1)
    timestamp: float = Field(..., ge=0.0, description="Frame timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_12345",
                "frame_data": "iVBORw0KGgoAAAANSUhEUgAA...",
                "timestamp": 1234567890.123
            }
        }


class Violation(BaseModel):
    """Proctoring violation detected."""
    type: str = Field(..., description="Violation type")
    severity: str = Field(..., description="Violation severity (low/medium/high)")
    timestamp: float = Field(..., description="Violation timestamp")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional violation details")


class AnalyzeProctorResponse(BaseModel):
    """Response model for proctoring analysis endpoint."""
    analysis: Dict[str, Any] = Field(..., description="Proctoring analysis results")
    violations: List[Violation] = Field(default_factory=list, description="Detected violations")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Analysis confidence score")
    
    class Config:
        json_schema_extra = {
            "example": {
                "analysis": {
                    "face_detected": True,
                    "gaze_direction": "forward",
                    "multiple_faces": False
                },
                "violations": [],
                "confidence": 0.95
            }
        }


class ParseLinkRequest(BaseModel):
    """Request model for link parsing endpoint."""
    url: HttpUrl = Field(..., description="Encoded exam configuration URL")
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/exam?config=encrypted_config_string"
            }
        }


class ParseLinkResponse(BaseModel):
    """Response model for link parsing endpoint."""
    config: Dict[str, Any] = Field(..., description="Parsed configuration")
    pdf_url: Optional[str] = Field(None, description="PDF URL")
    num_questions: Optional[int] = Field(None, ge=1, description="Number of questions")
    time_per_question: Optional[int] = Field(None, ge=1, description="Time per question in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "config": {
                    "course_id": "CS101",
                    "exam_id": "exam_001",
                    "duration_minutes": 60
                },
                "pdf_url": "https://example.com/exam.pdf",
                "num_questions": 5,
                "time_per_question": 600
            }
        }


class GenerateQuestionDirectRequest(BaseModel):
    """Request model for direct question generation (low-level OpenAI wrapper)."""
    context_text: str = Field(..., description="Context chunk text for question generation", min_length=10)
    previous_questions: Optional[List[str]] = Field(default_factory=list, description="Previous questions to avoid duplicates")
    session_id: Optional[str] = Field(None, description="Session ID for logging")
    
    class Config:
        json_schema_extra = {
            "example": {
                "context_text": "Machine learning is a subset of artificial intelligence...",
                "previous_questions": ["What is AI?", "Explain neural networks."],
                "session_id": "session_12345"
            }
        }


class GenerateQuestionDirectResponse(BaseModel):
    """Response model for direct question generation."""
    question: str = Field(..., description="Generated question text")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "What is the main difference between supervised and unsupervised learning?"
            }
        }


class GradeAnswerDirectRequest(BaseModel):
    """Request model for direct answer grading (low-level OpenAI wrapper)."""
    messages: List[Dict[str, str]] = Field(..., description="Chat messages for grading", min_items=1)
    chat_model: Optional[str] = Field("gpt-4o-mini", description="Chat model to use")
    session_id: Optional[str] = Field(None, description="Session ID for logging")
    
    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {"role": "system", "content": "You are a grading assistant."},
                    {"role": "user", "content": "Question: What is machine learning?\nAnswer: Machine learning is..."}
                ],
                "chat_model": "gpt-4o-mini",
                "session_id": "session_12345"
            }
        }


class GradeAnswerDirectResponse(BaseModel):
    """Response model for direct answer grading."""
    scores_dict: Dict[str, int] = Field(..., description="Scores dictionary with dimension scores")
    feedback_text: str = Field(..., description="Feedback text")
    overall_score: int = Field(..., ge=0, le=100, description="Overall score (0-100)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "scores_dict": {
                    "Conceptual": 85,
                    "Analytical": 80,
                    "Application": 75,
                    "Reflection": 70,
                    "Overall": 77
                },
                "feedback_text": "Good understanding of the concept. Consider providing more examples.",
                "overall_score": 77
            }
        }


class GenerateTTSRequest(BaseModel):
    """Request model for TTS endpoint."""
    text: str = Field(..., description="Text to convert to speech", min_length=1, max_length=4096)
    session_id: str = Field(..., description="Session ID for temp file management", min_length=1, max_length=255)
    model: Optional[str] = Field(None, description="TTS model to use (default: tts-1)")
    voice: Optional[str] = Field(None, description="Voice to use (default: alloy)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "What is the main idea of this passage?",
                "session_id": "session_12345",
                "model": "tts-1",
                "voice": "alloy"
            }
        }


class GenerateTTSResponse(BaseModel):
    """Response model for TTS endpoint."""
    audio_path: str = Field(..., description="Path to generated MP3 file")
    audio_base64: Optional[str] = Field(None, description="Base64-encoded audio data (optional)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "audio_path": "/tmp/session_12345/audio_abc123.mp3",
                "audio_base64": "UklGRiQAAABXQVZFZm10..."
            }
        }


class GenerateFollowupQuestionRequest(BaseModel):
    """Request model for follow-up question generation endpoint."""
    session_id: str = Field(..., description="Student session ID", min_length=1, max_length=255)
    main_question: str = Field(..., description="Main question text", min_length=1)
    student_answer: str = Field(..., description="Student's answer to main question", min_length=1)
    context_text: Optional[str] = Field(None, description="Context chunk text")
    previous_followups: Optional[List[str]] = Field(None, description="Previous follow-up questions")
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "session_12345",
                "main_question": "What is the time complexity of quicksort?",
                "student_answer": "It's O(n log n) on average.",
                "context_text": "Quicksort is a divide-and-conquer algorithm...",
                "previous_followups": []
            }
        }


class GenerateFollowupQuestionResponse(BaseModel):
    """Response model for follow-up question generation endpoint."""
    question: str = Field(..., description="Generated follow-up question text")
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "Can you explain why the worst-case time complexity is O(n²)?"
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response model."""
    detail: str = Field(..., description="Error message")
    error_type: Optional[str] = Field(None, description="Error type")
    request_id: Optional[str] = Field(None, description="Request ID for correlation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Invalid request body",
                "error_type": "VALIDATION_ERROR",
                "request_id": "req_12345"
            }
        }

