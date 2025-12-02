"""
Exam module for student interface (exam.ipynb).

This package contains all modules used exclusively by the student exam interface.
Modules are organized by functionality:

Subpackages:
- ai: AI-powered question generation, grading, and context management
- audio: Text-to-speech, speech-to-text, voiceprint, and stylometric analysis
- export: Finalize and export encrypted exam transcripts
- flow: Core business logic for exam flow (questions, audio, grading)
- pdf_cache: PDF content caching (memory and disk)
- proctor: Video proctoring and analysis
- security: Security utilities (OTET, device keys, Merkle trees, logging)
- state: State management (core, persistence, network, serialization)
- ui: UI components, handlers, helpers, and layout
- wrappers: Wrapper functions for backward compatibility with notebook context

Modules:
- config.py: Configuration for exam interface
- context_vars.py: Context variables for dependency injection
- cryptography.py: Encryption/decryption functions
- file_utils.py: File utilities for session management
- utils.py: Text processing, validation, and error handling utilities

All modules use dependency injection to preserve wiring and ensure compatibility.
"""

