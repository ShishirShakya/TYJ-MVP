"""
URL generation utilities for prof.ipynb - URL encoding and generation.

This module contains URL generation functions used only by prof.ipynb.
Functions used by multiple apps are in shared/.
"""

import base64
import hashlib
from urllib.parse import quote_plus
# Import centralized security configuration (SSOT - Principle #2)
from shared.security_config import get_hmac_secret

# SECURITY: Get HMAC_SECRET from centralized security config (SSOT - Principle #2)
HMAC_SECRET = get_hmac_secret(required=True)


def _get_obfuscation_key() -> bytes:
    """
    Generate a key for URL obfuscation from HMAC_SECRET.
    Returns a 32-byte key suitable for XOR cipher.
    """
    # Use HMAC_SECRET to derive a consistent key
    key_material = HMAC_SECRET.encode('utf-8')
    # Generate a 32-byte key using SHA256
    key = hashlib.sha256(key_material).digest()
    return key


def obfuscate_config_string(config_str: str) -> str:
    """
    Obfuscate/encrypt the config string using XOR cipher + base64 encoding.
    This hides sensitive information like passphrases and makes URLs non-readable.
    
    Args:
        config_str: Plain text config string to obfuscate
        
    Returns:
        Obfuscated config string (base64 encoded)
    """
    try:
        key = _get_obfuscation_key()
        # Convert config string to bytes
        data = config_str.encode('utf-8')
        
        # XOR cipher: XOR each byte with corresponding key byte (cyclically)
        encrypted = bytearray()
        for i, byte in enumerate(data):
            encrypted.append(byte ^ key[i % len(key)])
        
        # Base64 encode for URL-safe string
        obfuscated = base64.urlsafe_b64encode(bytes(encrypted)).decode('utf-8').rstrip('=')
        return obfuscated
    except Exception as e:
        # If obfuscation fails, return original (for backward compatibility)
        return config_str


def generate_config_string(
    course_id: str,
    exam_id: str,
    num_questions: int,
    min_followups: int,
    max_followups: int,
    section_id: str,
    decryption: str,
    start_date: str = "",
    end_date: str = "",
    time_per_question: int = 60
) -> str:
    """
    Generate plain text config string from parameters.
    
    ALWAYS generates 10-part format (required for time_per_question support):
    CourseID/ExamID/NumQuestions/MinFollowups/MaxFollowups/TimePerQuestion/SectionID/DecryptionPassphrase/StartDate/EndDate
    
    Dates should be in ISO format: YYYY-MM-DDTHH:MM:SS or empty string if not set
    
    Args:
        course_id: Course identifier
        exam_id: Exam identifier
        num_questions: Number of questions
        min_followups: Minimum follow-up questions
        max_followups: Maximum follow-up questions
        section_id: Section identifier
        decryption: Decryption passphrase
        start_date: Start date in ISO format (optional)
        end_date: End date in ISO format (optional)
        time_per_question: Time per question in seconds (optional, default 60)
        
    Returns:
        Config string in 10-part format: CourseID/ExamID/NumQuestions/... (always 10 parts)
        
    Raises:
        ValueError: If the generated config string does not have exactly 10 parts
    """
    # Use defaults if empty
    course_id = course_id.strip() if course_id.strip() else "UNKNOWN"
    exam_id = exam_id.strip() if exam_id.strip() else "UNKNOWN"
    num_questions = int(num_questions) if num_questions is not None else 1
    min_followups = int(min_followups) if min_followups is not None else 0
    max_followups = int(max_followups) if max_followups is not None else min_followups  # Default to min if not provided
    time_per_question = int(time_per_question) if time_per_question is not None else 60
    section_id = section_id.strip() if section_id and section_id.strip() else "UNKNOWN"
    decryption = decryption.strip() if (decryption and decryption.strip()) else ""
    start_date = start_date.strip() if start_date and start_date.strip() else ""
    end_date = end_date.strip() if end_date and end_date.strip() else ""
    
    # ALWAYS generate 10-part format (required for time_per_question parsing)
    # Format: CourseID/ExamID/NumQuestions/MinFollowups/MaxFollowups/TimePerQuestion/SectionID/Decryption/StartDate/EndDate
    config_str = f"{course_id}/{exam_id}/{num_questions}/{min_followups}/{max_followups}/{time_per_question}/{section_id}/{decryption}/{start_date}/{end_date}"
    
    # Validate that we have exactly 10 parts (safety check)
    parts = config_str.split("/")
    if len(parts) != 10:
        raise ValueError(f"Config string must have exactly 10 parts, got {len(parts)}: {config_str}")
    
    return config_str


