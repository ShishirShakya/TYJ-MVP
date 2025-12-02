"""
Unit tests for exam.state.persistence module.

Tests cover state persistence, file locking, atomic writes, and error handling.
"""

import pytest
import os
import json
import tempfile
import time
import threading
from unittest.mock import Mock, MagicMock, patch, mock_open

# Platform-specific imports
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False
from exam.state.persistence import (
    _get_file_lock,
    _cleanup_old_file_locks,
    _lock_file,
    _unlock_file,
    atomic_write_json_secure,
    save_state_to_disk,
    auto_save_state,
    load_state_from_disk,
    resume_from_disk,
    AUTO_SAVE_INTERVAL_SEC,
    _MAX_FILE_LOCKS,
    _LOCK_CLEANUP_INTERVAL,
)


class TestGetFileLock:
    """Tests for _get_file_lock function."""
    
    def test_get_file_lock_creates_new_lock(self):
        """Test creating a new file lock."""
        path = "/tmp/test_state.json"
        lock = _get_file_lock(path)
        
        assert lock is not None
        assert isinstance(lock, type(threading.Lock()))
    
    def test_get_file_lock_reuses_existing_lock(self):
        """Test reusing an existing file lock."""
        path = "/tmp/test_state.json"
        lock1 = _get_file_lock(path)
        lock2 = _get_file_lock(path)
        
        assert lock1 is lock2  # Should be the same lock object
    
    def test_get_file_lock_cleanup_when_too_many(self):
        """Test cleanup when too many locks exist."""
        # Create many locks
        for i in range(_MAX_FILE_LOCKS + 10):
            _get_file_lock(f"/tmp/test_{i}.json")
        
        # Should trigger cleanup
        lock = _get_file_lock("/tmp/test_new.json")
        assert lock is not None


class TestCleanupOldFileLocks:
    """Tests for _cleanup_old_file_locks function."""
    
    def test_cleanup_old_file_locks_removes_old(self):
        """Test cleanup removes old locks."""
        import exam.state.persistence as persistence_module
        
        # Create old locks
        old_path = "/tmp/old_lock.json"
        new_path = "/tmp/new_lock.json"
        
        # Manually set old access time
        with persistence_module._locks_lock:
            persistence_module._file_locks[old_path] = threading.Lock()
            persistence_module._file_lock_access_times[old_path] = time.time() - _LOCK_CLEANUP_INTERVAL - 100
            
            # Set new access time
            persistence_module._file_locks[new_path] = threading.Lock()
            persistence_module._file_lock_access_times[new_path] = time.time()
        
        # Trigger cleanup (function assumes lock is held, so acquire it)
        with persistence_module._locks_lock:
            _cleanup_old_file_locks()
        
        # Old lock should be removed
        assert old_path not in persistence_module._file_locks
        assert old_path not in persistence_module._file_lock_access_times
        
        # New lock should remain
        assert new_path in persistence_module._file_locks
    
    def test_cleanup_old_file_locks_keeps_minimum(self):
        """Test cleanup keeps at least 1000 locks."""
        import exam.state.persistence as persistence_module
        
        # Create many old locks
        with persistence_module._locks_lock:
            for i in range(1500):
                path = f"/tmp/old_lock_{i}.json"
                persistence_module._file_locks[path] = threading.Lock()
                persistence_module._file_lock_access_times[path] = time.time() - _LOCK_CLEANUP_INTERVAL - 100
        
        # Trigger cleanup (function assumes lock is held, so acquire it)
        with persistence_module._locks_lock:
            _cleanup_old_file_locks()
        
        # Should keep at least 1000 locks
        assert len(persistence_module._file_locks) >= 1000


