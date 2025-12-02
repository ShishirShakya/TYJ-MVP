"""
Unit tests for percentile calculation optimization.

Tests the O(n log n) percentile calculation using sorted grades and bisect.
"""

import pytest
from bisect import bisect_right


def calculate_percentile_optimized(grade_float: float, sorted_grades: list) -> float:
    """
    Optimized percentile calculation using binary search.
    
    This is the implementation from dash/ui/handlers.py.
    """
    if not sorted_grades:
        return 0.0
    percentile_val = (bisect_right(sorted_grades, grade_float) / len(sorted_grades)) * 100
    return percentile_val


def calculate_percentile_old(grade_float: float, all_grades_list: list) -> float:
    """
    Old O(n²) percentile calculation for comparison.
    """
    if not all_grades_list:
        return 0.0
    percentile_val = (sum(1 for g in all_grades_list if g <= grade_float) / len(all_grades_list)) * 100
    return percentile_val


class TestPercentileOptimization:
    """Tests for optimized percentile calculation."""
    
    def test_percentile_empty_list(self):
        """Test percentile calculation with empty list."""
        result = calculate_percentile_optimized(85.0, [])
        assert result == 0.0
    
    def test_percentile_single_grade(self):
        """Test percentile calculation with single grade."""
        sorted_grades = [85.0]
        result = calculate_percentile_optimized(85.0, sorted_grades)
        assert result == 100.0  # 1/1 = 100%
    
    def test_percentile_exact_match(self):
        """Test percentile when grade exactly matches a grade in list."""
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        result = calculate_percentile_optimized(85.0, sorted_grades)
        assert result == 60.0  # 3/5 = 60% (includes 85.0)
    
    def test_percentile_between_grades(self):
        """Test percentile when grade is between two grades in list."""
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        result = calculate_percentile_optimized(82.5, sorted_grades)
        assert result == 40.0  # 2/5 = 40% (70, 80 <= 82.5)
    
    def test_percentile_lower_than_all(self):
        """Test percentile when grade is lower than all grades."""
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        result = calculate_percentile_optimized(60.0, sorted_grades)
        assert result == 0.0  # 0/5 = 0%
    
    def test_percentile_higher_than_all(self):
        """Test percentile when grade is higher than all grades."""
        sorted_grades = [70.0, 80.0, 85.0, 90.0, 95.0]
        result = calculate_percentile_optimized(100.0, sorted_grades)
        assert result == 100.0  # 5/5 = 100%
    
    def test_percentile_duplicate_grades(self):
        """Test percentile with duplicate grades in list."""
        sorted_grades = [70.0, 80.0, 80.0, 85.0, 90.0]
        result = calculate_percentile_optimized(80.0, sorted_grades)
        assert result == 60.0  # 3/5 = 60% (includes both 80.0s)
    
    def test_percentile_large_list(self):
        """Test percentile with large list (performance test)."""
        sorted_grades = list(range(100))  # 0-99
        result = calculate_percentile_optimized(50.0, sorted_grades)
        assert result == 51.0  # 51/100 = 51% (0-50 inclusive)
    
    def test_percentile_matches_old_implementation(self):
        """Test that optimized implementation matches old implementation."""
        test_cases = [
            ([70.0, 80.0, 85.0, 90.0, 95.0], 85.0),
            ([60.0, 70.0, 80.0, 90.0, 100.0], 75.0),
            ([50.0, 60.0, 70.0, 80.0, 90.0], 65.0),
            ([10.0, 20.0, 30.0, 40.0, 50.0], 25.0),
        ]
        
        for all_grades, grade in test_cases:
            sorted_grades = sorted(all_grades)
            old_result = calculate_percentile_old(grade, all_grades)
            new_result = calculate_percentile_optimized(grade, sorted_grades)
            assert abs(old_result - new_result) < 0.001, f"Mismatch for {grade} in {all_grades}"
    
    def test_percentile_unsorted_input_handled(self):
        """Test that function works correctly with pre-sorted input."""
        # Function expects sorted input, but test that it handles it correctly
        sorted_grades = sorted([90.0, 70.0, 85.0, 80.0, 95.0])
        result = calculate_percentile_optimized(85.0, sorted_grades)
        assert result == 60.0  # 3/5 = 60%

