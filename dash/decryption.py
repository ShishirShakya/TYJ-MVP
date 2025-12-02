"""
Decryption utilities for dash.ipynb - instructor decryption and OTET management.

This module contains decryption functions used only by dash.ipynb.
Functions used by multiple apps are in shared/.
"""

import os
import json
import base64
import hashlib
import csv
import threading
from typing import Tuple, Optional, Any, Dict
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidTag, InvalidSignature

from shared.cryptography import decrypt_bytes
from shared.file_utils import _lock_file, _unlock_file, _user_dir
from shared.pii_obfuscation import decrypt_receipt_core
from dash.config import logger

# Constants
OTET_LEDGER_PATH = str(_user_dir() / "otet_ledger.csv")

# THREAD-SAFETY: Lock protects OTET ledger operations from race conditions
_otet_ledger_lock = threading.Lock()


# =========================
# OTET ledger management
# =========================

def _check_and_mark_otet(otet_token: str) -> str:
    """
    Check if OTET token has been used before and mark it as seen.
    
    THREAD-SAFE: Protected by lock to prevent race conditions (Principle #20).
    DATA INTEGRITY: Atomic check-and-write prevents duplicate marking (Principle #22).
    
    Args:
        otet_token: The OTET token to check
        
    Returns:
        "MISSING" if token is empty
        "DUPLICATE" if token was already seen
        "FIRST_USE" if token is new
    """
    if not otet_token:
        return "MISSING"
    
    ledger_path = OTET_LEDGER_PATH
    
    # THREAD-SAFETY: Use lock to make check-and-write atomic
    with _otet_ledger_lock:
        is_new = True
        
        try:
            # Check if token exists in ledger
            if os.path.exists(ledger_path):
                with open(ledger_path, "r", encoding="utf-8") as f:
                    _lock_file(f)
                    try:
                        reader = csv.reader(f)
                        for row in reader:
                            if len(row) > 0 and row[0] == otet_token:
                                is_new = False
                                break
                    finally:
                        _unlock_file(f)
            
            # If token is new, mark it as seen (atomic within lock)
            if is_new:
                try:
                    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
                    with open(ledger_path, "a", encoding="utf-8", newline="") as f:
                        _lock_file(f)
                        try:
                            writer = csv.writer(f)
                            writer.writerow([otet_token, datetime.now().isoformat()])
                        finally:
                            _unlock_file(f)
                except Exception as e:
                    # GRACEFUL FAILURE: Log error but don't crash (Principle #16)
                    logger.warning(
                        "otet_ledger_write_failed",
                        _internal_error_type=type(e).__name__,
                        _internal_error_message=str(e)[:100]
                    )
                    # Still return FIRST_USE since check passed
        except Exception as e:
            # GRACEFUL FAILURE: Log error but allow decryption (best-effort)
            logger.warning(
                "otet_ledger_read_failed",
                _internal_error_type=type(e).__name__,
                _internal_error_message=str(e)[:100]
            )
            # If ledger read fails, still allow decryption (best-effort)
            return "FIRST_USE"  # Default to FIRST_USE if we can't check
    
    return "DUPLICATE" if not is_new else "FIRST_USE"


# =========================
# Instructor decryption
# =========================

