"""
URL encoding and decoding utilities for professor links.

This module provides functions for encoding and decoding exam configuration
parameters in URLs, including obfuscation for security.
"""

import base64
import hashlib
from urllib.parse import unquote_plus, urlparse, parse_qs
from typing import Dict, Any, Optional
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()


def _get_hmac_secret() -> str:
    """
    Get HMAC secret from environment with lazy initialization.
    
    CONFIGURATION & SECRETS DISCIPLINE: Lazy initialization ensures secret is
    validated when actually needed, not at module import time (Principle #23).
    
    Returns:
        HMAC secret string
        
    Raises:
        ValueError: If VIVA_HMAC_SECRET is not set
    """
    secret = os.getenv("VIVA_HMAC_SECRET")
    if not secret:
        raise ValueError(
            "VIVA_HMAC_SECRET environment variable must be set. "
            "This is required for URL obfuscation. Set it in your .env file or environment variables."
        )
    return secret


def _get_obfuscation_key() -> bytes:
    """
    Generate a key for URL obfuscation from HMAC_SECRET.
    Returns a 32-byte key suitable for XOR cipher.
    """
    # Use HMAC_SECRET to derive a consistent key (lazy initialization)
    key_material = _get_hmac_secret().encode('utf-8')
    # Generate a 32-byte key using SHA256
    key = hashlib.sha256(key_material).digest()
    return key


def deobfuscate_config_string(obfuscated_str: str) -> str:
    """
    Deobfuscate/decrypt the config string.
    Returns the original config string.
    
    Args:
        obfuscated_str: Obfuscated config string to deobfuscate
        
    Returns:
        Original plain text config string
    """
    try:
        key = _get_obfuscation_key()
        # Add padding back to base64 string if needed
        padding = 4 - (len(obfuscated_str) % 4)
        if padding != 4:
            obfuscated_str += '=' * padding
        
        # Base64 decode
        encrypted = base64.urlsafe_b64decode(obfuscated_str.encode('utf-8'))
        
        # XOR decipher: XOR each byte with corresponding key byte (cyclically)
        decrypted = bytearray()
        for i, byte in enumerate(encrypted):
            decrypted.append(byte ^ key[i % len(key)])
        
        return decrypted.decode('utf-8')
    except Exception:
        # If deobfuscation fails, assume it's an old unencrypted format
        return obfuscated_str


