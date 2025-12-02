"""
File utilities for cross-platform file locking and session management.

This module provides file locking functions that work on both Windows and Unix/Linux,
as well as session directory management functions.
"""

import os
import pathlib

# File locking support (cross-platform)
try:
    if os.name == 'nt':  # Windows
        import msvcrt
        def _lock_file(fd):
            """
            Lock file on Windows using msvcrt.
            
            Args:
                fd: File descriptor to lock
            """
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
            except Exception:
                pass
        
        def _unlock_file(fd):
            """
            Unlock file on Windows using msvcrt.
            
            Args:
                fd: File descriptor to unlock
            """
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
    else:  # Unix/Linux
        import fcntl
        def _lock_file(fd):
            """
            Lock file on Unix/Linux using fcntl.
            
            Args:
                fd: File descriptor to lock
            """
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
            except Exception:
                pass
        
        def _unlock_file(fd):
            """
            Unlock file on Unix/Linux using fcntl.
            
            Args:
                fd: File descriptor to unlock
            """
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
    _HAS_FILE_LOCKING = True
except (ImportError, AttributeError):
    def _lock_file(fd):
        """
        Fallback: No-op if file locking is not available.
        
        Args:
            fd: File descriptor (ignored)
        """
        pass
    
    def _unlock_file(fd):
        """
        Fallback: No-op if file locking is not available.
        
        Args:
            fd: File descriptor (ignored)
        """
        pass
    _HAS_FILE_LOCKING = False


def _user_dir():
    """
    Get or create user directory for VivaAI configuration files.
    
    Returns:
        Path object to ~/.vivaai directory
    """
    import pathlib
    d = pathlib.Path.home() / ".vivaai"
    d.mkdir(exist_ok=True)
    return d

