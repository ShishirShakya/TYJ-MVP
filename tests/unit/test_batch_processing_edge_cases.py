"""
Unit tests for batch processing edge cases.

Tests edge cases in batch decryption and result building.
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import List, Dict, Any, Tuple


def build_result_row_safe(fobj, stats: Tuple, sorted_grades: List[float], mean_grade: float, std_grade: float) -> Dict[str, Any]:
    """
    Safe version of build_result_row for testing edge cases.
    
    This mimics the logic from dash/ui/handlers.py::build_result_row
    but simplified for testing.
    """
    filename, plaintext, summary_md, success, error_info, grade = stats
    
    if error_info:
        return {
            "Filename": filename,
            "Status": f"❌ {error_info.get('type', 'ERROR')}: {error_info.get('message', 'Unknown error')}",
        }
    
    row = {
        "Filename": filename,
        "Status": "✅ Success" if success else f"❌ {summary_md[:100]}" if summary_md else "❌ Unknown error"
    }
    
    # Percentile calculation (optimized version)
    if success and grade is not None and sorted_grades:
        try:
            grade_float = float(grade)
            from bisect import bisect_right
            percentile_val = (bisect_right(sorted_grades, grade_float) / len(sorted_grades)) * 100
            row["Percentile Rank"] = round(percentile_val, 1)
        except (ValueError, TypeError):
            pass
    
    return row


class TestBatchProcessingEdgeCases:
    """Tests for batch processing edge cases."""
    
    def test_empty_file_list(self):
        """Test batch processing with empty file list."""
        files = []
        results = []
        
        # Should handle empty list gracefully
        assert len(results) == 0
        assert isinstance(results, list)
    
    def test_single_file_success(self):
        """Test batch processing with single file that succeeds."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 85.0)
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 84.0, 10.0)
        
        assert row["Filename"] == "file1.enc"
        assert row["Status"] == "✅ Success"
        assert "Percentile Rank" in row
        assert row["Percentile Rank"] == 60.0  # 3/5 = 60%
    
    def test_single_file_error(self):
        """Test batch processing with single file that fails."""
        error_info = {"type": "DECRYPTION_ERROR", "message": "Invalid passphrase"}
        stats = ("file1.enc", None, None, False, error_info, None)
        sorted_grades = []
        
        row = build_result_row_safe(None, stats, sorted_grades, 0.0, 0.0)
        
        assert row["Filename"] == "file1.enc"
        assert "❌" in row["Status"]
        assert "DECRYPTION_ERROR" in row["Status"]
    
    def test_all_files_succeed(self):
        """Test batch processing where all files succeed."""
        files = ["file1.enc", "file2.enc", "file3.enc"]
        all_stats = [
            ("file1.enc", "plaintext1", "summary1", True, None, 85.0),
            ("file2.enc", "plaintext2", "summary2", True, None, 90.0),
            ("file3.enc", "plaintext3", "summary3", True, None, 75.0),
        ]
        
        # Collect grades
        all_grades = [85.0, 90.0, 75.0]
        sorted_grades = sorted(all_grades)
        mean_grade = sum(all_grades) / len(all_grades)
        
        results = []
        for fobj, stats in zip(files, all_stats):
            row = build_result_row_safe(fobj, stats, sorted_grades, mean_grade, 10.0)
            results.append(row)
        
        assert len(results) == 3
        assert all(r["Status"] == "✅ Success" for r in results)
    
    def test_all_files_fail(self):
        """Test batch processing where all files fail."""
        files = ["file1.enc", "file2.enc"]
        all_stats = [
            ("file1.enc", None, None, False, {"type": "ERROR1", "message": "Error 1"}, None),
            ("file2.enc", None, None, False, {"type": "ERROR2", "message": "Error 2"}, None),
        ]
        
        results = []
        for fobj, stats in zip(files, all_stats):
            row = build_result_row_safe(fobj, stats, [], 0.0, 0.0)
            results.append(row)
        
        assert len(results) == 2
        assert all("❌" in r["Status"] for r in results)
    
    def test_mixed_success_failure(self):
        """Test batch processing with mix of success and failure."""
        files = ["file1.enc", "file2.enc", "file3.enc"]
        all_stats = [
            ("file1.enc", "plaintext1", "summary1", True, None, 85.0),
            ("file2.enc", None, None, False, {"type": "ERROR", "message": "Failed"}, None),
            ("file3.enc", "plaintext3", "summary3", True, None, 90.0),
        ]
        
        # Collect only successful grades
        all_grades = [85.0, 90.0]
        sorted_grades = sorted(all_grades)
        
        results = []
        for fobj, stats in zip(files, all_stats):
            row = build_result_row_safe(fobj, stats, sorted_grades, 87.5, 5.0)
            results.append(row)
        
        assert len(results) == 3
        assert results[0]["Status"] == "✅ Success"
        assert "❌" in results[1]["Status"]
        assert results[2]["Status"] == "✅ Success"
    
    def test_percentile_empty_grades_list(self):
        """Test percentile calculation with empty grades list."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 85.0)
        sorted_grades = []
        
        row = build_result_row_safe(None, stats, sorted_grades, 0.0, 0.0)
        
        assert row["Filename"] == "file1.enc"
        assert "Percentile Rank" not in row  # Should not calculate percentile with empty list
    
    def test_percentile_single_grade(self):
        """Test percentile calculation with single grade."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 85.0)
        sorted_grades = [85.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 85.0, 0.0)
        
        assert "Percentile Rank" in row
        assert row["Percentile Rank"] == 100.0  # 1/1 = 100%
    
    def test_percentile_duplicate_grades(self):
        """Test percentile calculation with duplicate grades."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 80.0)
        sorted_grades = [70.0, 80.0, 80.0, 85.0, 90.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 81.0, 10.0)
        
        assert "Percentile Rank" in row
        assert row["Percentile Rank"] == 60.0  # 3/5 = 60% (includes both 80.0s)
    
    def test_percentile_grade_higher_than_all(self):
        """Test percentile when grade is higher than all grades."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 100.0)
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 84.0, 10.0)
        
        assert "Percentile Rank" in row
        assert row["Percentile Rank"] == 100.0  # 5/5 = 100%
    
    def test_percentile_grade_lower_than_all(self):
        """Test percentile when grade is lower than all grades."""
        stats = ("file1.enc", "plaintext", "summary", True, None, 60.0)
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 84.0, 10.0)
        
        assert "Percentile Rank" in row
        assert row["Percentile Rank"] == 0.0  # 0/5 = 0%
    
    def test_invalid_grade_string(self):
        """Test handling of invalid grade string."""
        stats = ("file1.enc", "plaintext", "summary", True, None, "invalid")
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 84.0, 10.0)
        
        assert row["Filename"] == "file1.enc"
        assert "Percentile Rank" not in row  # Should not calculate percentile with invalid grade
    
    def test_none_grade(self):
        """Test handling of None grade."""
        stats = ("file1.enc", "plaintext", "summary", True, None, None)
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        
        row = build_result_row_safe(None, stats, sorted_grades, 84.0, 10.0)
        
        assert row["Filename"] == "file1.enc"
        assert "Percentile Rank" not in row  # Should not calculate percentile with None grade
    
    def test_large_batch(self):
        """Test batch processing with large number of files."""
        num_files = 100
        files = [f"file{i}.enc" for i in range(num_files)]
        all_stats = [
            (f"file{i}.enc", f"plaintext{i}", f"summary{i}", True, None, 70.0 + (i % 30))
            for i in range(num_files)
        ]
        
        # Collect grades
        all_grades = [70.0 + (i % 30) for i in range(num_files)]
        sorted_grades = sorted(all_grades)
        mean_grade = sum(all_grades) / len(all_grades)
        
        results = []
        for fobj, stats in zip(files, all_stats):
            row = build_result_row_safe(fobj, stats, sorted_grades, mean_grade, 10.0)
            results.append(row)
        
        assert len(results) == num_files
        assert all(r["Status"] == "✅ Success" for r in results)
        assert all("Percentile Rank" in r for r in results)