def decode_config_from_url(url: str) -> Optional[Dict[str, Any]]:
    """
    Decode parameters from URL query string.
    Returns dict with: pdf_url, course_id, exam_id, num_questions, min_followups,
    max_followups, time_per_question, section_id, decryption, start_date, end_date
    
    Supports both URL formats:
    1. NEW FORMAT (v2): Individual query parameters
       Format: base_url?pdf_url=...&course_id=...&exam_id=...&passphrase={obfuscated}&...
    2. OLD FORMAT (v1): Obfuscated config string
       Format: base_url?pdf_url=...&config={obfuscated_config_string}
       Supports multiple legacy versions (5, 7, 9, 10 parts)
    
    Args:
        url: URL with encoded parameters
        
    Returns:
        Dictionary with decoded parameters, or None if parsing fails
    """
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Extract pdf_url (common to both formats)
        pdf_url = unquote_plus(params.get("pdf_url", [""])[0])
        
        # Check if this is the new format (v2) with individual query parameters
        if "course_id" in params or "passphrase" in params:
            # NEW FORMAT: Individual query parameters
            try:
                course_id = unquote_plus(params.get("course_id", ["UNKNOWN"])[0]) or "UNKNOWN"
                exam_id = unquote_plus(params.get("exam_id", ["UNKNOWN"])[0]) or "UNKNOWN"
                section_id = unquote_plus(params.get("section_id", ["UNKNOWN"])[0]) or "UNKNOWN"
                
                # Parse numeric values with defaults
                # Handle missing or empty parameters safely
                num_questions_val = params.get("num_questions", [""])[0] if params.get("num_questions") else ""
                num_questions = int(num_questions_val) if num_questions_val and num_questions_val.isdigit() else 1
                
                min_followups_val = params.get("min_followups", [""])[0] if params.get("min_followups") else ""
                min_followups = int(min_followups_val) if min_followups_val and min_followups_val.isdigit() else 0
                
                max_followups_val = params.get("max_followups", [""])[0] if params.get("max_followups") else ""
                max_followups = int(max_followups_val) if max_followups_val and max_followups_val.isdigit() else min_followups
                
                time_per_question_val = params.get("time_per_question", [""])[0] if params.get("time_per_question") else ""
                time_per_question = int(time_per_question_val) if time_per_question_val and time_per_question_val.isdigit() else 60
                
                # Extract and deobfuscate passphrase
                obfuscated_passphrase = unquote_plus(params.get("passphrase", [""])[0])
                if obfuscated_passphrase:
                    try:
                        decryption = deobfuscate_config_string(obfuscated_passphrase)
                    except Exception:
                        # If deobfuscation fails, try as plaintext (backward compatibility)
                        decryption = obfuscated_passphrase
                else:
                    decryption = ""
                
                # Extract dates (optional)
                start_date = unquote_plus(params.get("start_date", [""])[0])
                end_date = unquote_plus(params.get("end_date", [""])[0])
                
                return {
                    "pdf_url": pdf_url,
                    "course_id": course_id,
                    "exam_id": exam_id,
                    "num_questions": num_questions,
                    "min_followups": min_followups,
                    "max_followups": max_followups,
                    "time_per_question": time_per_question,
                    "section_id": section_id,
                    "decryption": decryption,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            except Exception:
                # If new format parsing fails, fall back to old format
                pass
        
        # OLD FORMAT: Obfuscated config string
        obfuscated_config = unquote_plus(params.get("config", [""])[0])
        
        if not obfuscated_config:
            return None
        
        # Try to deobfuscate the config string (supports both obfuscated and old unencrypted formats)
        try:
            config_str = deobfuscate_config_string(obfuscated_config)
        except Exception:
            # If deobfuscation fails, assume it's an old unencrypted format
            config_str = obfuscated_config
        
        # Split config string by '/' to get individual values
        parts = config_str.split("/")
        
        # Support old formats: 5 parts (oldest), 7 parts (with dates), 9 parts (with max_followups and section_id), 10 parts (with time_per_question)
        if len(parts) < 5:
            return None
        
        result = {
            "pdf_url": pdf_url,
            "course_id": parts[0] if parts[0] else "UNKNOWN",
            "exam_id": parts[1] if parts[1] else "UNKNOWN",
            "num_questions": int(parts[2]) if parts[2] and parts[2].isdigit() else 1,
            "min_followups": int(parts[3]) if parts[3] and parts[3].isdigit() else 0,
        }
        
        # Handle different format versions
        if len(parts) == 5:
            # Old format: CourseID/ExamID/NumQuestions/MinFollowups/Decryption
            result["max_followups"] = result["min_followups"]  # Use min as max for backward compatibility
            result["time_per_question"] = 60  # Default to 60 seconds for old format
            result["section_id"] = "UNKNOWN"
            result["decryption"] = parts[4] if parts[4] else ""
            result["start_date"] = ""
            result["end_date"] = ""
        elif len(parts) == 7:
            # Format with dates: CourseID/ExamID/NumQuestions/MinFollowups/Decryption/StartDate/EndDate
            result["max_followups"] = result["min_followups"]  # Use min as max for backward compatibility
            result["time_per_question"] = 60  # Default to 60 seconds for old format
            result["section_id"] = "UNKNOWN"
            result["decryption"] = parts[4] if parts[4] else ""
            result["start_date"] = parts[5] if parts[5] else ""
            result["end_date"] = parts[6] if parts[6] else ""
        elif len(parts) == 9:
            # Format: CourseID/ExamID/NumQuestions/MinFollowups/MaxFollowups/SectionID/Decryption/StartDate/EndDate
            result["max_followups"] = int(parts[4]) if parts[4] and parts[4].isdigit() else result["min_followups"]
            result["time_per_question"] = 60  # Default to 60 seconds for 9-part format (no time_per_question)
            result["section_id"] = parts[5] if parts[5] else "UNKNOWN"
            result["decryption"] = parts[6] if parts[6] else ""
            result["start_date"] = parts[7] if len(parts) > 7 and parts[7] else ""
            result["end_date"] = parts[8] if len(parts) > 8 and parts[8] else ""
        elif len(parts) == 10:
            # New format with time_per_question: CourseID/ExamID/NumQuestions/MinFollowups/MaxFollowups/TimePerQuestion/SectionID/Decryption/StartDate/EndDate
            result["max_followups"] = int(parts[4]) if parts[4] and parts[4].isdigit() else result["min_followups"]
            # Extract time_per_question from URL - validate it's present and numeric
            if parts[5] and parts[5].isdigit():
                result["time_per_question"] = int(parts[5])
            else:
                # If time_per_question is missing or invalid, default to 60 but log a warning
                result["time_per_question"] = 60
                # Log warning for debugging (uncomment if logging is available)
                # import logging
                # logging.warning(f"time_per_question missing/invalid in URL, defaulting to 60. parts[5]={parts[5]}")
            result["section_id"] = parts[6] if parts[6] else "UNKNOWN"
            result["decryption"] = parts[7] if parts[7] else ""
            result["start_date"] = parts[8] if len(parts) > 8 and parts[8] else ""
            result["end_date"] = parts[9] if len(parts) > 9 and parts[9] else ""
        else:
            return None
        
        return result
    except Exception as e:
        return None

