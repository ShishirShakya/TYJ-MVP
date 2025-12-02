"""
PDF processing utilities for downloading, extracting, and chunking PDF content.

This module provides functions for:
- Converting cloud storage URLs (Dropbox, Google Drive, OneDrive, Box) to direct download URLs
- Downloading PDFs from URLs with validation
- Extracting text from PDF bytes
- Chunking text into paragraphs with overlap
- Validating context chunks
"""

import os
import re
import tempfile
from typing import Optional, Tuple, List
import requests
import pdfplumber


def _detect_cloud_storage_provider(url: str) -> Tuple[str, str]:
    """
    Detect cloud storage provider from URL and return provider name.
    
    Args:
        url: Cloud storage share URL
        
    Returns:
        Tuple of (provider_name, normalized_url)
        Provider names: "Dropbox", "Google Drive", "OneDrive", "Box", "Direct URL"
    """
    if not url:
        return "Unknown", url
    
    url_lower = url.lower()
    
    if 'dropbox.com' in url_lower:
        return "Dropbox", url
    elif 'drive.google.com' in url_lower or 'docs.google.com' in url_lower:
        return "Google Drive", url
    elif 'onedrive.live.com' in url_lower or '1drv.ms' in url_lower:
        return "OneDrive", url
    elif 'box.com' in url_lower:
        return "Box", url
    else:
        return "Direct URL", url


def _convert_dropbox_url_internal(url: str) -> str:
    """
    Internal Dropbox URL conversion logic.
    Extracted from _convert_dropbox_url for reuse.
    
    Args:
        url: Dropbox share URL
        
    Returns:
        Direct download URL
    """
    if not url:
        return url
    
    # Parse URL and query string
    url_parts = url.split('?', 1)
    base_url = url_parts[0]
    query_string = url_parts[1] if len(url_parts) > 1 else ""
    
    # Handle new Dropbox format with /scl/fi/
    if '/scl/fi/' in base_url:
        # For /scl/ format, just change dl=0 to dl=1 in query string
        # Keep all other query parameters (rlkey, st, etc.)
        if query_string:
            # Parse query parameters
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            # Force dl=1
            params['dl'] = '1'
            
            # Reconstruct query string
            new_query = '&'.join(f"{k}={v}" for k, v in params.items())
            return f"{base_url}?{new_query}"
        else:
            # No query string, just add dl=1
            return f"{base_url}?dl=1"
    
    # Handle old format with /s/
    elif '/s/' in base_url:
        # Convert to dl.dropboxusercontent.com format
        url = base_url.replace('www.dropbox.com/s/', 'dl.dropboxusercontent.com/s/')
        url = url.replace('dropbox.com/s/', 'dl.dropboxusercontent.com/s/')
        # Always use dl=1 for direct download
        return f"{url}?dl=1"
    
    # For other Dropbox URLs or direct links, just ensure dl=1
    elif 'dropbox.com' in base_url:
        if query_string:
            # Update dl parameter if exists, otherwise add it
            params = {}
            for param in query_string.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    params[key] = value
            
            params['dl'] = '1'
            new_query = '&'.join(f"{k}={v}" for k, v in params.items())
            return f"{base_url}?{new_query}"
        else:
            return f"{base_url}?dl=1"
    
    # For non-Dropbox URLs, return as-is
    return url


def _convert_cloud_storage_url(url: str) -> Tuple[str, str]:
    """
    Convert cloud storage share URL to direct download URL.
    Supports Dropbox, Google Drive, OneDrive, Box, and direct URLs.
    
    Args:
        url: Cloud storage share URL
        
    Returns:
        Tuple of (direct_download_url, provider_name)
    """
    if not url:
        return url, "Unknown"
    
    provider, normalized_url = _detect_cloud_storage_provider(url)
    
    # Dropbox conversion (existing logic)
    if provider == "Dropbox":
        return _convert_dropbox_url_internal(normalized_url), provider
    
    # Google Drive conversion
    elif provider == "Google Drive":
        # Extract file ID from various Google Drive URL formats
        # Format 1: https://drive.google.com/file/d/FILE_ID/view?usp=sharing
        # Format 2: https://drive.google.com/open?id=FILE_ID
        # Format 3: https://docs.google.com/document/d/FILE_ID/edit
        file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', normalized_url)
        if not file_id_match:
            file_id_match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', normalized_url)
        
        if file_id_match:
            file_id = file_id_match.group(1)
            # Use direct download URL format
            # For large files, Google Drive may require confirmation - handled by requests redirect
            return f"https://drive.google.com/uc?export=download&id={file_id}", provider
        # If no file ID found, return as-is (may be a direct link already)
        return normalized_url, provider
    
    # OneDrive conversion
    elif provider == "OneDrive":
        # Handle short links (1drv.ms) - requests will follow redirect
        if '1drv.ms' in normalized_url.lower():
            return normalized_url, provider
        
        # Convert OneDrive share links to download links
        # Format: https://onedrive.live.com/redir?resid=...&authkey=...
        # Convert to: https://onedrive.live.com/download?resid=...&authkey=...
        converted_url = normalized_url.replace('/redir?', '/download?')
        return converted_url, provider
    
    # Box conversion
    elif provider == "Box":
        # Convert Box share links
        # Format: https://app.box.com/s/xxxxx -> https://app.box.com/shared/static/xxxxx
        if '/s/' in normalized_url:
            converted_url = normalized_url.replace('/s/', '/shared/static/')
            return converted_url, provider
        return normalized_url, provider
    
    # Direct URL (no conversion needed)
    else:
        return normalized_url, provider


