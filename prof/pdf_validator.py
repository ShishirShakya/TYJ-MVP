"""
PDF validation utilities for prof.ipynb.

This module contains PDF validation and chunking functions used only by prof.ipynb.
Functions used by multiple apps are in shared/.
"""

from typing import Dict, Any
from shared.pdf_processing import (
    _download_pdf_from_url,
    _load_pdf_from_bytes,
    _chunk_text,
    _validate_context,
)
from prof.config import MAX_PDF_SIZE, logger


def validate_pdf_and_calculate_chunks(pdf_url: str) -> Dict[str, Any]:
    """
    Validate PDF and calculate chunks using exact same logic as exam.ipynb.
    Returns dict with: num_total_chunks, num_valid_chunks, invalid_count, file_size_mb
    On error, returns dict with error message.
    
    Args:
        pdf_url: URL to the PDF file (cloud storage link)
        
    Returns:
        Dictionary with validation results:
        - num_total_chunks: Total number of chunks created
        - num_valid_chunks: Number of valid chunks
        - invalid_count: Number of invalid chunks
        - file_size_mb: File size in megabytes
        - error: Error message if validation failed, None otherwise
    """
    logger.info("pdf_validation_started", pdf_url=pdf_url, operation="validate_pdf_and_calculate_chunks")
    try:
        # Step 1: Download PDF
        pdf_bytes = _download_pdf_from_url(pdf_url, max_size=MAX_PDF_SIZE)
        file_size_mb = len(pdf_bytes) / (1024 * 1024)
        
        # Step 2: Extract text (MUST use same function as exam.ipynb)
        pdf_text = _load_pdf_from_bytes(pdf_bytes, logger=logger)
        
        # Step 3: Calculate chunks (MUST use exact same parameters as exam.ipynb)
        new_chunks = _chunk_text(pdf_text, max_chars=900, overlap=150)
        
        # Step 4: Validate chunks (MUST use exact same validation as exam.ipynb)
        valid_chunks = []
        invalid_count = 0
        for chunk in new_chunks:
            is_valid, error = _validate_context(chunk, min_chars=50)
            if is_valid:
                valid_chunks.append(chunk)
            else:
                invalid_count += 1
        
        # Step 5: Return results
        num_total_chunks = len(new_chunks)
        num_valid_chunks = len(valid_chunks)
        
        # Validation checks (same as exam.ipynb)
        if not new_chunks:
            logger.error(
                "pdf_chunking_failed",
                pdf_url=pdf_url,
                error="No valid chunks created. PDF may be empty or corrupted.",
                file_size_mb=file_size_mb
            )
            return {
                'error': "PDF chunking failed: No valid chunks created. PDF may be empty or corrupted.",
                'num_total_chunks': 0,
                'num_valid_chunks': 0,
                'invalid_count': 0,
                'file_size_mb': file_size_mb
            }
        
        if not valid_chunks:
            logger.error(
                "pdf_validation_failed",
                pdf_url=pdf_url,
                error="No valid chunks found",
                num_total_chunks=num_total_chunks,
                num_valid_chunks=0,
                invalid_count=invalid_count,
                file_size_mb=file_size_mb
            )
            return {
                'error': f"PDF validation failed: No valid chunks found. Total chunks: {num_total_chunks}, Valid chunks: 0. PDF content may be too short or invalid.",
                'num_total_chunks': num_total_chunks,
                'num_valid_chunks': 0,
                'invalid_count': invalid_count,
                'file_size_mb': file_size_mb
            }
        
        logger.info(
            "pdf_validation_success",
            pdf_url=pdf_url,
            num_total_chunks=num_total_chunks,
            num_valid_chunks=num_valid_chunks,
            invalid_count=invalid_count,
            file_size_mb=file_size_mb
        )
        return {
            'num_total_chunks': num_total_chunks,
            'num_valid_chunks': num_valid_chunks,
            'invalid_count': invalid_count,
            'file_size_mb': file_size_mb,
            'error': None
        }
    except ValueError as e:
        logger.error(
            "pdf_validation_error",
            pdf_url=pdf_url,
            error_type="ValueError",
            error_message=str(e),
            operation="validate_pdf_and_calculate_chunks"
        )
        return {
            'error': str(e),
            'num_total_chunks': 0,
            'num_valid_chunks': 0,
            'invalid_count': 0,
            'file_size_mb': 0
        }
    except Exception as e:
        error_type = type(e).__name__
        error_message = str(e)
        logger.error(
            "pdf_validation_exception",
            pdf_url=pdf_url,
            error_type=error_type,
            error_message=error_message,
            operation="validate_pdf_and_calculate_chunks"
        )
        return {
            'error': f"Error validating PDF: {error_type}: {error_message}",
            'num_total_chunks': 0,
            'num_valid_chunks': 0,
            'invalid_count': 0,
            'file_size_mb': 0
        }

