"""
Multi-face detection functions for video proctoring.
"""

from .config import PROCTOR_FLAG_RULES


def _detect_multi_face(n_faces: int) -> bool:
    """Detect if multiple faces are present."""
    return n_faces >= 2


def _flag_multi_face(st, n_faces: int) -> None:
    """Flag multi-face event if threshold is met."""
    if n_faces >= 2:
        st.multi_face_frames += 1
        if st.answering:
            st.block_multi_face_frames += 1
            st._consec_multi += 1
            if st._consec_multi == PROCTOR_FLAG_RULES["multi_face_flag_consec_frames"]:
                st._flag("MULTI_FACE", {"consec_frames": st._consec_multi})
    else:
        st._consec_multi = 0

