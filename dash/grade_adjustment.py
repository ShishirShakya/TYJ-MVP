"""
Grade adjustment algorithms for dash.ipynb.

This module contains pure functions for adjusting AI-generated grades:
- Statistical normalization (z-score based)
- Percentile curving (bracket-based)
- Confidence adjustment (reduce grade if low confidence)
- Confidence score calculation (from transcript analysis)
- Grade adjustment orchestration (applies multiple methods in sequence)

BUSINESS LOGIC ISOLATION: All grade adjustment business logic lives here (Principle #3).
UI handlers delegate to these functions - no business logic in UI layer.

DETERMINISTIC BEHAVIOR: All functions are pure and deterministic (Principle #5).
Same inputs always produce same outputs. No randomness or hidden state.
All functions can be unit tested with predictable results.
"""

from typing import Tuple, List, Optional
import numpy as np
from dash.parsing import _parse_rubric_scores
from shared.handler_configs import BatchDecryptConfig


def _calculate_confidence_score(plaintext: str) -> Tuple[float, str]:
    """
    Calculate confidence score based on answer characteristics.
    
    Uses rubric score consistency as a heuristic:
    - Lower variance in rubric scores = higher confidence
    - Higher variance = lower confidence
    
    DETERMINISTIC: Same input always produces same confidence score (Principle #5).
    
    Args:
        plaintext: Decrypted transcript plaintext
        
    Returns:
        Tuple of (confidence_score 0-100, confidence_label: "High"/"Medium"/"Low")
        
    Contract:
        - Input: plaintext (str) - decrypted transcript
        - Output: Tuple[float, str] - (confidence_score, label)
        - Deterministic: Same input → same output
        - No side effects: Pure function
        - Bounds: confidence_score always in [0, 100]
    """
    try:
        # Simple heuristic: Check for rubric score consistency
        rubric_avgs = _parse_rubric_scores(plaintext)
        if not rubric_avgs:
            return 50.0, "Medium"
        
        # Calculate variance in rubric scores (higher variance = lower confidence)
        scores = [v for v in rubric_avgs.values() if v is not None]
        if len(scores) < 2:
            return 50.0, "Medium"
        
        variance = np.var(scores)
        
        # Lower variance = higher confidence
        # Variance typically 0-400 (std 0-20), normalize to 0-100
        confidence = max(0, min(100, 100 - (variance / 4)))
        
        if confidence >= 80:
            label = "High"
        elif confidence >= 60:
            label = "Medium"
        else:
            label = "Low"
        
        return confidence, label
    except Exception:
        return 50.0, "Medium"


def _statistical_normalization(
    grade: float,
    batch_mean: float,
    batch_std: float,
    target_mean: float,
    target_std: float
) -> float:
    """
    Normalize grade to target distribution using z-scores.
    
    This adjusts grades to match a target mean and standard deviation,
    useful for normalizing across different batches or exam versions.
    
    DETERMINISTIC: Same inputs always produce same adjusted grade (Principle #5).
    
    Args:
        grade: Original grade to adjust
        batch_mean: Mean of current batch
        batch_std: Standard deviation of current batch
        target_mean: Target mean for adjusted grades
        target_std: Target standard deviation for adjusted grades
        
    Returns:
        Adjusted grade (clamped to [0, 100])
        
    Contract:
        - Input: grade, batch_mean, batch_std, target_mean, target_std (all float)
        - Output: Adjusted grade (float) in [0, 100]
        - Deterministic: Same inputs → same output
        - No side effects: Pure function
        - Edge case: Returns original grade if batch_std == 0
    """
    if batch_std == 0:
        return grade  # Can't normalize if no variance
    
    z_score = (grade - batch_mean) / batch_std
    adjusted = target_mean + (z_score * target_std)
    return max(0, min(100, adjusted))  # Clamp to [0, 100]


def _percentile_curving(
    grade: float,
    percentile: float,
    all_grades: List[float],
    top_pct: float,
    range_a: str,
    range_b: str,
    range_c: str
) -> float:
    """
    Map percentile to grade bracket using curving.
    
    This implements a percentile-based curving system where:
    - Top X% get A range
    - Next 20% get B range
    - Next 40% get C range
    - Bottom get D/F range
    
    Args:
        grade: Original grade (used for fallback)
        percentile: Percentile rank of the grade
        all_grades: List of all grades in batch
        top_pct: Percentage of top students to get A range
        range_a: A range (e.g., "90-100")
        range_b: B range (e.g., "80-89")
        range_c: C range (e.g., "70-79")
        
    Returns:
        Adjusted grade based on percentile bracket (clamped to [0, 100])
    """
    try:
        # Parse grade ranges
        def parse_range(range_str: str) -> Tuple[float, float]:
            """Parse range string like '90-100' into (min, max) tuple."""
            parts = range_str.split("-")
            if len(parts) == 2:
                return float(parts[0]), float(parts[1])
            return 90.0, 100.0  # Default to A range
        
        a_min, a_max = parse_range(range_a)
        b_min, b_max = parse_range(range_b)
        c_min, c_max = parse_range(range_c)
        
        # Determine which bracket based on percentile
        # Top % gets A range, next gets B, next gets C, rest gets D/F
        if percentile >= (100 - top_pct):
            # Top bracket: A range
            bracket_size = a_max - a_min
            position_in_bracket = (percentile - (100 - top_pct)) / top_pct
            adjusted = a_min + (position_in_bracket * bracket_size)
        elif percentile >= (100 - top_pct - 20):  # Next 20% gets B
            bracket_pct = 20
            bracket_start = 100 - top_pct - bracket_pct
            bracket_size = b_max - b_min
            position_in_bracket = (percentile - bracket_start) / bracket_pct
            adjusted = b_min + (position_in_bracket * bracket_size)
        elif percentile >= (100 - top_pct - 20 - 40):  # Next 40% gets C
            bracket_pct = 40
            bracket_start = 100 - top_pct - 20 - bracket_pct
            bracket_size = c_max - c_min
            position_in_bracket = (percentile - bracket_start) / bracket_pct
            adjusted = c_min + (position_in_bracket * bracket_size)
        else:
            # Bottom gets D/F (60-69)
            adjusted = 65.0  # Default D range middle
        
        return max(0, min(100, adjusted))
    except Exception:
        return grade  # Fallback to original if parsing fails