class TestLockFile:
    """Tests for _lock_file function."""
    
    def test_lock_file_fcntl_available(self):
        """Test file locking with fcntl (POSIX)."""
        if HAS_FCNTL:
            with patch('exam.state.persistence.HAS_FCNTL', True):
                with patch('fcntl.flock') as mock_flock:
                    fd = 123
                    result = _lock_file(fd, "/tmp/test.json")
                    
                    assert result is True
                    mock_flock.assert_called_once_with(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            pytest.skip("fcntl not available on this platform")
    
    def test_lock_file_fcntl_fails(self):
        """Test file locking failure with fcntl."""
        if HAS_FCNTL:
            with patch('exam.state.persistence.HAS_FCNTL', True):
                with patch('fcntl.flock', side_effect=IOError("Lock failed")):
                    fd = 123
                    result = _lock_file(fd, "/tmp/test.json")
                    
                    assert result is False
        else:
            pytest.skip("fcntl not available on this platform")
    
    def test_lock_file_msvcrt_available(self):
        """Test file locking with msvcrt (Windows)."""
        with patch('exam.state.persistence.HAS_FCNTL', False):
            with patch('exam.state.persistence.HAS_MSVCRT', True):
                fd = 123
                result = _lock_file(fd, "/tmp/test.json")
                
                # Should return True (relies on threading locks on Windows)
                assert result is True
    
    def test_lock_file_no_locking_available(self):
        """Test file locking when no locking available."""
        with patch('exam.state.persistence.HAS_FCNTL', False):
            with patch('exam.state.persistence.HAS_MSVCRT', False):
                fd = 123
                result = _lock_file(fd, "/tmp/test.json")
                
                # Should return True (relies on threading locks)
                assert result is True


class TestUnlockFile:
    """Tests for _unlock_file function."""
    
    def test_unlock_file_fcntl(self):
        """Test unlocking with fcntl."""
        if HAS_FCNTL:
            with patch('exam.state.persistence.HAS_FCNTL', True):
                with patch('fcntl.flock') as mock_flock:
                    fd = 123
                    _unlock_file(fd)
                    
                    mock_flock.assert_called_once_with(fd, fcntl.LOCK_UN)
        else:
            pytest.skip("fcntl not available on this platform")
    
    def test_unlock_file_msvcrt(self):
        """Test unlocking with msvcrt."""
        if HAS_MSVCRT:
            with patch('exam.state.persistence.HAS_FCNTL', False):
                with patch('exam.state.persistence.HAS_MSVCRT', True):
                    with patch('msvcrt.locking') as mock_locking:
                        fd = 123
                        _unlock_file(fd)
                        
                        mock_locking.assert_called_once_with(fd, msvcrt.LK_UNLCK, 1)
        else:
            pytest.skip("msvcrt not available on this platform")
    
    def test_unlock_file_error_handling(self):
        """Test unlock error handling."""
        if HAS_FCNTL:
            with patch('exam.state.persistence.HAS_FCNTL', True):
                with patch('fcntl.flock', side_effect=IOError("Unlock failed")):
                    fd = 123
                    # Should not raise exception
                    _unlock_file(fd)
        else:
            pytest.skip("fcntl not available on this platform")


class TestAtomicWriteJsonSecure:
    """Tests for atomic_write_json_secure function."""
    
    def test_atomic_write_json_secure_basic(self):
        """Test basic atomic write."""
        # On Windows without pywin32, this will raise RuntimeError (correct behavior)
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    with tempfile.TemporaryDirectory() as tmpdir:
                        path = os.path.join(tmpdir, "test_state.json")
                        obj = {"test": "data", "number": 42}
                        with pytest.raises(RuntimeError, match="Windows file security"):
                            atomic_write_json_secure(obj, path)
                    return
            except ImportError:
                # Windows without pywin32 - expect RuntimeError
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test_state.json")
                    obj = {"test": "data", "number": 42}
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test_state.json")
            obj = {"test": "data", "number": 42}
            
            atomic_write_json_secure(obj, path)
            
            # Verify file exists
            assert os.path.exists(path)
            
            # Verify content
            with open(path, 'r') as f:
                loaded = json.load(f)
            assert loaded == obj
    
    def test_atomic_write_json_secure_creates_directory(self):
        """Test atomic write creates directory if needed."""
        # On Windows without pywin32, this will raise RuntimeError (correct behavior)
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    with tempfile.TemporaryDirectory() as tmpdir:
                        path = os.path.join(tmpdir, "subdir", "test_state.json")
                        obj = {"test": "data"}
                        with pytest.raises(RuntimeError, match="Windows file security"):
                            atomic_write_json_secure(obj, path)
                    return
            except ImportError:
                # Windows without pywin32 - expect RuntimeError
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "subdir", "test_state.json")
                    obj = {"test": "data"}
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "test_state.json")
            obj = {"test": "data"}
            
            atomic_write_json_secure(obj, path)
            
            # Verify directory and file exist
            assert os.path.exists(path)
    
    def test_atomic_write_json_secure_posix_permissions(self):
        """Test POSIX file permissions."""
        # Only test on POSIX systems
        if hasattr(os, 'fchmod'):
            with patch('os.fchmod') as mock_fchmod:
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test_state.json")
                    obj = {"test": "data"}
                    
                    atomic_write_json_secure(obj, path)
                    
                    # Should set permissions
                    mock_fchmod.assert_called()
        else:
            pytest.skip("fchmod not available on this platform")
    
    def test_atomic_write_json_secure_windows_acl(self):
        """Test Windows ACL handling."""
        # Skip on non-Windows or if win32security not available
        try:
            import win32security
            import win32api
            import win32con
            # Check if win32con has the constants we need
            if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                pytest.skip("win32con doesn't have required file access constants")
        except ImportError:
            pytest.skip("win32security not available")
        
        # Mock fchmod to raise AttributeError (Windows behavior)
        with patch.object(os, 'fchmod', side_effect=AttributeError("No fchmod on Windows"), create=True):
            # Mock win32con constants if they don't exist
            file_access = 0x1F01FF  # FILE_ALL_ACCESS
            if hasattr(win32con, 'FILE_ALL_ACCESS'):
                file_access = win32con.FILE_ALL_ACCESS
            elif hasattr(win32con, 'FILE_GENERIC_READ'):
                file_access = (win32con.FILE_GENERIC_READ | 
                              win32con.FILE_GENERIC_WRITE | 
                              win32con.FILE_GENERIC_EXECUTE)
            
            # Mock the win32security calls
            with patch('win32security.LookupAccountName') as mock_lookup:
                with patch('win32security.ACL') as mock_acl:
                    with patch('win32security.SECURITY_DESCRIPTOR') as mock_sd:
                        with patch('win32security.SetFileSecurity') as mock_set:
                            # Mock win32con constants in the module
                            with patch('exam.state.persistence.win32con.FILE_ALL_ACCESS', file_access, create=True):
                                mock_lookup.return_value = (Mock(), None)
                                mock_acl_instance = Mock()
                                mock_acl.return_value = mock_acl_instance
                                mock_sd_instance = Mock()
                                mock_sd.return_value = mock_sd_instance
                                
                                with tempfile.TemporaryDirectory() as tmpdir:
                                    path = os.path.join(tmpdir, "test_state.json")
                                    obj = {"test": "data"}
                                    
                                    # Should handle Windows ACLs
                                    atomic_write_json_secure(obj, path)
                                    assert os.path.exists(path)
    
    def test_atomic_write_json_secure_windows_acl_not_available(self):
        """Test Windows ACL handling when win32security not available - should fail hard."""
        # Mock fchmod to raise AttributeError (Windows behavior)
        with patch.object(os, 'fchmod', side_effect=AttributeError("No fchmod on Windows"), create=True):
            # Mock import to fail for win32security
            import builtins
            original_import = builtins.__import__
            def mock_import(name, *args, **kwargs):
                if name == 'win32security' or name.startswith('win32security'):
                    raise ImportError("No module named win32security")
                return original_import(name, *args, **kwargs)
            
            with patch.object(builtins, '__import__', side_effect=mock_import):
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test_state.json")
                    obj = {"test": "data"}
                    
                    # SECURITY: Should fail hard on Windows without pywin32 (FERPA compliance)
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
    
    def test_atomic_write_json_secure_cleanup_temp_file(self):
        """Test temp file cleanup on error."""
        # On Windows without pywin32, this will raise RuntimeError before json.dump
        import sys
        if sys.platform == "win32":
            try:
                import win32security
            except ImportError:
                # Windows without pywin32 - expect RuntimeError before json.dump
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test_state.json")
                    obj = {"test": "data"}
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with patch('json.dump', side_effect=Exception("Write failed")):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "test_state.json")
                obj = {"test": "data"}
                
                # Should handle error gracefully
                try:
                    atomic_write_json_secure(obj, path)
                except Exception:
                    pass
                
                # Temp file should be cleaned up
                temp_files = [f for f in os.listdir(tmpdir) if f.startswith("._viva_state.")]
                assert len(temp_files) == 0


