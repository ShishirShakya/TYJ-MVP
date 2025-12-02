"""
Unit tests for shared.ferpa_rbac module.

Tests cover role-based access control, role validation, and FERPA compliance.
"""

import pytest
import os
from unittest.mock import patch, Mock
from datetime import datetime, timezone
from shared.ferpa_rbac import (
    UserRole,
    is_rbac_enabled,
    get_user_role,
    require_role,
    has_instructor_access,
    has_student_access,
    format_ferpa_block_error
)


class TestUserRole:
    """Tests for UserRole enum."""
    
    def test_user_role_values(self):
        """Test that UserRole enum has correct values."""
        assert UserRole.STUDENT.value == "STUDENT"
        assert UserRole.INSTRUCTOR.value == "INSTRUCTOR"
        assert UserRole.ADMIN.value == "ADMIN"


class TestIsRbacEnabled:
    """Tests for is_rbac_enabled function."""
    
    def test_rbac_disabled_by_default(self):
        """Test that RBAC is disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            assert is_rbac_enabled() is False
    
    def test_rbac_enabled_when_set(self):
        """Test that RBAC is enabled when environment variable is set."""
        with patch.dict(os.environ, {"FERPA_RBAC_ENABLED": "true"}):
            assert is_rbac_enabled() is True
    
    def test_rbac_disabled_when_false(self):
        """Test that RBAC is disabled when environment variable is false."""
        with patch.dict(os.environ, {"FERPA_RBAC_ENABLED": "false"}):
            assert is_rbac_enabled() is False
    
    def test_rbac_case_insensitive(self):
        """Test that RBAC check is case-insensitive."""
        with patch.dict(os.environ, {"FERPA_RBAC_ENABLED": "TRUE"}):
            assert is_rbac_enabled() is True
        with patch.dict(os.environ, {"FERPA_RBAC_ENABLED": "True"}):
            assert is_rbac_enabled() is True


class TestGetUserRole:
    """Tests for get_user_role function."""
    
    def test_get_user_role_student(self):
        """Test getting STUDENT role from state."""
        state = {"user_role": "STUDENT"}
        assert get_user_role(state) == UserRole.STUDENT
    
    def test_get_user_role_instructor(self):
        """Test getting INSTRUCTOR role from state."""
        state = {"user_role": "INSTRUCTOR"}
        assert get_user_role(state) == UserRole.INSTRUCTOR
    
    def test_get_user_role_admin(self):
        """Test getting ADMIN role from state."""
        state = {"user_role": "ADMIN"}
        assert get_user_role(state) == UserRole.ADMIN
    
    def test_get_user_role_none_when_missing(self):
        """Test that None is returned when role is missing."""
        state = {}
        assert get_user_role(state) is None
    
    def test_get_user_role_none_when_invalid(self):
        """Test that None is returned when role is invalid."""
        state = {"user_role": "INVALID_ROLE"}
        assert get_user_role(state) is None
    
    def test_get_user_role_none_when_state_none(self):
        """Test that None is returned when state is None."""
        assert get_user_role(None) is None


class TestRequireRole:
    """Tests for require_role function."""
    
    @pytest.fixture
    def mock_log_fn(self):
        """Create a mock logging function."""
        return Mock()
    
    def test_require_role_allows_when_rbac_disabled(self, mock_log_fn):
        """Test that access is allowed when RBAC is disabled."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=False):
            state = {"user_role": "STUDENT"}
            result = require_role(state, UserRole.INSTRUCTOR, "test_purpose", mock_log_fn)
            assert result is True
            mock_log_fn.assert_not_called()
    
    def test_require_role_allows_matching_role(self, mock_log_fn):
        """Test that access is allowed when role matches."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            result = require_role(state, UserRole.INSTRUCTOR, "test_purpose", mock_log_fn)
            assert result is True
            # Log function should be called on successful access
            mock_log_fn.assert_called_once()
    
    def test_require_role_denies_non_matching_role(self, mock_log_fn):
        """Test that access is denied when role doesn't match."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "STUDENT"}
            result = require_role(state, UserRole.INSTRUCTOR, "test_purpose", mock_log_fn)
            assert result is False
            mock_log_fn.assert_not_called()
    
    def test_require_role_denies_when_role_unknown(self, mock_log_fn):
        """Test that access is denied when role cannot be determined."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {}
            result = require_role(state, UserRole.INSTRUCTOR, "test_purpose", mock_log_fn)
            assert result is False
            mock_log_fn.assert_not_called()
    
    def test_require_role_logs_on_success(self, mock_log_fn):
        """Test that logging function is called on successful access."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            require_role(state, UserRole.INSTRUCTOR, "grade_review", mock_log_fn)
            
            # Verify log function was called with correct parameters
            mock_log_fn.assert_called_once()
            call_kwargs = mock_log_fn.call_args[1]
            assert call_kwargs["who"] == "INSTRUCTOR"
            assert call_kwargs["what"] == "student_data_access"
            assert call_kwargs["why"] == "grade_review"
            assert isinstance(call_kwargs["when"], datetime)
    
    def test_require_role_handles_logging_failure(self):
        """Test that access check doesn't fail if logging fails."""
        def failing_log_fn(**kwargs):
            raise Exception("Logging failed")
        
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            # Should still return True even if logging fails
            result = require_role(state, UserRole.INSTRUCTOR, "test_purpose", failing_log_fn)
            assert result is True


