"""
Proctoring configuration constants.

Configuration values are loaded from environment variables via secure_config,
with defaults matching the original hardcoded values for backward compatibility.
"""

# Import secure configuration management (SSOT - Principle #2)
from shared.config.secure_config import get_proctor_config

# Get proctoring config from environment variables (with defaults)
_proctor_config = get_proctor_config()

# Proctoring Rules (thresholds for detection)
# Values come from secure_config, defaults match original hardcoded values
PROCTOR_RULES = {
    "yaw_max_deg": _proctor_config["yaw_max_deg"],
    "pitch_max_deg": _proctor_config["pitch_max_deg"],
    "away_min_consec_frames": _proctor_config["away_min_consec_frames"],
    "allow_multi_face": _proctor_config["allow_multi_face"],
}

# Proctoring Configuration (configurable thresholds)
PROCTOR_CONFIG = {
    "away_ratio_threshold": _proctor_config["away_ratio_threshold"],
    "calibration_frames": _proctor_config["calibration_frames"],
    "allow_break_duration": _proctor_config["allow_break_duration"],
}

# Proctoring Flag Rules (thresholds for flagging violations)
# Values come from secure_config via get_proctor_config() (SSOT - Principle #2)
PROCTOR_FLAG_RULES = {
    # Fire a flag each time the student is away for >= this many consecutive frames while answering
    "away_flag_consec_frames": _proctor_config["away_flag_consec_frames"],
    # Fire a flag if we see multiple faces for at least this many consecutive frames while answering
    "multi_face_flag_consec_frames": _proctor_config["multi_face_flag_consec_frames"],
    # Optional: flag if no face for at least this many consecutive frames while answering
    "no_face_flag_consec_frames": _proctor_config["no_face_flag_consec_frames"],
    # Extreme gaze drift threshold (consecutive frames)
    "extreme_gaze_consec_frames": _proctor_config["extreme_gaze_consec_frames"],
}

# Sparse landmark indices for visual hash (subset of MediaPipe face mesh landmarks)
_SPARSE_IDX = [1, 33, 133, 362, 263, 61, 291, 13]

# Head pose landmark indices (MediaPipe face mesh)
_HEADPOSE_IDX = {
    "L_EAR": 234,
    "R_EAR": 454,
    "NOSE": 1,
    "L_EYE": 159,
    "R_EYE": 386,
    "MOUTH": 13,
}