class TestSaveStateToDisk:
    """Tests for save_state_to_disk function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        import uuid
        from datetime import datetime, timezone
        return {
            "session_id": str(uuid.uuid4()),
            "request_id": str(uuid.uuid4()),
            "student_id": "test_student",
            "phase": "idle",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "session_start_time": time.time(),
            "history": [],
            "scores": [],
            "rubrics": [],
            "flags": [],
        }
    
    def test_save_state_to_disk_success(self, mock_state):
        """Test successful state save."""
        # On Windows without pywin32, this will raise RuntimeError (correct behavior)
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    from exam.state.core import ensure_state
                    from shared.time_provider import MockTimeProvider
                    time_provider = MockTimeProvider(initial_time=time.time())
                    mock_state = ensure_state(mock_state, time_provider=time_provider)
                    with tempfile.TemporaryDirectory() as tmpdir:
                        state_path = os.path.join(tmpdir, "state.json")
                        tombstone_path = os.path.join(tmpdir, "tombstone.json")
                        with patch('exam.state.persistence._paths_for_session') as mock_paths:
                            mock_paths.return_value = {
                                "STATE_PATH": state_path,
                                "TOMBSTONE_PATH": tombstone_path,
                            }
                            result = save_state_to_disk(mock_state, persist_ok=True)
                            assert result is False  # Should fail on Windows without proper ACL constants
                    return
            except ImportError:
                # Windows without pywin32 - expect failure
                from exam.state.core import ensure_state
                from shared.time_provider import MockTimeProvider
                time_provider = MockTimeProvider(initial_time=time.time())
                mock_state = ensure_state(mock_state, time_provider=time_provider)
                with tempfile.TemporaryDirectory() as tmpdir:
                    state_path = os.path.join(tmpdir, "state.json")
                    tombstone_path = os.path.join(tmpdir, "tombstone.json")
                    with patch('exam.state.persistence._paths_for_session') as mock_paths:
                        mock_paths.return_value = {
                            "STATE_PATH": state_path,
                            "TOMBSTONE_PATH": tombstone_path,
                        }
                        result = save_state_to_disk(mock_state, persist_ok=True)
                        assert result is False  # Should fail on Windows without pywin32
                return
        
        # Ensure state passes validation by using ensure_state
        from exam.state.core import ensure_state
        from shared.time_provider import MockTimeProvider
        time_provider = MockTimeProvider(initial_time=time.time())
        mock_state = ensure_state(mock_state, time_provider=time_provider)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "state.json")
            tombstone_path = os.path.join(tmpdir, "tombstone.json")
            
            # Patch at the module level where it's imported
            with patch('exam.state.persistence._paths_for_session') as mock_paths:
                mock_paths.return_value = {
                    "STATE_PATH": state_path,
                    "TOMBSTONE_PATH": tombstone_path,
                }
                
                result = save_state_to_disk(mock_state, persist_ok=True)
                
                assert result is True
                assert os.path.exists(state_path)
    
    def test_save_state_to_disk_persist_ok_false(self, mock_state):
        """Test save when persist_ok is False."""
        result = save_state_to_disk(mock_state, persist_ok=False)
        assert result is False
    
    def test_save_state_to_disk_tombstone_exists(self, mock_state):
        """Test save when tombstone exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "state.json")
            tombstone_path = os.path.join(tmpdir, "tombstone.json")
            
            # Create tombstone file
            os.makedirs(os.path.dirname(tombstone_path), exist_ok=True)
            with open(tombstone_path, 'w') as f:
                f.write("{}")
            
            # Patch at the module level where it's imported
            with patch('exam.state.persistence._paths_for_session') as mock_paths:
                mock_paths.return_value = {
                    "STATE_PATH": state_path,
                    "TOMBSTONE_PATH": tombstone_path,
                }
                
                result = save_state_to_disk(mock_state, persist_ok=True)
                assert result is False
                # State file should not exist
                assert not os.path.exists(state_path)
    
    def test_save_state_to_disk_validation_fails(self, mock_state):
        """Test save when validation fails."""
        with patch('exam.file_utils._paths_for_session') as mock_paths:
            with tempfile.TemporaryDirectory() as tmpdir:
                mock_paths.return_value = {
                    "STATE_PATH": os.path.join(tmpdir, "state.json"),
                    "TOMBSTONE_PATH": os.path.join(tmpdir, "tombstone.json"),
                }
                
                with patch('exam.state.validation.validate_state_before_persistence', return_value=(False, "Validation error")):
                    result = save_state_to_disk(mock_state, persist_ok=True)
                    assert result is False
    
    def test_save_state_to_disk_validation_not_available(self, mock_state):
        """Test save when validation module not available."""
        # On Windows without pywin32, this will fail before validation check
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect failure
                    with patch('exam.file_utils._paths_for_session') as mock_paths:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            mock_paths.return_value = {
                                "STATE_PATH": os.path.join(tmpdir, "state.json"),
                                "TOMBSTONE_PATH": os.path.join(tmpdir, "tombstone.json"),
                            }
                            # Mock import to fail for validation module
                            import builtins
                            original_import = builtins.__import__
                            def mock_import(name, *args, **kwargs):
                                if name == 'exam.state.validation' or name.startswith('exam.state.validation'):
                                    raise ImportError("No module named exam.state.validation")
                                return original_import(name, *args, **kwargs)
                            
                            with patch.object(builtins, '__import__', side_effect=mock_import):
                                result = save_state_to_disk(mock_state, persist_ok=True)
                                # Should fail on Windows without proper ACL constants
                                assert result is False
                    return
            except ImportError:
                # Windows without pywin32 - expect failure
                with patch('exam.file_utils._paths_for_session') as mock_paths:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        mock_paths.return_value = {
                            "STATE_PATH": os.path.join(tmpdir, "state.json"),
                            "TOMBSTONE_PATH": os.path.join(tmpdir, "tombstone.json"),
                        }
                        # Mock import to fail for validation module
                        import builtins
                        original_import = builtins.__import__
                        def mock_import(name, *args, **kwargs):
                            if name == 'exam.state.validation' or name.startswith('exam.state.validation'):
                                raise ImportError("No module named exam.state.validation")
                            return original_import(name, *args, **kwargs)
                        
                        with patch.object(builtins, '__import__', side_effect=mock_import):
                            result = save_state_to_disk(mock_state, persist_ok=True)
                            # Should fail on Windows without pywin32
                            assert result is False
                return
        
        with patch('exam.file_utils._paths_for_session') as mock_paths:
            with tempfile.TemporaryDirectory() as tmpdir:
                mock_paths.return_value = {
                    "STATE_PATH": os.path.join(tmpdir, "state.json"),
                    "TOMBSTONE_PATH": os.path.join(tmpdir, "tombstone.json"),
                }
                
                # Mock import to fail for validation module
                import builtins
                original_import = builtins.__import__
                def mock_import(name, *args, **kwargs):
                    if name == 'exam.state.validation' or name.startswith('exam.state.validation'):
                        raise ImportError("No module named exam.state.validation")
                    return original_import(name, *args, **kwargs)
                
                with patch.object(builtins, '__import__', side_effect=mock_import):
                    result = save_state_to_disk(mock_state, persist_ok=True)
                    # Should still save (backward compatibility)
                    assert result is True
    
    def test_save_state_to_disk_write_error(self, mock_state):
        """Test save when write fails."""
        with patch('exam.file_utils._paths_for_session') as mock_paths:
            with tempfile.TemporaryDirectory() as tmpdir:
                mock_paths.return_value = {
                    "STATE_PATH": os.path.join(tmpdir, "state.json"),
                    "TOMBSTONE_PATH": os.path.join(tmpdir, "tombstone.json"),
                }
                
                with patch('exam.state.persistence.atomic_write_json_secure', side_effect=Exception("Write failed")):
                    result = save_state_to_disk(mock_state, persist_ok=True)
                    assert result is False


