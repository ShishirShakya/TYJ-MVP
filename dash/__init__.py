"""
Dashboard module for instructor interface (dash.ipynb).

This package contains all modules used exclusively by the instructor dashboard.
Modules are organized by functionality:

Subpackages:
- ui: UI layer (handlers, helpers) for Gradio interface

Modules:
- cache.py: Cache management for decrypted exam data
- config.py: Configuration for dashboard interface
- csv_export.py: CSV/Excel export functionality
- decryption.py: Decryption of encrypted exam files
- grade_adjustment.py: Grade adjustment calculations (statistical, percentile, confidence)
- parsing.py: Parsing of decrypted exam data

All modules use dependency injection to preserve wiring and ensure compatibility.
"""