class TestHasInstructorAccess:
    """Tests for has_instructor_access function."""
    
    def test_has_instructor_access_allows_instructor(self):
        """Test that instructor access is allowed for INSTRUCTOR role."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            assert has_instructor_access(state, "grade_review") is True
    
    def test_has_instructor_access_allows_admin(self):
        """Test that instructor access is allowed for ADMIN role."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "ADMIN"}
            assert has_instructor_access(state, "grade_review") is True
    
    def test_has_instructor_access_denies_student(self):
        """Test that instructor access is denied for STUDENT role."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "STUDENT"}
            assert has_instructor_access(state, "grade_review") is False


class TestHasStudentAccess:
    """Tests for has_student_access function."""
    
    def test_has_student_access_allows_student(self):
        """Test that student access is allowed for STUDENT role."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "STUDENT"}
            assert has_student_access(state, "exam_taking") is True
    
    def test_has_student_access_denies_instructor(self):
        """Test that student access is denied for INSTRUCTOR role."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            assert has_student_access(state, "exam_taking") is False


class TestFormatFerpaBlockError:
    """Tests for format_ferpa_block_error function."""
    
    def test_format_ferpa_block_error_without_correlation_id(self):
        """Test error message formatting without correlation ID."""
        msg = format_ferpa_block_error()
        assert "Access restricted under student privacy safeguards" in msg
        assert "Reference ID" not in msg
    
    def test_format_ferpa_block_error_with_correlation_id(self):
        """Test error message formatting with correlation ID."""
        correlation_id = "test-correlation-123"
        msg = format_ferpa_block_error(correlation_id)
        assert "Access restricted under student privacy safeguards" in msg
        assert correlation_id in msg
        assert "Reference ID" in msg


class TestFerpaRbacIntegration:
    """Integration tests for RBAC module."""
    
    def test_full_rbac_flow(self):
        """Test complete RBAC flow with logging."""
        mock_log_fn = Mock()
        
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Test instructor accessing student data
            instructor_state = {"user_role": "INSTRUCTOR"}
            assert require_role(instructor_state, UserRole.INSTRUCTOR, "batch_decrypt", mock_log_fn) is True
            
            # Test student trying to access instructor-only data
            student_state = {"user_role": "STUDENT"}
            assert require_role(student_state, UserRole.INSTRUCTOR, "batch_decrypt", mock_log_fn) is False
            
            # Verify logging was called for successful access
            assert mock_log_fn.call_count == 1
    
    def test_rbac_backward_compatibility(self):
        """Test that RBAC is backward compatible when disabled."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=False):
            # Even without role, access should be allowed (backward compatibility)
            state = {}
            assert require_role(state, UserRole.INSTRUCTOR, "test", None) is True