def instructor_decrypt(
    enc_file: Optional[str],
    passphrase: str,
    logger: Optional[Any] = None,
    require_role_fn: Optional[Any] = None,
    state: Optional[Dict[str, Any]] = None
) -> Tuple[str, str]:
    """
    Decrypt and verify an encrypted exam transcript file.
    
    FERPA COMPLIANCE: Only authorized educational personnel may access student data.
    RBAC check is performed if require_role_fn is provided.
    
    Args:
        enc_file: Path to the encrypted .enc file
        passphrase: Decryption passphrase
        logger: Optional logger for structured logging (if None, no logging)
        require_role_fn: Optional RBAC function to check role (for FERPA compliance)
        state: Optional state dictionary for RBAC (if require_role_fn provided)
        
    Returns:
        (plaintext: str, summary_md: str)
        - plaintext: Decrypted transcript text or error message
        - summary_md: Markdown summary of integrity check results
    """
    # FERPA COMPLIANCE: Check role before accessing student data
    if require_role_fn and state is not None:
        try:
            from shared.ferpa_rbac import UserRole, format_ferpa_block_error
            import uuid
            
            if not require_role_fn(state, UserRole.INSTRUCTOR, "instructor_decrypt"):
                correlation_id = str(uuid.uuid4())
                error_msg = format_ferpa_block_error(correlation_id)
                if logger:
                    logger.warning(
                        "ferpa_access_denied",
                        reason="insufficient_role",
                        correlation_id=correlation_id,
                        operation="instructor_decrypt"
                    )
                return error_msg, ""
        except Exception as e:
            # Don't fail decryption if RBAC check fails (backward compatibility)
            if logger:
                logger.warning(
                    "rbac_check_failed",
                    error=str(e),
                    operation="instructor_decrypt",
                    action="allowing_access_for_backward_compatibility"
                )
    
    if enc_file is None:
        if logger:
            logger.warning("decrypt_no_file", message="No file provided for decryption")
        return "Please upload an .enc file.", ""
    
    try:
        if logger:
            logger.info("decrypt_started", file_path=enc_file, operation="instructor_decrypt")
        
        # RESOURCE MANAGEMENT: Check file size before opening to prevent memory exhaustion
        # Check file size first (before opening file handle)
        try:
            from shared.constants import MAX_FILE_SIZE  # SSOT - Principle #2
            file_size = os.path.getsize(enc_file)
            if file_size > MAX_FILE_SIZE:
                size_mb = file_size / (1024 * 1024)
                max_mb = MAX_FILE_SIZE / (1024 * 1024)
                if logger:
                    logger.warning(
                        "file_too_large",
                        file_path=enc_file,
                        file_size_mb=round(size_mb, 2),
                        max_size_mb=max_mb
                    )
                return f"❌ File too large: {size_mb:.1f}MB (max {max_mb:.0f}MB).", ""
        except (OSError, IOError) as e:
            if logger:
                logger.warning(
                    "file_size_check_failed",
                    file_path=enc_file,
                    _internal_error_type=type(e).__name__,
                    _internal_error_message=str(e)[:100]
                )
            return "❌ Could not access file. Please check the file exists and is readable.", ""
        
        # RESOURCE MANAGEMENT: Use context manager to ensure file handle is closed
        with open(enc_file, "rb") as f:
            data = f.read()
        
        try:
            outer = json.loads(data.decode("utf-8"))
            assert outer.get("magic") == "VIVA2"
        except Exception:
            # Legacy file format (no receipt)
            try:
                pt_legacy_bytes = decrypt_bytes(data, passphrase)
                if logger:
                    logger.info("decrypt_legacy_success", file_path=enc_file, format="legacy")
                return pt_legacy_bytes.decode("utf-8", errors="replace"), "Legacy file (no receipt)."
            except InvalidTag:
                if logger:
                    logger.error("decrypt_failed_wrong_passphrase", file_path=enc_file, error_type="InvalidTag")
                return "❌ Decryption failed: wrong passphrase.", ""
        
        # Modern file format (with receipt)
        receipt = outer["receipt"]
        core_raw = receipt["core"]
        sig_b64 = receipt["signature"]
        
        # FERPA COMPLIANCE: Decrypt receipt_core if encrypted (new format)
        # Backward compatibility: if core_raw is already a dict, use as-is
        try:
            core = decrypt_receipt_core(core_raw)
        except ValueError as e:
            if logger:
                logger.error(
                    "decrypt_receipt_core_failed",
                    file_path=enc_file,
                    error_type="ValueError",
                    _internal_error_message=str(e)[:200]
                )
            return f"❌ Failed to decrypt receipt_core: {str(e)}", ""
        
        # Compute core_bytes from decrypted/plaintext core for signature verification
        core_bytes = json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")
        aad = hashlib.sha256(core_bytes).digest()
        
        # Verify signature using decrypted/plaintext core
        pub = base64.urlsafe_b64decode(core["device_pubkey"] + "==")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        
        try:
            ed25519.Ed25519PublicKey.from_public_bytes(pub).verify(sig, hashlib.sha256(core_bytes).digest())
        except InvalidSignature:
            if logger:
                logger.error("decrypt_invalid_signature", file_path=enc_file, error_type="InvalidSignature")
            return "❌ Invalid signature: device key signature failed.", ""
        
        sealed = base64.b64decode(outer["sealed_blob_b64"])
        
        try:
            pt_bytes = decrypt_bytes(sealed, passphrase, aad=aad)
        except InvalidTag:
            if logger:
                logger.error("decrypt_failed_passphrase_mismatch", file_path=enc_file, error_type="InvalidTag")
            return "❌ Decryption failed: wrong passphrase or receipt binding mismatch.", ""
        
        calc_sha = hashlib.sha256(pt_bytes).hexdigest()
        if calc_sha != core["transcript_sha256"]:
            if logger:
                # SECURITY: Never log full hashes - only first 8 chars for debugging
                logger.error(
                    "decrypt_tamper_detected",
                    file_path=enc_file,
                    calculated_sha_prefix=calc_sha[:8] + "...",
                    expected_sha_prefix=core["transcript_sha256"][:8] + "...",
                    hash_mismatch=True
                )
            return "❌ Tamper detected: transcript hash mismatch.", ""
        
        # Update receipt with decrypted core for downstream use
        receipt["core"] = core
        
        verdict = _check_and_mark_otet(core["otet"])
        
        if logger:
            # SECURITY: Never log OTET tokens - only verdict status
            logger.info(
                "decrypt_success",
                file_path=enc_file,
                verdict=verdict,
                otet_status="present" if core.get("otet") else "missing"
            )
        
        md_summary = f"**Integrity:** Signature & hash OK | {verdict}" if verdict else "**Integrity:** Signature & hash OK"
        pt_text = pt_bytes.decode("utf-8", errors="replace")
        
        return pt_text, md_summary
        
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        
        if logger:
            # SECURITY: Log internal error details but sanitize user-facing messages
            logger.error(
                "decrypt_error",
                file_path=enc_file,
                error_type=error_type,
                _internal_error_message=error_message[:200],  # Truncate for safety
                operation="instructor_decrypt"
            )
        
        # SECURITY: Sanitize error message - don't expose implementation details
        return "❌ Decryption failed. Please check the file and passphrase.", ""

