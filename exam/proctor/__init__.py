"""
Video proctoring module for exam.ipynb.

This module provides video proctoring functionality including:
- Face detection and multi-face detection
- Gaze analysis and head pose estimation
- Frame analysis and proctoring rule evaluation
- Proctor state management
- Calibration utilities

Modules:
- state.py: ProctorState class for managing proctoring state
- frame_analyzer.py: Main frame analysis function (proctor_analyze_frame)
- face_detector.py: Face detection utilities
- multi_face_detector.py: Multi-face detection utilities
- gaze_analyzer.py: Gaze and head pose analysis
- calibration.py: Calibration utilities
- config.py: Proctoring configuration (rules, flags, indices)

All functions use dependency injection to preserve wiring.
"""

from .state import ProctorState
from .frame_analyzer import proctor_analyze_frame
from .config import (
    PROCTOR_RULES,
    PROCTOR_CONFIG,
    PROCTOR_FLAG_RULES,
    _SPARSE_IDX,
    _HEADPOSE_IDX,
)

__all__ = [
    "ProctorState",
    "proctor_analyze_frame",
    "PROCTOR_RULES",
    "PROCTOR_CONFIG",
    "PROCTOR_FLAG_RULES",
    "_SPARSE_IDX",
    "_HEADPOSE_IDX",
]

