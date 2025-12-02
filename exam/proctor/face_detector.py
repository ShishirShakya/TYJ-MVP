"""
Face detection utilities for video proctoring.
"""

import hashlib
from typing import Optional, Any

# Optional numpy import (handled gracefully if not available)
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False


def _safe_np(img: Any) -> Optional[Any]:
    """Convert image to numpy array safely."""
    if np is None:
        return None
    if isinstance(img, np.ndarray):
        return img
    try:
        from PIL import Image as PILImage
        if isinstance(img, PILImage.Image):
            return np.array(img)
    except Exception:
        pass
    return None


def _hash_landmarks(ctx: Any, pts: Any) -> None:
    """Hash landmarks for visual hash generation."""
    if np is None:
        return
    arr = np.asarray(pts, dtype=np.float32).ravel()
    ctx.update((arr * 1000).astype(np.int32).tobytes())