def _convert_dropbox_url(url: str) -> str:
    """
    Convert Dropbox public share URL to direct download URL.
    Handles both old format (/s/) and new format (/scl/).
    
    DEPRECATED: Use _convert_cloud_storage_url() instead for multi-provider support.
    Kept for backward compatibility.
    
    Old format: https://www.dropbox.com/s/xxxxx/file.pdf?dl=0
    New format: https://www.dropbox.com/scl/fi/xxxxx/file.pdf?rlkey=xxx&dl=0
    
    Args:
        url: Dropbox share URL
        
    Returns:
        Direct download URL with dl=1
    """
    return _convert_cloud_storage_url(url)[0]


def _download_pdf_from_url(url: str, max_size: Optional[int] = None) -> bytes:
    """
    Download PDF from URL (supports Dropbox, Google Drive, OneDrive, Box, direct links) 
    with improved error detection.
    Returns PDF content as bytes.
    
    Args:
        url: URL to download PDF from
        max_size: Maximum file size in bytes (optional)
        
    Returns:
        PDF content as bytes
        
    Raises:
        ValueError: If download fails, file is too large, or content is not a PDF
    """
    try:
        # Convert cloud storage URL if needed
        download_url, provider = _convert_cloud_storage_url(url)
        
        # Download with streaming and size limits
        response = requests.get(download_url, stream=True, timeout=30, allow_redirects=True)
        response.raise_for_status()
        
        # VALIDATION: Check if response is actually a PDF
        # Cloud storage providers might return HTML error pages with 200 OK
        content_type = response.headers.get('Content-Type', '').lower()
        if 'html' in content_type:
            # Provider returned HTML (likely an error page)
            raise ValueError(f"{provider} returned HTML instead of PDF. The link may be expired, rate-limited, or disabled. Please check the {provider} link.")
        
        # Check if it's a PDF (but don't fail if content-type is missing - some servers don't send it)
        if 'pdf' not in content_type and not download_url.lower().endswith('.pdf'):
            # Warn but continue - some servers don't send correct content-type
            pass
        
        # Check size from headers
        content_length = response.headers.get('Content-Length')
        if content_length:
            size = int(content_length)
            if max_size is not None and size > max_size:
                raise ValueError(f"PDF file too large ({size / (1024*1024):.1f}MB). Maximum allowed: {max_size / (1024*1024):.1f}MB")
        
        # Download with size limit
        pdf_data = b""
        for chunk in response.iter_content(chunk_size=8192):
            pdf_data += chunk
            if max_size is not None and len(pdf_data) > max_size:
                raise ValueError(f"PDF file too large. Maximum allowed: {max_size / (1024*1024):.1f}MB")
        
        if len(pdf_data) == 0:
            raise ValueError("Downloaded PDF is empty")
        
        # VALIDATION: Check if downloaded content is actually a PDF
        # PDF files start with %PDF- (magic number)
        if len(pdf_data) > 0 and not pdf_data.startswith(b'%PDF-'):
            # Check if it's HTML (provider error page)
            if pdf_data.startswith(b'<html') or pdf_data.startswith(b'<!DOCTYPE') or pdf_data.startswith(b'<HTML'):
                raise ValueError(f"{provider} returned HTML error page instead of PDF. The link may be expired, rate-limited, or disabled. Please check the {provider} link.")
            
            # Check for common error messages in the content (provider-agnostic check)
            pdf_data_str = pdf_data[:500].decode('utf-8', errors='ignore').lower()
            provider_lower = provider.lower()
            if provider_lower in pdf_data_str and ('error' in pdf_data_str or 'forbidden' in pdf_data_str or 'not found' in pdf_data_str):
                raise ValueError(f"{provider} returned an error page instead of PDF. The link may be expired, rate-limited, or disabled. Please check the {provider} link.")
            
            # Otherwise, it's not a valid PDF
            raise ValueError("Downloaded file is not a valid PDF. Please check the URL.")
        
        return pdf_data
    except requests.exceptions.HTTPError as e:
        # Handle specific HTTP errors with better messages
        provider = _detect_cloud_storage_provider(url)[0]
        if e.response.status_code == 429:
            raise ValueError(f"{provider} rate limit exceeded. Please wait a few minutes and try again, or use a different {provider} link.")
        elif e.response.status_code == 403:
            raise ValueError(f"{provider} link is forbidden or expired. Please check the link or create a new public link.")
        elif e.response.status_code == 404:
            raise ValueError(f"{provider} link not found. Please check the link or create a new public link.")
        else:
            raise ValueError(f"Failed to download PDF: HTTP {e.response.status_code} - {str(e)}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to download PDF: {type(e).__name__}: {e}")
    except Exception as e:
        raise ValueError(f"Error downloading PDF: {type(e).__name__}: {e}")


