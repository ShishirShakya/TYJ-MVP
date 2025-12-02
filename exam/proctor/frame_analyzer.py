"""
Main frame analysis function for video proctoring.
"""

import time
from typing import Tuple, Any, Optional

# Optional numpy import (handled gracefully if not available)
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False

from .state import ProctorState
from .face_detector import _safe_np, _hash_landmarks
from .gaze_analyzer import _detect_away, _detect_extreme_gaze, _adjust_thresholds_with_calibration
from .multi_face_detector import _flag_multi_face
from .calibration import _collect_calibration_samples, _is_calibration_complete
from .config import PROCTOR_RULES, PROCTOR_CONFIG, PROCTOR_FLAG_RULES, _SPARSE_IDX


def proctor_analyze_frame(frame: Any, st: ProctorState, has_proctor: bool = True) -> Tuple[dict, ProctorState]:
    """
    Analyze a single video frame for proctoring violations.
    
    Args:
        frame: Video frame (numpy array or PIL Image)
        st: ProctorState instance
        has_proctor: Whether MediaPipe is available
        
    Returns:
        Tuple of (summary_dict, updated_state)
    """
    if not has_proctor or not st.enabled:
        st.last_status = "disabled" if not has_proctor else "off"
        return st.summary_global(), st

    img = _safe_np(frame)
    if img is None:
        st.last_status = "no_frame"
        return st.summary_global(), st

    res = st._mesh.process(img)
    st.frames += 1
    faces = getattr(res, "multi_face_landmarks", None) or []
    n_faces = len(faces)

    # Default increments / resets
    saw_face = (n_faces >= 1)
    if saw_face:
        st.face_frames += 1
        st._consec_no_face = 0
        # Choose the first face for pose
        lmk = faces[0]
        pts = np.array([[p.x, p.y, p.z] for p in lmk.landmark], dtype=np.float32)
        yaw, pitch = st._yaw_pitch(pts)
        
        # Calibration phase: collect baseline gaze patterns
        _collect_calibration_samples(st, yaw, pitch)
        _is_calibration_complete(st)
        
        st._yaw_acc += yaw
        st._pitch_acc += pitch
        st.yaw_deg_avg = st._yaw_acc / st.face_frames
        st.pitch_deg_avg = st._pitch_acc / st.face_frames

        # Away detection (adjust thresholds based on calibration if available)
        yaw_threshold = PROCTOR_RULES["yaw_max_deg"]
        pitch_threshold = PROCTOR_RULES["pitch_max_deg"]
        
        # If calibrated, adjust thresholds based on baseline (allow ±2 std deviations)
        if st.calibration_complete:
            yaw_threshold, pitch_threshold = _adjust_thresholds_with_calibration(
                yaw, pitch,
                {
                    "calibration_complete": st.calibration_complete,
                    "baseline_yaw_mean": st.baseline_yaw_mean,
                    "baseline_yaw_std": st.baseline_yaw_std,
                    "baseline_pitch_mean": st.baseline_pitch_mean,
                    "baseline_pitch_std": st.baseline_pitch_std,
                },
                yaw_threshold,
                pitch_threshold
            )
        
        away = _detect_away(yaw, pitch, yaw_threshold, pitch_threshold)
        if away:
            st.away_consec += 1
            # Track break duration for break allowance
            if st.answering:
                if st.break_start_time is None:
                    st.break_start_time = time.time()
                else:
                    st.break_duration = time.time() - st.break_start_time
            else:
                st.break_start_time = None
                st.break_duration = 0.0
            
            if st.away_consec >= PROCTOR_RULES["away_min_consec_frames"]:
                st.away_frames += 1
                if st.answering:
                    st.block_away_frames += 1
                    # Allow breaks up to allow_break_duration without flagging
                    allow_break_duration = PROCTOR_CONFIG.get("allow_break_duration", 5)
                    if st.break_duration > allow_break_duration:
                        # Fire AWAY_BURST flag at a higher burst threshold (only after break allowance)
                        if st.away_consec == PROCTOR_FLAG_RULES["away_flag_consec_frames"]:
                            st._flag("AWAY_BURST", {"consec_frames": st.away_consec})
        else:
            st.away_consec = 0
            st.break_start_time = None
            st.break_duration = 0.0
        
        # ADVANCED ANTI-CHEAT: Extreme gaze drift (external screen indicator)
        extreme_gaze = _detect_extreme_gaze(yaw, pitch)
        if extreme_gaze:
            st._consec_extreme_gaze += 1
            if st.answering and st._consec_extreme_gaze >= PROCTOR_FLAG_RULES.get("extreme_gaze_consec_frames", 8):
                st._flag("EXTREME_GAZE", {"consec_frames": st._consec_extreme_gaze, "yaw": round(yaw, 1), "pitch": round(pitch, 1)})
        else:
            st._consec_extreme_gaze = 0

        # Multi-face handling
        _flag_multi_face(st, n_faces)

        # Hash landmarks for visual hash
        _hash_landmarks(st._hash_ctx, pts[_SPARSE_IDX, :2])
        st.last_status = "present_away" if away else "present"
        if st.answering:
            st.block_frames += 1
            st.block_face_frames += 1

    else:
        # No face seen this frame
        st.last_status = "no_face"
        st.away_consec = 0
        st._consec_extreme_gaze = 0  # Reset extreme gaze when face lost
        if st.answering:
            st.block_frames += 1
            st._consec_no_face += 1
            # Optional: flag extended no-face while answering
            if st._consec_no_face == PROCTOR_FLAG_RULES["no_face_flag_consec_frames"]:
                st._flag("NO_FACE", {"consec_frames": st._consec_no_face})
        else:
            st._consec_no_face = 0
        st._consec_multi = 0

    return st.summary_global(), st