def encode_config_to_url(
    base_url: str,
    pdf_url: str,
    course_id: str,
    exam_id: str,
    num_questions: int,
    min_followups: int,
    max_followups: int,
    section_id: str,
    decryption: str,
    start_date: str = "",
    end_date: str = "",
    time_per_question: int = 60
) -> str:
    """
    Encode all parameters into a URL with query parameters.
    Format: base_url?pdf_url={pdf_url}&config={config_string}
    
    DEPRECATED: This function generates the old obfuscated format.
    Use encode_config_to_url_v2() for the new readable format with individual query parameters.
    
    Args:
        base_url: Base URL for the exam interface
        pdf_url: URL to the PDF file
        course_id: Course identifier
        exam_id: Exam identifier
        num_questions: Number of questions
        min_followups: Minimum follow-up questions
        max_followups: Maximum follow-up questions
        section_id: Section identifier
        decryption: Decryption passphrase
        start_date: Start date in ISO format (optional)
        end_date: End date in ISO format (optional)
        time_per_question: Time per question in seconds (optional, default 60)
        
    Returns:
        Complete URL with encoded parameters (old format)
    """
    config_str = generate_config_string(
        course_id, exam_id, num_questions, min_followups, max_followups,
        section_id, decryption, start_date, end_date, time_per_question
    )
    
    # Obfuscate the config string to hide sensitive information
    obfuscated_config = obfuscate_config_string(config_str)
    
    # URL encode the parameters
    encoded_pdf_url = quote_plus(pdf_url)
    encoded_config = quote_plus(obfuscated_config)
    
    # Build URL
    url = f"{base_url}?pdf_url={encoded_pdf_url}&config={encoded_config}"
    return url


def encode_config_to_url_v2(
    base_url: str,
    pdf_url: str,
    course_id: str,
    exam_id: str,
    num_questions: int,
    min_followups: int,
    max_followups: int,
    section_id: str,
    decryption: str,
    start_date: str = "",
    end_date: str = "",
    time_per_question: int = 60
) -> str:
    """
    Encode all parameters into a URL with individual query parameters (new readable format).
    Format: base_url?pdf_url=...&course_id=...&exam_id=...&passphrase={obfuscated}&...
    
    This format is more readable and easier to navigate for professors teaching multiple courses.
    Only the passphrase is obfuscated for security; other parameters are plaintext.
    
    Args:
        base_url: Base URL for the exam interface
        pdf_url: URL to the PDF file
        course_id: Course identifier
        exam_id: Exam identifier
        num_questions: Number of questions
        min_followups: Minimum follow-up questions
        max_followups: Maximum follow-up questions
        section_id: Section identifier
        decryption: Decryption passphrase (will be obfuscated)
        start_date: Start date in ISO format (optional)
        end_date: End date in ISO format (optional)
        time_per_question: Time per question in seconds (optional, default 60)
        
    Returns:
        Complete URL with individual query parameters (new format)
    """
    # Normalize and validate inputs
    course_id = course_id.strip() if course_id and course_id.strip() else "UNKNOWN"
    exam_id = exam_id.strip() if exam_id and exam_id.strip() else "UNKNOWN"
    section_id = section_id.strip() if section_id and section_id.strip() else "UNKNOWN"
    num_questions = int(num_questions) if num_questions is not None else 1
    min_followups = int(min_followups) if min_followups is not None else 0
    max_followups = int(max_followups) if max_followups is not None else min_followups
    time_per_question = int(time_per_question) if time_per_question is not None else 60
    decryption = decryption.strip() if decryption and decryption.strip() else ""
    start_date = start_date.strip() if start_date and start_date.strip() else ""
    end_date = end_date.strip() if end_date and end_date.strip() else ""
    
    # Obfuscate only the passphrase (security)
    obfuscated_passphrase = obfuscate_config_string(decryption)
    
    # URL encode all parameters (handles spaces, special chars, dates automatically)
    encoded_pdf_url = quote_plus(pdf_url)
    encoded_course_id = quote_plus(course_id)
    encoded_exam_id = quote_plus(exam_id)
    encoded_section_id = quote_plus(section_id)
    encoded_passphrase = quote_plus(obfuscated_passphrase)
    encoded_start_date = quote_plus(start_date)
    encoded_end_date = quote_plus(end_date)
    
    # Build URL with individual query parameters
    url = (
        f"{base_url}?pdf_url={encoded_pdf_url}"
        f"&course_id={encoded_course_id}"
        f"&exam_id={encoded_exam_id}"
        f"&num_questions={num_questions}"
        f"&min_followups={min_followups}"
        f"&max_followups={max_followups}"
        f"&time_per_question={time_per_question}"
        f"&section_id={encoded_section_id}"
        f"&passphrase={encoded_passphrase}"
    )
    
    # Add dates only if provided (to keep URLs shorter when not needed)
    if start_date:
        url += f"&start_date={encoded_start_date}"
    if end_date:
        url += f"&end_date={encoded_end_date}"
    
    return url

