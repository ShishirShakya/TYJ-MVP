"""
Assessment API endpoints.

This module provides all assessment-related endpoints:
- Question generation
- Answer grading
- Audio processing
- Proctor analysis
- Link parsing
- Direct OpenAI wrapper endpoints
"""

import os
import tempfile
import shutil
import base64
from typing import Dict, Any
from fastapi import Request, APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import JSONResponse

from app.schemas import (
    GenerateQuestionRequest, GenerateQuestionResponse,
    GenerateQuestionDirectRequest, GenerateQuestionDirectResponse,
    GradeAnswerRequest, GradeAnswerResponse,
    GradeAnswerDirectRequest, GradeAnswerDirectResponse,
    ProcessAudioRequest, ProcessAudioResponse,
    AnalyzeProctorRequest, AnalyzeProctorResponse,
    ParseLinkRequest, ParseLinkResponse,
    GenerateTTSRequest, GenerateTTSResponse,
    GenerateFollowupQuestionRequest, GenerateFollowupQuestionResponse,
    ErrorResponse, Violation
)
from app.adapters import (
    load_state_from_session_id,
    build_flow_dependencies,
    call_ask_main_question,
    call_grade_current_block,
    call_handle_mic
)
from app.dependencies import get_openai_client
from app.auth import require_auth
from shared.logging_config import get_logger
from shared.constants import MAX_REQUEST_BODY_SIZE

logger = get_logger()

# Create router for assessment endpoints
router = APIRouter()


@router.post(
    "/generate-question",
    response_model=GenerateQuestionResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_question(
    request: Request,
    req: GenerateQuestionRequest,
    api_key: str = Depends(require_auth)
):
    """
    Generate assessment question for a student.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    **API Version**: v1 (current stable)
    
    **Version Negotiation**:
    - URL path: `/api/v1/assessments/generate-question` (major version)
    - Header: `X-API-Version: 1` (minor version)
    - Accept: `application/vnd.api+json;version=1` (minor version)
    
    **EVOLVABILITY**: Supports version negotiation for future changes (Principle #15).
    
    **Note**: This endpoint integrates with the exam flow logic in `exam/flow/questions.py`.
    """
    # EVOLVABILITY: Get negotiated API version (Principle #15)
    api_version = getattr(request.state, "api_version", "1")
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    try:
        # Load state from session_id
        state = load_state_from_session_id(req.session_id)
        if state is None:
            # Create new state if not found
            from exam.state.core import ensure_state
            state = ensure_state({"session_id": req.session_id})
            state["course_id"] = req.course_id
            state["exam_id"] = req.exam_id
        
        # Build dependencies
        dependencies = build_flow_dependencies(openai_client)
        
        # Call question generation
        updated_state, question_text, question_id = call_ask_main_question(
            state=state,
            client=openai_client,
            dependencies=dependencies
        )
        
        # Save updated state
        from exam.state.persistence import save_state_to_disk
        save_state_to_disk(updated_state)
        
        logger.info(
            "generate_question_success",
            request_id=request_id,
            session_id=req.session_id,
            question_id=question_id
        )
        
        return GenerateQuestionResponse(
            question=question_text,
            question_id=question_id,
            context_chunk=None  # Could be enhanced to return chunk info
        )
        
    except Exception as e:
        logger.error(
            "generate_question_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while generating question"},
            headers={"X-API-Version": api_version}
        )