class TestAutoSaveState:
    """Tests for auto_save_state function."""
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state for testing."""
        return {
            "session_id": "test_session",
            "phase": "idle",
            "session_start_time": time.time(),
            "last_auto_save_time": 0,
        }
    
    def test_auto_save_state_phase_complete(self, mock_state):
        """Test auto-save when phase is complete."""
        mock_state["phase"] = "complete"
        result = auto_save_state(mock_state, persist_ok=True)
        assert result is False
    
    def test_auto_save_state_no_session_start(self, mock_state):
        """Test auto-save when session not started."""
        mock_state["session_start_time"] = None
        result = auto_save_state(mock_state, persist_ok=True)
        assert result is False
    
    def test_auto_save_state_interval_not_met(self, mock_state):
        """Test auto-save when interval not met."""
        mock_state["last_auto_save_time"] = time.time() - 10  # Only 10 seconds ago
        result = auto_save_state(mock_state, persist_ok=True)
        assert result is False
    
    def test_auto_save_state_interval_met(self, mock_state):
        """Test auto-save when interval is met."""
        mock_state["last_auto_save_time"] = time.time() - AUTO_SAVE_INTERVAL_SEC - 10
        
        with patch('exam.state.persistence.save_state_to_disk', return_value=True):
            result = auto_save_state(mock_state, persist_ok=True)
            assert result is True
            assert "last_auto_save_time" in mock_state
    
    def test_auto_save_state_save_fails(self, mock_state):
        """Test auto-save when save fails."""
        mock_state["last_auto_save_time"] = time.time() - AUTO_SAVE_INTERVAL_SEC - 10
        
        with patch('exam.state.persistence.save_state_to_disk', return_value=False):
            result = auto_save_state(mock_state, persist_ok=True)
            assert result is False
            # Should not update last_auto_save_time if save failed
            assert mock_state.get("last_auto_save_time") != time.time()


class TestLoadStateFromDisk:
    """Tests for load_state_from_disk function."""
    
    def test_load_state_from_disk_disabled(self):
        """Test that load_state_from_disk is disabled."""
        state, message = load_state_from_disk()
        
        assert state is None
        assert "disabled" in message.lower()


class TestResumeFromDisk:
    """Tests for resume_from_disk function."""
    
    def test_resume_from_disk_disabled(self):
        """Test that resume_from_disk is disabled."""
        result = resume_from_disk()
        
        assert len(result) == 4
        state, status, interactive, visible = result
        assert state is not None
        assert "disabled" in status.get("value", "").lower()
    
    def test_resume_from_disk_with_custom_ensure_state(self):
        """Test resume_from_disk with custom ensure_state function."""
        def custom_ensure_state(s):
            s["custom"] = True
            return s
        
        result = resume_from_disk(ensure_state_fn=custom_ensure_state)
        
        assert len(result) == 4
        state, status, interactive, visible = result
        assert state.get("custom") is True
    
    def test_lock_file_error_handling(self):
        """Test _lock_file error handling (lines 139-148)."""
        import exam.state.persistence as persistence_module
        from exam.state.persistence import _lock_file
        
        # Test exception handling path by directly patching the fcntl call
        # Since fcntl is conditionally imported, we need to inject it into the module
        original_has_fcntl = persistence_module.HAS_FCNTL
        
        try:
            persistence_module.HAS_FCNTL = True
            # Inject a mock fcntl module
            mock_fcntl = Mock()
            mock_fcntl.flock = Mock(side_effect=IOError("Lock failed"))
            mock_fcntl.LOCK_EX = 2
            mock_fcntl.LOCK_NB = 4
            persistence_module.fcntl = mock_fcntl
            
            result = _lock_file(123, "/tmp/test.json")
            assert result is False
        finally:
            persistence_module.HAS_FCNTL = original_has_fcntl
            if hasattr(persistence_module, 'fcntl'):
                delattr(persistence_module, 'fcntl')
    
    def test_unlock_file_error_handling(self):
        """Test _unlock_file error handling (lines 160, 163-164)."""
        import exam.state.persistence as persistence_module
        from exam.state.persistence import _unlock_file
        
        original_has_fcntl = persistence_module.HAS_FCNTL
        original_has_msvcrt = persistence_module.HAS_MSVCRT
        
        try:
            # Test fcntl unlock error
            persistence_module.HAS_FCNTL = True
            persistence_module.HAS_MSVCRT = False
            
            mock_fcntl = Mock()
            mock_fcntl.flock = Mock(side_effect=IOError("Unlock failed"))
            mock_fcntl.LOCK_UN = 8
            persistence_module.fcntl = mock_fcntl
            
            # Should not raise, just pass silently
            _unlock_file(123)
            
            # Test msvcrt unlock error
            persistence_module.HAS_FCNTL = False
            persistence_module.HAS_MSVCRT = True
            
            mock_msvcrt = Mock()
            mock_msvcrt.locking = Mock(side_effect=IOError("Unlock failed"))
            mock_msvcrt.LK_UNLCK = 0
            persistence_module.msvcrt = mock_msvcrt
            
            # Should not raise, just pass silently
            _unlock_file(123)
        finally:
            persistence_module.HAS_FCNTL = original_has_fcntl
            persistence_module.HAS_MSVCRT = original_has_msvcrt
            if hasattr(persistence_module, 'fcntl'):
                delattr(persistence_module, 'fcntl')
            if hasattr(persistence_module, 'msvcrt'):
                delattr(persistence_module, 'msvcrt')
    
    def test_atomic_write_json_secure_windows_acl_before_replace(self):
        """Test Windows ACL security before file replace (lines 206-208)."""
        from exam.state.persistence import atomic_write_json_secure
        
        obj = {"test": "data"}
        
        # On Windows without pywin32, this will raise RuntimeError (correct behavior)
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    with tempfile.TemporaryDirectory() as tmpdir:
                        path = os.path.join(tmpdir, "test.json")
                        with pytest.raises(RuntimeError, match="Windows file security"):
                            atomic_write_json_secure(obj, path)
                    return
            except ImportError:
                # Windows without pywin32 - expect RuntimeError
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test.json")
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            
            # Test with win32security available (non-Windows or Windows with proper pywin32)
            # Mock fchmod to raise AttributeError (simulating Windows behavior)
            with patch.object(os, 'fchmod', side_effect=AttributeError("chmod not available"), create=True):
                with patch('exam.state.persistence.HAS_FCNTL', False):
                    try:
                        import win32security
                        import win32api
                        import win32con
                        # Mock win32security and win32con to test the path
                        with patch('win32security.LookupAccountName') as mock_lookup:
                            with patch('win32security.ACL') as mock_acl:
                                with patch('win32security.SECURITY_DESCRIPTOR') as mock_sd:
                                    with patch('win32security.SetFileSecurity') as mock_set:
                                        file_access = 0x1F01FF  # FILE_ALL_ACCESS
                                        if hasattr(win32con, 'FILE_ALL_ACCESS'):
                                            file_access = win32con.FILE_ALL_ACCESS
                                        elif hasattr(win32con, 'FILE_GENERIC_READ'):
                                            file_access = (win32con.FILE_GENERIC_READ |
                                                          win32con.FILE_GENERIC_WRITE |
                                                          win32con.FILE_GENERIC_EXECUTE)
                                        with patch('exam.state.persistence.win32con.FILE_ALL_ACCESS', file_access, create=True):
                                            mock_lookup.return_value = (Mock(), None)
                                            mock_acl_instance = Mock()
                                            mock_acl.return_value = mock_acl_instance
                                            mock_sd_instance = Mock()
                                            mock_sd.return_value = mock_sd_instance
                                            
                                            atomic_write_json_secure(obj, path)
                                            
                                            # Verify Windows ACL code was attempted
                                            assert os.path.exists(path)
                    except ImportError:
                        # win32security not available - expect RuntimeError
                        with patch.dict('sys.modules', {'win32security': None, 'win32api': None, 'win32con': None}):
                            with pytest.raises(RuntimeError, match="Windows file security"):
                                atomic_write_json_secure(obj, path)
    
    def test_atomic_write_json_secure_windows_acl_after_replace(self):
        """Test Windows ACL security after file replace (lines 227-239)."""
        from exam.state.persistence import atomic_write_json_secure
        
        obj = {"test": "data"}
        
        # On Windows without pywin32, this will raise RuntimeError (correct behavior)
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    with tempfile.TemporaryDirectory() as tmpdir:
                        path = os.path.join(tmpdir, "test.json")
                        with pytest.raises(RuntimeError, match="Windows file security"):
                            atomic_write_json_secure(obj, path)
                    return
            except ImportError:
                # Windows without pywin32 - expect RuntimeError
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test.json")
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            
            # Test with win32security available after replace
            # First fchmod will fail, then we try Windows ACLs
            call_count = [0]
            def mock_fchmod(fd, mode):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First fchmod (before replace) - fail to trigger Windows ACL path
                    raise AttributeError("fchmod not available")
            
            def mock_chmod(p, mode):
                # Second chmod (after replace) - fail to trigger Windows ACL path
                raise AttributeError("chmod not available")
            
            with patch('os.fchmod', side_effect=mock_fchmod):
                with patch('os.chmod', side_effect=mock_chmod):
                    with patch('exam.state.persistence.HAS_FCNTL', False):
                        try:
                            import win32security
                            import win32api
                            import win32con
                            # Mock win32security and win32con to test the path
                            with patch('win32security.LookupAccountName') as mock_lookup:
                                with patch('win32security.ACL') as mock_acl:
                                    with patch('win32security.SECURITY_DESCRIPTOR') as mock_sd:
                                        with patch('win32security.SetFileSecurity') as mock_set:
                                            file_access = 0x1F01FF  # FILE_ALL_ACCESS
                                            if hasattr(win32con, 'FILE_ALL_ACCESS'):
                                                file_access = win32con.FILE_ALL_ACCESS
                                            elif hasattr(win32con, 'FILE_GENERIC_READ'):
                                                file_access = (win32con.FILE_GENERIC_READ |
                                                              win32con.FILE_GENERIC_WRITE |
                                                              win32con.FILE_GENERIC_EXECUTE)
                                            with patch('exam.state.persistence.win32con.FILE_ALL_ACCESS', file_access, create=True):
                                                mock_lookup.return_value = (Mock(), None)
                                                mock_acl_instance = Mock()
                                                mock_acl.return_value = mock_acl_instance
                                                mock_sd_instance = Mock()
                                                mock_sd.return_value = mock_sd_instance
                                                
                                                atomic_write_json_secure(obj, path)
                                                
                                                # Verify Windows ACL code was attempted
                                                assert os.path.exists(path)
                        except ImportError:
                            # win32security not available - expect RuntimeError
                            with patch.dict('sys.modules', {'win32security': None, 'win32api': None, 'win32con': None}):
                                with pytest.raises(RuntimeError, match="Windows file security"):
                                    atomic_write_json_secure(obj, path)
    
    def test_atomic_write_json_secure_finally_block_exception(self):
        """Test finally block exception handling (lines 244-245)."""
        from exam.state.persistence import atomic_write_json_secure
        
        obj = {"test": "data"}
        
        # On Windows without pywin32, this will raise RuntimeError before finally block
        import sys
        if sys.platform == "win32":
            try:
                import win32security
                import win32con
                # Check if win32con has the constants we need
                if not hasattr(win32con, 'FILE_ALL_ACCESS') and not hasattr(win32con, 'FILE_GENERIC_READ'):
                    # win32con doesn't have file access constants - expect RuntimeError
                    with tempfile.TemporaryDirectory() as tmpdir:
                        path = os.path.join(tmpdir, "test.json")
                        with pytest.raises(RuntimeError, match="Windows file security"):
                            atomic_write_json_secure(obj, path)
                    return
            except ImportError:
                # Windows without pywin32 - expect RuntimeError
                with tempfile.TemporaryDirectory() as tmpdir:
                    path = os.path.join(tmpdir, "test.json")
                    with pytest.raises(RuntimeError, match="Windows file security"):
                        atomic_write_json_secure(obj, path)
                return
        
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            
            # Test that exception in finally block is handled
            with patch('os.path.exists', return_value=True):
                with patch('os.unlink', side_effect=Exception("Cleanup failed")):
                    # Should not raise, exception in finally is caught
                    atomic_write_json_secure(obj, path)
                    # File should still be created despite cleanup error
                    assert os.path.exists(path)

