"""
Calibration functions for video proctoring.
"""

import statistics
from typing import Optional

from .config import PROCTOR_CONFIG


def _collect_calibration_samples(st, yaw: float, pitch: float) -> None:
    """Collect calibration samples for baseline calculation."""
    if not st.calibration_complete:
        st.calibration_yaw_samples.append(yaw)
        st.calibration_pitch_samples.append(pitch)
        st.calibration_frames += 1


def _calculate_baseline_stats(st) -> None:
    """Calculate baseline statistics from calibration samples."""
    if st.calibration_yaw_samples:
        st.baseline_yaw_mean = statistics.mean(st.calibration_yaw_samples)
        st.baseline_yaw_std = statistics.stdev(st.calibration_yaw_samples) if len(st.calibration_yaw_samples) > 1 else 0.0
    if st.calibration_pitch_samples:
        st.baseline_pitch_mean = statistics.mean(st.calibration_pitch_samples)
        st.baseline_pitch_std = statistics.stdev(st.calibration_pitch_samples) if len(st.calibration_pitch_samples) > 1 else 0.0


def _is_calibration_complete(st) -> bool:
    """Check if calibration is complete based on frame count."""
    calibration_frames = PROCTOR_CONFIG.get("calibration_frames", 30)
    if st.calibration_frames >= calibration_frames and not st.calibration_complete:
        _calculate_baseline_stats(st)
        st.calibration_complete = True
    return st.calibration_complete

