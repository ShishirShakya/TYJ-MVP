"""
ProctorState class for managing video proctoring state.
"""

import hashlib
from datetime import datetime, timezone
from typing import Optional

from .config import _HEADPOSE_IDX


class ProctorState:
    """Manages state for video proctoring analysis."""
    
    def __init__(self):
        self.enabled = False
        self.frames = 0
        self.face_frames = 0
        self._hash_ctx = hashlib.sha256()

        # Running stats
        self.away_consec = 0
        self.away_frames = 0
        self.yaw_deg_avg = 0.0
        self.pitch_deg_avg = 0.0
        self._yaw_acc = 0.0
        self._pitch_acc = 0.0
        self.multi_face_frames = 0
        
        # Calibration data
        self.calibration_complete = False
        self.calibration_frames = 0
        self.calibration_yaw_samples = []
        self.calibration_pitch_samples = []
        self.baseline_yaw_mean = 0.0
        self.baseline_pitch_mean = 0.0
        self.baseline_yaw_std = 0.0
        self.baseline_pitch_std = 0.0

        # Per-block tallies (already in app)
        self.block_frames = 0
        self.block_face_frames = 0
        self.block_away_frames = 0
        self.block_multi_face_frames = 0

        # New: consecutive trackers for flagging while answering
        self._consec_multi = 0
        self._consec_no_face = 0
        self._consec_extreme_gaze = 0  # NEW: Track extreme gaze drift

        # New: flags (events) and counts
        self.flags = []             # list of {"ts_iso":..., "tag":..., "detail":...}
        self.flag_counts = {        # simple counters per tag
            "AWAY_BURST": 0,
            "MULTI_FACE": 0,
            "NO_FACE": 0,
            "EXTREME_GAZE": 0,
        }

        self.answering = False
        self.last_status = "idle"
        self._mesh = None
        
        # Break allowance tracking
        self.break_start_time = None
        self.break_duration = 0.0
        self.last_feedback_warning = None
        self.feedback_warning_time = None

    def start(self, has_proctor: bool, mp=None):
        """Initialize MediaPipe face mesh if available."""
        if has_proctor and self._mesh is None and mp is not None:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=2, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5
            )
        self.enabled = has_proctor

    def stop(self):
        """Stop MediaPipe face mesh and disable proctoring."""
        if self._mesh is not None:
            try:
                self._mesh.close()
            except Exception:
                pass
            self._mesh = None
        self.enabled = False

    def _yaw_pitch(self, pts):
        """Calculate yaw and pitch from face landmarks."""
        le, re = _HEADPOSE_IDX["L_EAR"], _HEADPOSE_IDX["R_EAR"]
        nose, leye, reye, mouth = _HEADPOSE_IDX["NOSE"], _HEADPOSE_IDX["L_EYE"], _HEADPOSE_IDX["R_EYE"], _HEADPOSE_IDX["MOUTH"]
        ear_mid_x = 0.5 * (pts[le, 0] + pts[re, 0])
        yaw = (pts[nose, 0] - ear_mid_x) * 180.0
        eye_mid_y = 0.5 * (pts[leye, 1] + pts[reye, 1])
        pitch = (pts[mouth, 1] - eye_mid_y) * 180.0
        return float(yaw), float(pitch)

    def _flag(self, tag: str, detail: Optional[dict] = None):
        """Record a one-shot event flag."""
        self.flag_counts[tag] = self.flag_counts.get(tag, 0) + 1
        self.flags.append({
            "ts_iso": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
            "tag": tag,
            "detail": detail or {},
        })

    def add_block_rollup(self):
        """Generate summary for current block and reset block counters."""
        f = max(1, self.block_frames)
        summary = {
            "block_frames": self.block_frames,
            "block_face_ratio": round(self.block_face_frames / f, 3),
            "block_away_ratio": round(self.block_away_frames / f, 3),
            "block_multi_face_ratio": round(self.block_multi_face_frames / f, 3),
        }
        self.block_frames = self.block_face_frames = self.block_away_frames = self.block_multi_face_frames = 0
        return summary

    def summary_global(self):
        """Generate global summary statistics."""
        f = max(1, self.frames)
        return {
            "frames": self.frames,
            "face_present_ratio": round(self.face_frames / f, 3),
            "avg_yaw_deg": round(self.yaw_deg_avg, 2),
            "avg_pitch_deg": round(self.pitch_deg_avg, 2),
            "away_ratio": round(self.away_frames / f, 3),
            "multi_face_ratio": round(self.multi_face_frames / f, 3),
            "vis_hash": self._hash_ctx.hexdigest()[:12],
            "status": self.last_status,
            # New: quick view of flags
            "flags_total": sum(self.flag_counts.values()),
            "flag_counts": dict(self.flag_counts),
        }