@router.post(
    "/grade",
    response_model=GradeAnswerResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def grade_answer(
    request: Request,
    req: GradeAnswerRequest,
    api_key: str = Depends(require_auth)
):
    """
    Grade a student's answer.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    
    **Note**: This endpoint integrates with the grading logic in `exam/flow/grading.py`.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    try:
        # Load state from session_id
        state = load_state_from_session_id(req.session_id)
        if state is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Session {req.session_id} not found"}
            )
        
        # Add answer to state if not already present
        if req.answer:
            from exam.wrappers.state import queue_answer_locally
            from exam.config import PERSIST_OK
            queue_answer_locally(
                state,
                req.answer,
                audio_path=req.audio_path,
                PERSIST_OK=PERSIST_OK
            )
        
        # Build dependencies
        dependencies = build_flow_dependencies(openai_client)
        
        # Call grading
        updated_state, grading_result = call_grade_current_block(
            state=state,
            client=openai_client,
            dependencies=dependencies
        )
        
        # Save updated state
        from exam.state.persistence import save_state_to_disk
        save_state_to_disk(updated_state)
        
        logger.info(
            "grade_answer_success",
            request_id=request_id,
            session_id=req.session_id,
            question_id=req.question_id,
            score=grading_result["score"]
        )
        
        return GradeAnswerResponse(**grading_result)
        
    except Exception as e:
        logger.error(
            "grade_answer_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while grading answer"}
        )


@router.post(
    "/process-audio",
    response_model=ProcessAudioResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 413: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def process_audio(
    request: Request,
    audio_file: UploadFile = File(..., description="Audio file (WAV, MP3, etc.)"),
    session_id: str = Form(..., description="Student session ID", min_length=1, max_length=255),
    api_key: str = Depends(require_auth)
):
    """
    Process audio recording for assessment.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    
    **Note**: This endpoint integrates with the audio processing logic in `exam/flow/audio.py`.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    # Validate file size
    if audio_file.size and audio_file.size > MAX_REQUEST_BODY_SIZE:
        logger.warning(
            "audio_file_too_large",
            request_id=request_id,
            session_id=session_id,
            file_size=audio_file.size,
            max_size=MAX_REQUEST_BODY_SIZE
        )
        return JSONResponse(
            status_code=413,
            content={"detail": f"File too large. Maximum size: {MAX_REQUEST_BODY_SIZE} bytes"}
        )
    
    try:
        # Load state from session_id
        state = load_state_from_session_id(session_id)
        if state is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Session {session_id} not found"}
            )
        
        # Save uploaded file to temporary location
        temp_audio_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.filename)[1] if audio_file.filename else ".wav") as tmp_file:
                shutil.copyfileobj(audio_file.file, tmp_file)
                temp_audio_path = tmp_file.name
            
            # Build dependencies
            dependencies = build_flow_dependencies(openai_client)
            
            # Call audio processing
            updated_state, transcript, features = call_handle_mic(
                state=state,
                audio_path=temp_audio_path,
                client=openai_client,
                dependencies=dependencies
            )
            
            # Save updated state
            from exam.state.persistence import save_state_to_disk
            save_state_to_disk(updated_state)
            
            logger.info(
                "process_audio_success",
                request_id=request_id,
                session_id=session_id,
                transcript_length=len(transcript),
                temp_audio_path=temp_audio_path
            )
            
            return ProcessAudioResponse(
                transcript=transcript,
                features=features
            )
        finally:
            # Clean up temporary file
            if temp_audio_path and os.path.exists(temp_audio_path):
                try:
                    os.unlink(temp_audio_path)
                except Exception as cleanup_error:
                    logger.warning(
                        "temp_audio_cleanup_failed",
                        request_id=request_id,
                        session_id=session_id,
                        temp_path=temp_audio_path,
                        error_type=type(cleanup_error).__name__,
                        error_message=str(cleanup_error)[:200]
                    )
        
    except Exception as e:
        logger.error(
            "process_audio_error",
            request_id=request_id,
            session_id=session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while processing audio"}
        )


