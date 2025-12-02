"""
Configuration objects for complex handlers.

These dataclasses consolidate multiple parameters into single objects,
improving code clarity and maintainability while preserving wiring.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class BatchDecryptConfig:
    """
    Configuration for batch decryption handler.
    
    Consolidates 34 parameters into a single object for better maintainability.
    This improves Principle #1 (Minimal, Clear Code) without breaking wiring.
    """
    # Display filter flags
    show_verdict: bool = True
    show_session_id: bool = False
    show_grade: bool = True
    show_duration: bool = True
    show_rubric_sub_scores: bool = False
    show_course_name: bool = True
    show_section: bool = True
    show_video_enabled: bool = False
    show_video_verdict: bool = False
    show_video_flags: bool = False
    show_audio_enabled: bool = False
    show_audio_verdict: bool = False
    show_audio_flags: bool = False
    show_stylometric: bool = False
    show_percentile: bool = False
    show_zscore: bool = False
    show_flag_extremes: bool = False
    
    # Grade adjustment flags
    enable_adjustment: bool = False
    method_statistical: bool = False
    method_percentile: bool = False
    method_confidence: bool = False
    
    # Statistical normalization parameters
    target_mean: float = 75.0
    target_std: float = 10.0
    
    # Percentile curving parameters
    top_pct: float = 10.0
    range_a: str = "90-100"
    range_b: str = "80-89"
    range_c: str = "70-79"
    
    # Confidence adjustment parameters
    conf_threshold: float = 0.7
    conf_factor: float = 1.1

