"""
Unit tests for shared.ferpa_audit module.

Tests cover audit trail logging, log file management, and FERPA compliance.
"""

import pytest
import os
import json
import tempfile
import shutil
from unittest.mock import patch, Mock, mock_open
from datetime import datetime, timezone, timedelta
from pathlib import Path
from shared.ferpa_audit import (
    get_audit_log_dir,
    get_audit_log_path,
    log_ferpa_access,
    read_audit_logs
)


class TestGetAuditLogDir:
    """Tests for get_audit_log_dir function."""
    
    def test_get_audit_log_dir_default(self):
        """Test default audit log directory."""
        with patch.dict(os.environ, {}, clear=True):
            log_dir = get_audit_log_dir()
            assert log_dir == "./ferpa_audit_logs"
            # Directory should be created
            assert os.path.exists(log_dir)
            # Cleanup
            if os.path.exists(log_dir):
                shutil.rmtree(log_dir)
    
    def test_get_audit_log_dir_custom(self):
        """Test custom audit log directory from environment variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": tmpdir}):
                log_dir = get_audit_log_dir()
                assert log_dir == tmpdir
                assert os.path.exists(log_dir)


class TestGetAuditLogPath:
    """Tests for get_audit_log_path function."""
    
    def test_get_audit_log_path_default(self):
        """Test audit log path for today."""
        with patch.dict(os.environ, {}, clear=True):
            log_path = get_audit_log_path()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            assert today in log_path
            assert log_path.endswith(".json")
    
    def test_get_audit_log_path_specific_date(self):
        """Test audit log path for specific date."""
        with patch.dict(os.environ, {}, clear=True):
            test_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
            log_path = get_audit_log_path(test_date)
            assert "2024-01-15" in log_path
            assert log_path.endswith(".json")


class TestLogFerpaAccess:
    """Tests for log_ferpa_access function."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for audit logs."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def test_log_ferpa_access_basic(self, temp_log_dir):
        """Test basic audit log entry creation."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when
            )
            
            # Verify log file was created
            log_path = get_audit_log_path(when)
            assert os.path.exists(log_path)
            
            # Verify log entry content
            with open(log_path, "r") as f:
                logs = json.load(f)
                assert len(logs) == 1
                entry = logs[0]
                assert entry["who"] == "INSTRUCTOR"
                assert entry["what"] == "batch_decrypt"
                assert entry["why"] == "grade_review"
                assert entry["when"] == when.isoformat() + "Z"
    
    def test_log_ferpa_access_with_session_id(self, temp_log_dir):
        """Test audit log entry with session ID (obfuscated)."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when,
                session_id="test_session_12345"
            )
            
            log_path = get_audit_log_path(when)
            with open(log_path, "r") as f:
                logs = json.load(f)
                entry = logs[0]
                assert entry["session_id"] == "****2345"  # Obfuscated
    
    def test_log_ferpa_access_with_user_id(self, temp_log_dir):
        """Test audit log entry with user ID."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when,
                user_id="instructor_123"
            )
            
            log_path = get_audit_log_path(when)
            with open(log_path, "r") as f:
                logs = json.load(f)
                entry = logs[0]
                assert entry["user_id"] == "instructor_123"
    
    def test_log_ferpa_access_sanitizes_pii(self, temp_log_dir):
        """Test that PII is sanitized from additional context."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when,
                additional_context={
                    "student_id": "should_be_removed",
                    "student_name": "should_be_removed",
                    "email": "should_be_removed",
                    "operation_count": 5  # Should be kept
                }
            )
            
            log_path = get_audit_log_path(when)
            with open(log_path, "r") as f:
                logs = json.load(f)
                entry = logs[0]
                if "context" in entry:
                    context = entry["context"]
                    assert "student_id" not in context
                    assert "student_name" not in context
                    assert "email" not in context
                    assert context.get("operation_count") == 5
    
    def test_log_ferpa_access_appends_to_existing(self, temp_log_dir):
        """Test that new entries are appended to existing log file."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            
            # Create first entry
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when
            )
            
            # Create second entry
            log_ferpa_access(
                who="ADMIN",
                what="export_data",
                why="compliance_audit",
                when=when
            )
            
            log_path = get_audit_log_path(when)
            with open(log_path, "r") as f:
                logs = json.load(f)
                assert len(logs) == 2
                assert logs[0]["who"] == "INSTRUCTOR"
                assert logs[1]["who"] == "ADMIN"
    
    def test_log_ferpa_access_handles_failure_gracefully(self):
        """Test that logging failure doesn't break the operation."""
        # Mock file operations to fail
        with patch('builtins.open', side_effect=IOError("Permission denied")):
            # Should not raise exception
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=datetime.now(timezone.utc)
            )
            # If we get here, the function handled the error gracefully


