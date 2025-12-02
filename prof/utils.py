"""
Utility functions for prof.ipynb - duration calculations.

This module contains utility functions used only by prof.ipynb.
Functions used by multiple apps are in shared/.
"""

from typing import Tuple


def calculate_max_duration(num_questions: int, min_followups: int, max_followups: int, time_per_question: int = 60) -> Tuple[float, float]:
    """
    Calculate maximum examination duration.
    Formula: (time_per_question + 30 + 10) * (num_questions + (num_questions * max_followups))
    Returns: (max_duration_sec, max_duration_min)
    
    Args:
        num_questions: Number of questions
        min_followups: Minimum follow-ups per question
        max_followups: Maximum follow-ups per question
        time_per_question: Time per question in seconds (default: 60)
        
    Returns:
        Tuple of (max_duration_sec: float, max_duration_min: float)
    """
    PROCESSING_TIME = 30
    BUFFER_TIME = 10
    
    max_duration_sec = (time_per_question + PROCESSING_TIME + BUFFER_TIME) * \
                      (num_questions + (num_questions * max_followups))
    
    max_duration_min = max_duration_sec / 60
    
    return max_duration_sec, max_duration_min

