"""
Shared utilities for VivaAI Secure Exam Proctoring System.

This package contains common functions used by multiple apps (exam.ipynb, dash.ipynb, prof.ipynb).
Functions used by only one app have been moved to app-specific folders (exam/, dash/, prof/).
"""

from shared.cryptography import decrypt_bytes
from shared.url_encoding import (
    deobfuscate_config_string,
    decode_config_from_url,
)
from shared.file_utils import _lock_file, _unlock_file, _user_dir
from shared.pdf_processing import (
    _convert_dropbox_url,
    _download_pdf_from_url,
    _load_pdf_from_bytes,
    _chunk_text,
    _validate_context,
)
from shared.config_parsing import (
    parse_professor_link_and_setup,
    validate_config_params,
    parse_passphrase_from_url,
)

__all__ = [
    # Cryptography (only decrypt_bytes remains - encrypt_bytes moved to exam/)
    "decrypt_bytes",
    # URL encoding (only decode functions remain - encode functions moved to prof/)
    "deobfuscate_config_string",
    "decode_config_from_url",
    # File utilities (only shared functions remain - session functions moved to exam/)
    "_lock_file",
    "_unlock_file",
    "_user_dir",
    # PDF processing (used by exam and prof)
    "_convert_dropbox_url",
    "_download_pdf_from_url",
    "_load_pdf_from_bytes",
    "_chunk_text",
    "_validate_context",
    # Config parsing (used by exam and dash)
    "parse_professor_link_and_setup",
    "validate_config_params",
    "parse_passphrase_from_url",
]
