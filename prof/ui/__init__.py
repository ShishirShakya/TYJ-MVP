"""
UI layer for prof.ipynb (professor URL generator).

This package contains UI-related modules for the professor URL generator:

Modules:
- helpers.py: Pure helper functions for UI calculations and formatting
- handlers.py: Gradio event handlers with dependency injection
  - PDF validation
  - URL generation
  - All handlers use dependency injection to preserve wiring

All handlers follow consistent patterns:
- Extract dependencies from dependencies dictionary
- Use shared validation helpers (shared/validation.py)
- Use shared error formatters (shared/error_formatter.py)
- Return standardized error messages
"""