@router.post(
    "/analyze-proctor",
    response_model=AnalyzeProctorResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def analyze_proctor(
    request: Request,
    req: AnalyzeProctorRequest,
    api_key: str = Depends(require_auth)
):
    """
    Analyze proctoring data (face detection, gaze analysis, etc.).
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    
    **Note**: This endpoint integrates with the proctoring logic in `exam/proctor/`.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Validate frame data size (base64 encoded)
    if len(req.frame_data) > MAX_REQUEST_BODY_SIZE:
        logger.warning(
            "frame_data_too_large",
            request_id=request_id,
            session_id=req.session_id,
            frame_data_size=len(req.frame_data),
            max_size=MAX_REQUEST_BODY_SIZE
        )
        return JSONResponse(
            status_code=413,
            content={"detail": f"Frame data too large. Maximum size: {MAX_REQUEST_BODY_SIZE} bytes"}
        )
    
    try:
        # Load state from session_id
        state = load_state_from_session_id(req.session_id)
        if state is None:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Session {req.session_id} not found"}
            )
        
        # Decode base64 frame data
        try:
            frame_bytes = base64.b64decode(req.frame_data)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid base64 frame data"}
            )
        
        # Process proctoring frame
        from exam.proctor import ProctorState, proctor_analyze_frame
        
        # Check if MediaPipe is available
        try:
            import mediapipe as mp
            _HAS_PROCTOR = True
        except ImportError:
            mp = None
            _HAS_PROCTOR = False
        
        # Get or create ProctorState
        proctor_state = state.get("proctor_state")
        if not isinstance(proctor_state, ProctorState):
            proctor_state = ProctorState()
            state["proctor_state"] = proctor_state
        
        # Initialize ProctorState with MediaPipe if available
        if not proctor_state.enabled and _HAS_PROCTOR:
            proctor_state.start(_HAS_PROCTOR, mp)
        
        # Convert base64 bytes to image format
        try:
            from PIL import Image
            import io
            frame_image = Image.open(io.BytesIO(frame_bytes))
            try:
                import numpy as np
                frame = np.array(frame_image)
            except ImportError:
                frame = frame_image
        except Exception as decode_error:
            logger.warning(
                "frame_decode_failed",
                request_id=request_id,
                session_id=req.session_id,
                error_type=type(decode_error).__name__,
                error_message=str(decode_error)[:200]
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Unable to decode frame data. Expected base64-encoded image (PNG, JPEG, etc.)"}
            )
        
        # Set answering state based on exam phase
        proctor_state.answering = state.get("phase") in ("awaiting_main_answer", "awaiting_followup_answer")
        
        # Analyze frame
        summary, updated_proctor_state = proctor_analyze_frame(frame, proctor_state, _HAS_PROCTOR)
        
        # Update state
        state["proctor_state"] = updated_proctor_state
        state["proctor_summary"] = summary
        
        # Extract analysis results
        analysis = {
            "face_detected": summary.get("face_present_ratio", 0.0) > 0.0,
            "gaze_direction": "forward" if summary.get("away_ratio", 0.0) < 0.1 else "away",
            "multiple_faces": summary.get("multi_face_ratio", 0.0) > 0.0,
            "frames_analyzed": summary.get("frames", 0),
            "face_present_ratio": summary.get("face_present_ratio", 0.0),
            "away_ratio": summary.get("away_ratio", 0.0),
            "multi_face_ratio": summary.get("multi_face_ratio", 0.0),
            "avg_yaw_deg": summary.get("avg_yaw_deg", 0.0),
            "avg_pitch_deg": summary.get("avg_pitch_deg", 0.0),
            "timestamp": req.timestamp,
            "last_status": summary.get("status", "unknown"),
            "flags_total": summary.get("flags_total", 0)
        }
        
        # Extract violations
        violations = []
        flags = getattr(updated_proctor_state, "flags", [])
        for flag in flags:
            violation_type = flag.get("tag", "UNKNOWN")
            severity = "high" if violation_type in ("MULTI_FACE", "NO_FACE") else "medium"
            violations.append(Violation(
                type=violation_type,
                severity=severity,
                timestamp=req.timestamp,
                details=flag.get("detail", {})
            ))
        
        # Calculate confidence
        if _HAS_PROCTOR and updated_proctor_state.enabled:
            confidence = 0.95
        elif _HAS_PROCTOR:
            confidence = 0.70
        else:
            confidence = 0.50
        
        # Save updated state
        from exam.state.persistence import save_state_to_disk
        save_state_to_disk(state)
        
        logger.info(
            "analyze_proctor_success",
            request_id=request_id,
            session_id=req.session_id,
            timestamp=req.timestamp
        )
        
        return AnalyzeProctorResponse(
            analysis=analysis,
            violations=violations,
            confidence=confidence
        )
        
    except Exception as e:
        logger.error(
            "analyze_proctor_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while analyzing proctor data"}
        )


@router.post(
    "/parse-link",
    response_model=ParseLinkResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def parse_link(
    request: Request,
    req: ParseLinkRequest,
    api_key: str = Depends(require_auth)
):
    """
    Parse professor exam configuration link.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    
    This endpoint parses encoded exam configuration URLs and extracts
    configuration parameters including course ID, exam ID, number of questions,
    time per question, and PDF URL.
    """
    request_id = getattr(request.state, "request_id", "unknown")
    
    try:
        from shared.url_encoding import decode_config_from_url
        from shared.config_parsing import validate_config_params
        
        # Decode configuration from URL
        config = decode_config_from_url(str(req.url))
        
        if config is None:
            logger.warning(
                "parse_link_invalid_url",
                request_id=request_id,
                url=str(req.url)[:100]
            )
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid URL format. Expected format: base_url?pdf_url=...&course_id=...&exam_id=...&passphrase=... (new format) or base_url?pdf_url=...&config=... (old format)"}
            )
        
        # Validate configuration parameters
        is_valid, validation_error = validate_config_params(
            config,
            require_pdf=False,
            validate_time_per_question=False
        )
        
        if not is_valid:
            logger.warning(
                "parse_link_validation_failed",
                request_id=request_id,
                validation_error=validation_error
            )
            return JSONResponse(
                status_code=400,
                content={"detail": validation_error}
            )
        
        # Extract relevant fields for response
        response_data = {
            "config": {
                "course_id": config.get("course_id", "UNKNOWN"),
                "exam_id": config.get("exam_id", "UNKNOWN"),
                "num_questions": config.get("num_questions", 1),
                "min_followups": config.get("min_followups", 0),
                "max_followups": config.get("max_followups", config.get("min_followups", 0)),
                "time_per_question": config.get("time_per_question", 60),
                "section_id": config.get("section_id", "UNKNOWN"),
                "start_date": config.get("start_date"),
                "end_date": config.get("end_date")
            },
            "pdf_url": config.get("pdf_url") or None,
            "num_questions": config.get("num_questions"),
            "time_per_question": config.get("time_per_question")
        }
        
        logger.info(
            "parse_link_success",
            request_id=request_id,
            course_id=config.get("course_id"),
            exam_id=config.get("exam_id"),
            num_questions=config.get("num_questions")
        )
        
        return ParseLinkResponse(**response_data)
        
    except Exception as e:
        logger.error(
            "parse_link_error",
            request_id=request_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while parsing link"}
        )


@router.post(
    "/generate-question-direct",
    response_model=GenerateQuestionDirectResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_question_direct(
    request: Request,
    req: GenerateQuestionDirectRequest,
    api_key: str = Depends(require_auth)
):
    """
    Low-level question generation endpoint (direct OpenAI wrapper).
    
    This endpoint provides direct access to question generation without requiring
    full state management. Used internally by exam.py when API mode is enabled.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    # Phase 3.4: Log data access
    try:
        from shared.security_audit import log_data_access
        client_ip = request.client.host if request.client else "unknown"
        log_data_access(
            user_id=f"api_key:{api_key[:8]}...",
            resource_type="question_generation",
            resource_id=req.session_id or "unknown",
            action="GENERATE",
            session_id=req.session_id,
            ip_address=client_ip
        )
    except Exception:
        pass
    
    try:
        from exam.ai.question_generator import _gen_main_question_with_ctx
        from exam.state.core import ensure_state
        
        # Create minimal state for question generation
        state = ensure_state({
            "session_id": req.session_id or "api_session",
            "questions_meta": [
                {"question_text": q, "context_sha256": None}
                for q in req.previous_questions
            ]
        })
        
        # Generate question
        question = _gen_main_question_with_ctx(
            s=state,
            ctx_text=req.context_text,
            client=openai_client
        )
        
        logger.info(
            "generate_question_direct_success",
            request_id=request_id,
            session_id=req.session_id,
            question_length=len(question)
        )
        
        return GenerateQuestionDirectResponse(question=question)
        
    except Exception as e:
        logger.error(
            "generate_question_direct_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while generating question"}
        )