def _confidence_adjustment(
    grade: float,
    confidence_score: float,
    threshold: float,
    factor: float
) -> float:
    """
    Apply confidence-based adjustment (reduce grade if low confidence).
    
    If the confidence score is below the threshold, the grade is multiplied
    by the factor (typically < 1.0 to reduce the grade).
    
    Args:
        grade: Original grade to adjust
        confidence_score: Confidence score (0-100)
        threshold: Confidence threshold (if below, apply adjustment)
        factor: Multiplier to apply if confidence is low (typically 0.8-0.9)
        
    Returns:
        Adjusted grade (clamped to [0, 100])
    """
    if confidence_score < threshold:
        adjusted = grade * factor
        return max(0, min(100, adjusted))
    return grade  # No adjustment if confidence is high enough


def apply_grade_adjustments(
    grade_float: float,
    plaintext: str,
    percentile_val: Optional[float],
    all_grades_list: List[float],
    mean_grade: float,
    std_grade: float,
    config: BatchDecryptConfig
) -> Tuple[float, List[str], Optional[float], Optional[str]]:
    """
    Apply grade adjustments using configured methods.
    
    BUSINESS LOGIC ISOLATION: This function orchestrates grade adjustment business logic
    (Principle #3). UI handlers should call this function instead of implementing
    adjustment logic themselves.
    
    Applies adjustments in sequence:
    1. Statistical Normalization (if enabled)
    2. Percentile-Based Curving (if enabled)
    3. Confidence-Based Adjustment (if enabled, always last)
    
    DETERMINISTIC: Same inputs always produce same outputs (Principle #5).
    
    Args:
        grade_float: Original grade to adjust
        plaintext: Decrypted transcript plaintext (for confidence calculation)
        percentile_val: Percentile rank of the grade (None if not calculated)
        all_grades_list: List of all grades in batch (for percentile curving)
        mean_grade: Mean of all grades in batch
        std_grade: Standard deviation of all grades in batch
        config: BatchDecryptConfig with adjustment settings
        
    Returns:
        Tuple of:
        - adjusted_grade: Final adjusted grade
        - adjustment_methods: List of method names applied (e.g., ["Normalized", "Curved"])
        - conf_score: Confidence score if confidence adjustment was applied, None otherwise
        - conf_label: Confidence label if confidence adjustment was applied, None otherwise
        
    Contract:
        - Input: grade_float, plaintext, percentile_val, all_grades_list, mean_grade, std_grade, config
        - Output: Tuple[float, List[str], Optional[float], Optional[str]]
        - Deterministic: Same inputs → same output
        - No side effects: Pure function
        - Bounds: adjusted_grade always in [0, 100]
    """
    if not config.enable_adjustment or grade_float is None:
        return grade_float, [], None, None
    
    adjusted_grade = grade_float
    adjustment_methods = []
    conf_score = None
    conf_label = None
    
    # Method 1: Statistical Normalization
    if config.method_statistical and std_grade > 0:
        adjusted_grade = _statistical_normalization(
            adjusted_grade, mean_grade, std_grade,
            config.target_mean, config.target_std
        )
        adjustment_methods.append("Normalized")
    
    # Method 2: Percentile-Based Curving
    if config.method_percentile and percentile_val is not None:
        adjusted_grade = _percentile_curving(
            adjusted_grade, percentile_val, all_grades_list,
            config.top_pct,
            config.range_a,
            config.range_b,
            config.range_c
        )
        adjustment_methods.append("Curved")
    
    # Method 3: Confidence-Based Adjustment (always last)
    if config.method_confidence:
        # Calculate confidence score
        conf_score, conf_label = _calculate_confidence_score(plaintext)
        adjusted_grade = _confidence_adjustment(
            adjusted_grade,
            conf_score,
            config.conf_threshold,
            config.conf_factor
        )
        adjustment_methods.append(f"Confidence ({conf_label})")
    
    return adjusted_grade, adjustment_methods, conf_score, conf_label

