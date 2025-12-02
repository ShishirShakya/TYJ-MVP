"""
Platform abstraction for OS-specific operations.

This module provides a platform abstraction layer to improve Principle #6
(Portability Across All Clients) while preserving wiring through dependency injection.
"""

from typing import Protocol, Optional
import os
import tempfile
import socket


class PlatformProvider(Protocol):
    """
    Protocol for platform providers.
    
    Allows both real and mock implementations to be used interchangeably.
    """
    
    def get_temp_dir(self) -> str:
        """Get temporary directory path."""
        ...
    
    def get_hostname(self) -> str:
        """Get hostname."""
        ...
    
    def join_path(self, *parts: str) -> str:
        """Join path components."""
        ...
    
    def path_exists(self, path: str) -> bool:
        """Check if path exists."""
        ...
    
    def get_file_size(self, path: str) -> int:
        """Get file size in bytes."""
        ...
    
    def get_file_mtime(self, path: str) -> float:
        """Get file modification time."""
        ...


class RealPlatformProvider:
    """
    Real platform provider that uses system operations.
    
    This is the default implementation for production use.
    """
    
    def get_temp_dir(self) -> str:
        """Get temporary directory path."""
        return tempfile.gettempdir()
    
    def get_hostname(self) -> str:
        """Get hostname."""
        try:
            return socket.gethostname()
        except Exception:
            return "UNKNOWN"
    
    def join_path(self, *parts: str) -> str:
        """Join path components."""
        return os.path.join(*parts)
    
    def path_exists(self, path: str) -> bool:
        """Check if path exists."""
        return os.path.exists(path)
    
    def get_file_size(self, path: str) -> int:
        """Get file size in bytes."""
        return os.path.getsize(path)
    
    def get_file_mtime(self, path: str) -> float:
        """Get file modification time."""
        return os.path.getmtime(path)


class MockPlatformProvider:
    """
    Mock platform provider for testing.
    
    Allows setting fixed values for deterministic testing.
    """
    
    def __init__(
        self,
        temp_dir: str = "/tmp",
        hostname: str = "test-host"
    ):
        """
        Initialize mock platform provider.
        
        Args:
            temp_dir: Mock temporary directory
            hostname: Mock hostname
        """
        self._temp_dir = temp_dir
        self._hostname = hostname
        self._files: dict[str, dict] = {}  # path -> {size, mtime}
    
    def get_temp_dir(self) -> str:
        """Get mock temporary directory."""
        return self._temp_dir
    
    def get_hostname(self) -> str:
        """Get mock hostname."""
        return self._hostname
    
    def join_path(self, *parts: str) -> str:
        """
        Join path components (mock).
        
        PORTABILITY: Uses os.path.join() for cross-platform compatibility (Principle #6).
        """
        return os.path.join(*parts)
    
    def path_exists(self, path: str) -> bool:
        """Check if path exists (mock)."""
        return path in self._files
    
    def get_file_size(self, path: str) -> int:
        """Get file size (mock)."""
        return self._files.get(path, {}).get("size", 0)
    
    def get_file_mtime(self, path: str) -> float:
        """Get file modification time (mock)."""
        return self._files.get(path, {}).get("mtime", 0.0)
    
    def add_file(self, path: str, size: int = 0, mtime: float = 1000.0) -> None:
        """
        Add a mock file.
        
        Args:
            path: File path
            size: File size in bytes
            mtime: Modification time
        """
        self._files[path] = {"size": size, "mtime": mtime}


# Global default platform provider
_default_platform_provider: Optional[PlatformProvider] = None


def get_default_platform_provider() -> PlatformProvider:
    """
    Get the default platform provider instance.
    
    Returns:
        PlatformProvider instance (RealPlatformProvider by default)
    """
    global _default_platform_provider
    if _default_platform_provider is None:
        _default_platform_provider = RealPlatformProvider()
    return _default_platform_provider


def set_default_platform_provider(provider: PlatformProvider) -> None:
    """
    Set the default platform provider (mainly for testing).
    
    Args:
        provider: PlatformProvider instance to use as default
    """
    global _default_platform_provider
    _default_platform_provider = provider


def create_platform_provider(use_mock: bool = False) -> PlatformProvider:
    """
    Create a platform provider instance.
    
    Args:
        use_mock: If True, create MockPlatformProvider; otherwise RealPlatformProvider
        
    Returns:
        PlatformProvider instance
    """
    if use_mock:
        return MockPlatformProvider()
    return RealPlatformProvider()