@router.post(
    "/grade-answer-direct",
    response_model=GradeAnswerDirectResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def grade_answer_direct(
    request: Request,
    req: GradeAnswerDirectRequest,
    api_key: str = Depends(require_auth)
):
    """
    Low-level answer grading endpoint (direct OpenAI wrapper).
    
    This endpoint provides direct access to answer grading without requiring
    full state management. Used internally by exam.py when API mode is enabled.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    # Phase 3.4: Log data access
    try:
        from shared.security_audit import log_data_access
        client_ip = request.client.host if request.client else "unknown"
        log_data_access(
            user_id=f"api_key:{api_key[:8]}...",
            resource_type="answer_grading",
            resource_id=req.session_id or "unknown",
            action="GRADE",
            session_id=req.session_id,
            ip_address=client_ip
        )
    except Exception:
        pass
    
    try:
        from exam.ai.grader import _parse_feedback, _calculate_overall_score
        from exam.utils import with_retry
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        
        # Get circuit breaker
        circuit_breaker_manager = get_default_circuit_breaker_manager()
        circuit_breaker = circuit_breaker_manager.get_breaker("openai_chat") if circuit_breaker_manager else None
        
        # Call OpenAI API
        comp = with_retry(
            openai_client.chat.completions.create,
            circuit_breaker=circuit_breaker,
            service_name="openai_chat",
            model=req.chat_model,
            messages=req.messages,
            temperature=0.2,
            max_tokens=500
        )
        
        # Extract feedback
        fb_raw = comp.choices[0].message.content.strip()
        
        # Parse feedback
        parse_result = _parse_feedback(fb_raw)
        if not isinstance(parse_result, tuple) or len(parse_result) != 2:
            scores_dict = {}
            feedback_text = fb_raw
        else:
            scores_dict, feedback_text = parse_result
        
        if not isinstance(scores_dict, dict):
            scores_dict = {}
        
        # Calculate overall score
        overall_score = _calculate_overall_score(scores_dict)
        scores_dict["Overall"] = overall_score
        
        logger.info(
            "grade_answer_direct_success",
            request_id=request_id,
            session_id=req.session_id,
            overall_score=overall_score
        )
        
        return GradeAnswerDirectResponse(
            scores_dict=scores_dict,
            feedback_text=feedback_text,
            overall_score=overall_score
        )
        
    except Exception as e:
        logger.error(
            "grade_answer_direct_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while generating question"}
        )


@router.post(
    "/generate-tts",
    response_model=GenerateTTSResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_tts(
    request: Request,
    req: GenerateTTSRequest,
    api_key: str = Depends(require_auth)
):
    """
    Generate text-to-speech audio (low-level OpenAI wrapper).
    
    This endpoint provides direct access to TTS generation without requiring
    full state management. Used internally by exam.py when API mode is enabled.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    try:
        from exam.state.core import ensure_state
        from exam.config import TTS_MODEL, TTS_VOICE
        from exam.file_utils import _paths_for_session
        from exam.utils import with_retry
        from shared.circuit_breaker import get_default_circuit_breaker_manager
        
        # Create minimal state
        state = ensure_state({
            "session_id": req.session_id or "api_session"
        })
        
        # Use provided model/voice or defaults
        model = req.model or TTS_MODEL
        voice = req.voice or TTS_VOICE
        
        # Get circuit breaker
        circuit_breaker_manager = get_default_circuit_breaker_manager()
        circuit_breaker = circuit_breaker_manager.get_breaker("openai_audio") if circuit_breaker_manager else None
        
        # Truncate text
        text_truncated = req.text[:4096]
        
        # Generate TTS audio
        resp = with_retry(
            openai_client.audio.speech.create,
            circuit_breaker=circuit_breaker,
            service_name="openai_audio",
            model=model,
            voice=voice,
            input=text_truncated
        )
        
        # Save to temporary file
        paths = _paths_for_session(state)
        tmp_dir = paths.get("TMP_DIR", tempfile.gettempdir())
        os.makedirs(tmp_dir, exist_ok=True)
        
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3", dir=tmp_dir)
        
        # Extract audio bytes
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
        
        audio_path = tmp.name
        
        # Optionally encode as base64
        audio_base64 = None
        try:
            with open(audio_path, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            pass
        
        logger.info(
            "generate_tts_success",
            request_id=request_id,
            session_id=req.session_id,
            text_length=len(text_truncated),
            audio_path=audio_path
        )
        
        return GenerateTTSResponse(
            audio_path=audio_path,
            audio_base64=audio_base64
        )
        
    except Exception as e:
        logger.error(
            "generate_tts_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while generating question"}
        )


@router.post(
    "/generate-followup-question-direct",
    response_model=GenerateFollowupQuestionResponse,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}
)
async def generate_followup_question_direct(
    request: Request,
    req: GenerateFollowupQuestionRequest,
    api_key: str = Depends(require_auth)
):
    """
    Generate follow-up question directly (low-level OpenAI wrapper).
    
    This endpoint provides direct access to follow-up question generation without requiring
    full state management. Used internally by exam.py when API mode is enabled.
    
    **Authentication**: Required (X-API-Key header)
    **Rate Limiting**: Per-API-key rate limiting applied
    """
    request_id = getattr(request.state, "request_id", "unknown")
    openai_client = get_openai_client()
    
    try:
        from exam.ai.question_generator import _gen_followup_direct
        
        # Generate follow-up question
        question = _gen_followup_direct(
            main_question=req.main_question,
            student_answer=req.student_answer,
            context_text=req.context_text,
            previous_followups=req.previous_followups or [],
            client=openai_client
        )
        
        logger.info(
            "generate_followup_question_direct_success",
            request_id=request_id,
            session_id=req.session_id,
            question_length=len(question)
        )
        
        return GenerateFollowupQuestionResponse(question=question)
        
    except Exception as e:
        logger.error(
            "generate_followup_question_direct_error",
            request_id=request_id,
            session_id=req.session_id,
            error_type=type(e).__name__,
            error_message=str(e)[:200]
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error while generating question"}
        )