class TestReadAuditLogs:
    """Tests for read_audit_logs function."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for audit logs."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def test_read_audit_logs_no_logs(self, temp_log_dir):
        """Test reading logs when no logs exist."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            logs = read_audit_logs()
            assert logs == []
    
    def test_read_audit_logs_single_day(self, temp_log_dir):
        """Test reading logs from a single day."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            
            # Create log entries
            log_ferpa_access(
                who="INSTRUCTOR",
                what="batch_decrypt",
                why="grade_review",
                when=when
            )
            log_ferpa_access(
                who="ADMIN",
                what="export_data",
                why="compliance_audit",
                when=when
            )
            
            # Read logs
            logs = read_audit_logs()
            assert len(logs) == 2
    
    def test_read_audit_logs_filter_by_who(self, temp_log_dir):
        """Test filtering logs by 'who'."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=when)
            log_ferpa_access(who="ADMIN", what="export_data", why="compliance_audit", when=when)
            
            # Filter by INSTRUCTOR
            logs = read_audit_logs(who="INSTRUCTOR")
            assert len(logs) == 1
            assert logs[0]["who"] == "INSTRUCTOR"
    
    def test_read_audit_logs_filter_by_what(self, temp_log_dir):
        """Test filtering logs by 'what'."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=when)
            log_ferpa_access(who="ADMIN", what="export_data", why="compliance_audit", when=when)
            
            # Filter by batch_decrypt
            logs = read_audit_logs(what="batch_decrypt")
            assert len(logs) == 1
            assert logs[0]["what"] == "batch_decrypt"
    
    def test_read_audit_logs_date_range(self, temp_log_dir):
        """Test reading logs within a date range."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            # Create logs for different days
            day1 = datetime(2024, 1, 15, tzinfo=timezone.utc)
            day2 = datetime(2024, 1, 16, tzinfo=timezone.utc)
            day3 = datetime(2024, 1, 17, tzinfo=timezone.utc)
            
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=day1)
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=day2)
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=day3)
            
            # Read logs for day1 to day2
            logs = read_audit_logs(start_date=day1, end_date=day2)
            assert len(logs) == 2
    
    def test_read_audit_logs_handles_corrupted_file(self, temp_log_dir):
        """Test that corrupted log files are handled gracefully."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            # Create a corrupted log file
            log_path = get_audit_log_path()
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "w") as f:
                f.write("invalid json content")
            
            # Should return empty list, not raise exception
            logs = read_audit_logs()
            assert isinstance(logs, list)


class TestFerpaAuditIntegration:
    """Integration tests for audit module."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for audit logs."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    
    def test_full_audit_flow(self, temp_log_dir):
        """Test complete audit logging and retrieval flow."""
        with patch.dict(os.environ, {"FERPA_AUDIT_LOG_DIR": temp_log_dir}):
            when = datetime.now(timezone.utc)
            
            # Log multiple access events
            log_ferpa_access(who="INSTRUCTOR", what="batch_decrypt", why="grade_review", when=when)
            log_ferpa_access(who="ADMIN", what="export_data", why="compliance_audit", when=when)
            log_ferpa_access(who="INSTRUCTOR", what="single_decrypt", why="grade_review", when=when)
            
            # Read all logs
            all_logs = read_audit_logs()
            assert len(all_logs) == 3
            
            # Filter by who
            instructor_logs = read_audit_logs(who="INSTRUCTOR")
            assert len(instructor_logs) == 2
            
            # Filter by what
            batch_logs = read_audit_logs(what="batch_decrypt")
            assert len(batch_logs) == 1

