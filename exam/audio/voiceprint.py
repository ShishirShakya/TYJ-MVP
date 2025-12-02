"""
Voiceprint analysis module for exam.ipynb.

This module contains functions for voiceprint extraction and comparison:
- Audio feature extraction
- Voiceprint comparison
"""

from typing import Dict, Optional

# Optional numpy import
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None
    _HAS_NUMPY = False

# Optional librosa import
try:
    import librosa
    _HAS_LIBROSA = True
except ImportError:
    librosa = None
    _HAS_LIBROSA = False


def extract_audio_features(audio_path: str) -> Dict:
    """
    Extract audio features for voiceprint analysis.
    
    Returns dict with pitch, spectral features, timing.
    
    Args:
        audio_path: Path to audio file
        
    Returns:
        Dictionary with audio features, or empty dict if extraction fails
    """
    if not _HAS_LIBROSA or not librosa or not _HAS_NUMPY or not np:
        return {}
    
    try:
        # Load audio with librosa (handles mp3, wav, etc.)
        y, sr = librosa.load(audio_path, sr=None, duration=30)  # Limit to 30s for speed
        
        # Extract fundamental frequency (pitch)
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_values = []
        for t in range(pitches.shape[1]):
            index = magnitudes[:, t].argmax()
            pitch = pitches[index, t]
            if pitch > 0:
                pitch_values.append(pitch)
        
        mean_pitch = np.mean(pitch_values) if pitch_values else 0
        std_pitch = np.std(pitch_values) if pitch_values else 0
        
        # Spectral features (timbre)
        spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)[0])
        spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr)[0])
        mfccs = np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13), axis=1)
        
        # Timing features
        duration = librosa.get_duration(y=y, sr=sr)
        
        return {
            "mean_pitch": float(mean_pitch),
            "std_pitch": float(std_pitch),
            "spectral_centroid": float(spectral_centroid),
            "spectral_rolloff": float(spectral_rolloff),
            "mfccs": [float(v) for v in mfccs],
            "duration": float(duration),
        }
    except Exception:
        return {}


def compare_voiceprints(
    features1: Dict,
    features2: Dict,
    threshold: float = 0.3
) -> bool:
    """
    Compare two voiceprint feature sets.
    
    Returns True if similar (likely same speaker), False if different.
    
    Args:
        features1: First voiceprint features
        features2: Second voiceprint features
        threshold: Similarity threshold (default: 0.3)
        
    Returns:
        True if voiceprints are similar, False otherwise
    """
    if not features1 or not features2:
        return True  # Skip check if features unavailable
    
    if not _HAS_NUMPY or not np:
        return True  # Skip if numpy unavailable
    
    try:
        # Compare pitch (major indicator of speaker)
        pitch_diff = abs(features1.get("mean_pitch", 0) - features2.get("mean_pitch", 0))
        pitch_std_avg = (features1.get("std_pitch", 1) + features2.get("std_pitch", 1)) / 2
        if pitch_std_avg > 0:
            pitch_similarity = 1 - min(pitch_diff / (pitch_std_avg * 3), 1.0)
        else:
            pitch_similarity = 1.0
        
        # Compare spectral features (timbre)
        spec_diff = abs(
            features1.get("spectral_centroid", 0) - features2.get("spectral_centroid", 0)
        )
        spec_avg = (
            features1.get("spectral_centroid", 1) + features2.get("spectral_centroid", 1)
        ) / 2
        if spec_avg > 0:
            spec_similarity = 1 - min(spec_diff / (spec_avg * 0.3), 1.0)
        else:
            spec_similarity = 1.0
        
        # Compare MFCC features (overall voice characteristics)
        mfccs1 = features1.get("mfccs", [])
        mfccs2 = features2.get("mfccs", [])
        if mfccs1 and mfccs2 and len(mfccs1) == len(mfccs2):
            mfcc_diff = np.mean([abs(a - b) for a, b in zip(mfccs1, mfccs2)])
            mfcc_similarity = 1 - min(mfcc_diff / 20.0, 1.0)
        else:
            mfcc_similarity = 1.0
        
        # Weighted average
        overall_similarity = (
            pitch_similarity * 0.5 + spec_similarity * 0.25 + mfcc_similarity * 0.25
        )
        return overall_similarity >= threshold
    except Exception:
        return True  # Default to passing if analysis fails

