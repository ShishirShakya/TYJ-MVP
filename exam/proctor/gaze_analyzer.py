"""
Gaze analysis functions for video proctoring.
"""

from .config import PROCTOR_RULES, PROCTOR_FLAG_RULES


def _calculate_yaw_pitch(pts, headpose_idx):
    """Calculate yaw and pitch from face landmarks."""
    le, re = headpose_idx["L_EAR"], headpose_idx["R_EAR"]
    nose, leye, reye, mouth = headpose_idx["NOSE"], headpose_idx["L_EYE"], headpose_idx["R_EYE"], headpose_idx["MOUTH"]
    ear_mid_x = 0.5 * (pts[le, 0] + pts[re, 0])
    yaw = (pts[nose, 0] - ear_mid_x) * 180.0
    eye_mid_y = 0.5 * (pts[leye, 1] + pts[reye, 1])
    pitch = (pts[mouth, 1] - eye_mid_y) * 180.0
    return float(yaw), float(pitch)


def _detect_away(yaw: float, pitch: float, yaw_threshold: float, pitch_threshold: float) -> bool:
    """Detect if student is looking away based on yaw/pitch thresholds."""
    return abs(yaw) > yaw_threshold or abs(pitch) > pitch_threshold


def _detect_extreme_gaze(yaw: float, pitch: float) -> bool:
    """Detect extreme gaze drift (external screen indicator)."""
    extreme_gaze_deg = PROCTOR_RULES.get("extreme_gaze_deg", 50)
    return abs(yaw) > extreme_gaze_deg or abs(pitch) > 30


def _adjust_thresholds_with_calibration(
    yaw: float,
    pitch: float,
    baseline_stats: dict,
    default_yaw_threshold: float,
    default_pitch_threshold: float
) -> tuple[float, float]:
    """Adjust thresholds based on calibration baseline statistics."""
    yaw_threshold = default_yaw_threshold
    pitch_threshold = default_pitch_threshold
    
    if baseline_stats.get("calibration_complete", False):
        baseline_yaw_mean = baseline_stats.get("baseline_yaw_mean", 0.0)
        baseline_yaw_std = baseline_stats.get("baseline_yaw_std", 0.0)
        baseline_pitch_mean = baseline_stats.get("baseline_pitch_mean", 0.0)
        baseline_pitch_std = baseline_stats.get("baseline_pitch_std", 0.0)
        
        # Allow ±2 std deviations from baseline
        if baseline_yaw_std > 0:
            yaw_threshold = max(yaw_threshold, abs(baseline_yaw_mean) + 2 * baseline_yaw_std)
        if baseline_pitch_std > 0:
            pitch_threshold = max(pitch_threshold, abs(baseline_pitch_mean) + 2 * baseline_pitch_std)
    
    return yaw_threshold, pitch_threshold