def _load_pdf_from_bytes(pdf_bytes: bytes, max_pages: Optional[int] = None, logger=None) -> str:
    """
    Extract text from PDF bytes.
    Returns extracted text as string.
    
    Args:
        pdf_bytes: PDF content as bytes
        max_pages: Maximum number of pages to extract (optional, truncates if exceeded)
        logger: Optional logger instance for warnings (if None, uses print)
        
    Returns:
        Extracted text as string
        
    Raises:
        ValueError: If PDF processing fails or no text could be extracted
    """
    text = ""
    try:
        # Save to temporary file for pdfplumber
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(pdf_bytes)
            tmp_path = tmp_file.name
        
        try:
            with pdfplumber.open(tmp_path) as pdf:
                page_count = 0
                for page in pdf.pages:
                    page_count += 1
                    if max_pages is not None and page_count > max_pages:
                        warning_msg = f"⚠️ PDF has too many pages (>{max_pages}). Truncating."
                        if logger:
                            logger.warning(
                                "pdf_too_many_pages",
                                message=f"PDF has too many pages (>{max_pages}). Truncating.",
                                page_count=page_count,
                                max_pages=max_pages,
                                action="truncating"
                            )
                        else:
                            # OBSERVABILITY: Fallback to basic logging if logger not available (Principle #13)
                            # In production, logger should always be available
                            import sys
                            sys.stderr.write(f"WARNING: {warning_msg}\n")
                        break
                    t = page.extract_text()
                    if t:
                        text += t
        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        
        if not text:
            raise ValueError("No text could be extracted from PDF")
        
        return text
    except Exception as e:
        raise ValueError(f"Error processing PDF: {type(e).__name__}: {e}")


def _chunk_text(text: str, max_chars: int = 500, overlap: int = 100) -> List[str]:
    """
    Chunk text into paragraphs with overlap.
    
    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk (default: 500)
        overlap: Number of characters to overlap between chunks (default: 100)
        
    Returns:
        List of text chunks
    """
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    chunks, buf = [], ""
    for para in paras:
        # If a single paragraph exceeds max_chars, split it
        if len(para) > max_chars:
            # First, save current buffer if it exists
            if buf:
                chunks.append(buf)
                buf = ""
            
            # Split the long paragraph into chunks
            start = 0
            while start < len(para):
                end = start + max_chars
                chunk = para[start:end]
                chunks.append(chunk)
                
                # Move start position with overlap
                start = end - overlap
                if start >= len(para):
                    break
        else:
            # Normal paragraph handling
            if not buf:
                buf = para
            elif len(buf) + 1 + len(para) <= max_chars:
                buf += "\n" + para
            else:
                chunks.append(buf)
                tail = buf[-overlap:] if overlap > 0 else ""
                buf = (tail + "\n" + para).strip()
    
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if c.strip()]


def _validate_context(ctx_text: str, min_chars: int = 50) -> Tuple[bool, str]:
    """
    Validate context chunk before use.
    Returns (is_valid, error_message).
    
    Args:
        ctx_text: Context text to validate
        min_chars: Minimum number of characters required (default: 50)
        
    Returns:
        Tuple of (is_valid: bool, error_message: str)
    """
    if not ctx_text or not ctx_text.strip():
        return False, "Context is empty"
    
    ctx_text = ctx_text.strip()
    
    # Check minimum length
    if len(ctx_text) < min_chars:
        return False, f"Context too short ({len(ctx_text)} chars, min {min_chars})"
    
    # Check for meaningful content (not just whitespace/special chars)
    meaningful_chars = sum(1 for c in ctx_text if c.isalnum())
    if meaningful_chars < min_chars * 0.7:
        return False, "Context doesn't contain enough meaningful content"
    
    return True, ""

