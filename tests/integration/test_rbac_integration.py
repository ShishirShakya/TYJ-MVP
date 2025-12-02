"""
Integration tests for RBAC-enabled flows.

Tests cover RBAC integration with actual handler functions and dependency injection.
"""

import pytest
import os
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from shared.ferpa_rbac import UserRole, require_role, can_access_student_data
from shared.ferpa_audit import log_ferpa_access


class TestRbacIntegration:
    """Integration tests for RBAC with handlers."""
    
    @pytest.fixture
    def mock_log_fn(self):
        """Create a mock logging function."""
        return Mock()
    
    @pytest.fixture
    def instructor_state(self):
        """Create instructor state."""
        return {"user_role": "INSTRUCTOR"}
    
    @pytest.fixture
    def student_state(self):
        """Create student state."""
        return {"user_role": "STUDENT", "student_id": "student_123"}
    
    @pytest.fixture
    def admin_state(self):
        """Create admin state."""
        return {"user_role": "ADMIN"}
    
    def test_batch_decrypt_rbac_flow(self, instructor_state, mock_log_fn):
        """Test RBAC flow for batch decryption."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Instructor should have access
            assert require_role(instructor_state, UserRole.INSTRUCTOR, "batch_decrypt", mock_log_fn) is True
            
            # Verify logging was called
            mock_log_fn.assert_called_once()
            call_kwargs = mock_log_fn.call_args[1]
            assert call_kwargs["who"] == "INSTRUCTOR"
            assert call_kwargs["what"] == "student_data_access"
            assert call_kwargs["why"] == "batch_decrypt"
    
    def test_batch_decrypt_rbac_denied(self, student_state, mock_log_fn):
        """Test that students cannot access batch decryption."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Student should not have access
            assert require_role(student_state, UserRole.INSTRUCTOR, "batch_decrypt", mock_log_fn) is False
            
            # Logging should not be called for denied access
            mock_log_fn.assert_not_called()
    
    def test_per_student_access_instructor(self, instructor_state, mock_log_fn):
        """Test instructor accessing any student's data."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Instructor can access any student's data
            assert can_access_student_data(
                instructor_state,
                "student_123",
                "grade_review",
                mock_log_fn
            ) is True
            
            # Verify logging was called
            mock_log_fn.assert_called_once()
    
    def test_per_student_access_student_own(self, student_state, mock_log_fn):
        """Test student accessing their own data."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Student can access their own data
            assert can_access_student_data(
                student_state,
                "student_123",  # Same as student_state["student_id"]
                "exam_taking",
                mock_log_fn
            ) is True
            
            # Verify logging was called
            mock_log_fn.assert_called_once()
    
    def test_per_student_access_student_denied(self, student_state, mock_log_fn):
        """Test student cannot access another student's data."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Student cannot access another student's data
            assert can_access_student_data(
                student_state,
                "student_456",  # Different student
                "exam_taking",
                mock_log_fn
            ) is False
            
            # Logging should not be called for denied access
            mock_log_fn.assert_not_called()
    
    def test_admin_access_any_student(self, admin_state, mock_log_fn):
        """Test admin can access any student's data."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            # Admin can access any student's data
            assert can_access_student_data(
                admin_state,
                "student_123",
                "compliance_audit",
                mock_log_fn
            ) is True
            
            # Verify logging was called
            mock_log_fn.assert_called_once()
    
    def test_rbac_disabled_backward_compatibility(self, student_state):
        """Test that RBAC disabled allows access (backward compatibility)."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=False):
            # When RBAC disabled, access should be allowed
            assert require_role(student_state, UserRole.INSTRUCTOR, "batch_decrypt", None) is True
    
    def test_rbac_with_dependencies_pattern(self, instructor_state):
        """Test RBAC pattern used in handlers with dependencies."""
        # Simulate dependencies dictionary
        dependencies = {
            "require_role": require_role,
            "log_ferpa_access": log_ferpa_access,
            "get_user_role": lambda state: UserRole(state.get("user_role")) if state.get("user_role") else None
        }
        
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            require_role_fn = dependencies.get("require_role")
            log_fn = dependencies.get("log_ferpa_access")
            
            # This is the pattern used in handlers
            if require_role_fn:
                has_access = require_role_fn(
                    instructor_state,
                    UserRole.INSTRUCTOR,
                    "batch_decrypt",
                    log_fn
                )
                assert has_access is True


class TestRbacErrorHandling:
    """Tests for RBAC error handling."""
    
    def test_rbac_handles_missing_role_gracefully(self):
        """Test that RBAC handles missing role gracefully."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {}  # No user_role
            assert require_role(state, UserRole.INSTRUCTOR, "test", None) is False
    
    def test_rbac_handles_invalid_role_gracefully(self):
        """Test that RBAC handles invalid role gracefully."""
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INVALID_ROLE"}
            assert require_role(state, UserRole.INSTRUCTOR, "test", None) is False
    
    def test_rbac_handles_logging_failure(self):
        """Test that logging failure doesn't break access check."""
        def failing_log_fn(**kwargs):
            raise Exception("Logging failed")
        
        with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
            state = {"user_role": "INSTRUCTOR"}
            # Should still return True even if logging fails
            assert require_role(state, UserRole.INSTRUCTOR, "test", failing_log_fn) is True


class TestRbacAuditIntegration:
    """Tests for RBAC integration with audit logging."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for audit logs."""
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def test_rbac_logs_to_audit_trail(self, temp_log_dir):
        """Test that RBAC access is logged to audit trail."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            with patch('shared.ferpa_rbac.is_rbac_enabled', return_value=True):
                state = {"user_role": "INSTRUCTOR"}
                
                # Perform access check with audit logging
                require_role(state, UserRole.INSTRUCTOR, "batch_decrypt", log_ferpa_access)
                
                # Verify log file was created
                from shared.ferpa_audit import get_audit_log_path, read_audit_logs
                log_path = get_audit_log_path()
                assert os.path.exists(log_path)
                
                # Verify log entry exists
                logs = read_audit_logs()
                assert len(logs) == 1
                assert logs[0]["who"] == "INSTRUCTOR"
                assert logs[0]["what"] == "student_data_access"
                assert logs[0]["why"] == "batch_decrypt"

