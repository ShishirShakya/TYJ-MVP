"""
UI helper functions for dash.ipynb.

This module contains helper functions for UI calculations and formatting.
These are pure functions that don't depend on Gradio directly.
"""

import os
import csv
from typing import Optional


def convert_csv_to_excel(csv_path: str) -> Optional[str]:
    """
    Convert CSV file to Excel format (.xlsx).
    
    Args:
        csv_path: Path to the CSV file to convert
        
    Returns:
        Path to the created Excel file, or None if conversion failed
    """
    try:
        import openpyxl
        from openpyxl import Workbook
        
        # Read CSV
        with open(csv_path, 'r', encoding='utf-8') as f:
            csv_reader = csv.reader(f)
            rows = list(csv_reader)
        
        # Create Excel file
        excel_path = csv_path.replace('.csv', '.xlsx')
        wb = Workbook()
        ws = wb.active
        
        for row in rows:
            ws.append(row)
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        wb.save(excel_path)
        os.remove(csv_path)  # Remove CSV file
        return excel_path
    except ImportError:
        raise ImportError("Excel export requires 'openpyxl' package. Install with: pip install openpyxl")
    except Exception as e:
        # SECURITY: Sanitize error message - don't expose implementation details
        # Internal error details should be logged, not exposed to user
        raise Exception("Excel export failed. Please try CSV format instead.") from e


def get_csv_column_list() -> list:
    """
    Get the list of all columns to include in CSV export.
    
    Returns:
        List of column names (all 56 columns from batch_csv_summarize)
    """
    return [
        # Basic Information (3)
        "filename", "integrity_summary", "verdict_duplicate",
        # Session Information (7)
        "session_id", "student_id", "started_at", "completed_at",
        "num_blocks", "avg_overall", "duration_sec",
        # Exam Metadata (5)
        "course_id", "exam_id", "section_id", "start_date", "end_date",
        # Rubric Sub-Scores (4)
        "rubric_conceptual", "rubric_analytical", "rubric_application", "rubric_reflection",
        # Grade Adjustments (3)
        "original_grade", "adjusted_grade", "adjustment_methods",
        # Video Proctoring Telemetry (13)
        "proctor_enabled", "proctor_verdict", "proctor_reason",
        "face_present_ratio", "away_ratio", "multi_face_ratio",
        "flags_total", "flag_AWAY_BURST", "flag_MULTI_FACE", "flag_NO_FACE", "flag_EXTREME_GAZE",
        # Audio Analysis Telemetry (12)
        "audio_analysis_enabled", "audio_verdict", "audio_reason", "audio_flags_total",
        "flag_VOICEPRINT_MISMATCH", "flag_UNNATURAL_SPEECH_RATE",
        "flag_NO_HESITATION_PATTERN", "flag_LEXICAL_INCONSISTENCY", "flag_ZERO_PAUSE_DELIVERY",
        "flag_PROFANITY_DETECTED", "flag_ANSWER_REUSE_DETECTED",
        # Session Control Telemetry (2)
        "flag_SESSION_TIMEOUT", "flag_ANSWER_TIMEOUT"
    ]

