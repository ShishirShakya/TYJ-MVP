# Test Suite

This directory contains the test suite for the VivaAI Secure Exam Proctoring System.

## Structure

```
tests/
├── conftest.py                      # Pytest configuration and shared fixtures
├── helpers.py                       # Test helper functions
├── run_all_tests.py                 # Test runner script
├── COMPLETE_FLOW_TESTING.md         # Complete flow testing guide
├── unit/                            # Unit tests for individual modules
│   ├── test_state_core.py
│   ├── test_security_logging.py
│   └── test_rate_limiting.py
└── integration/                     # Integration tests for workflows
    ├── test_complete_exam_flow.py   # Complete end-to-end exam flow tests
    ├── test_grading_workflow.py
    └── test_state_persistence_workflow.py
```

## Running Tests

### Run all tests
```bash
uv run pytest
```

### Run specific test file
```bash
uv run pytest tests/unit/test_state_core.py
```

### Run with coverage
```bash
uv run pytest --cov=exam --cov=shared --cov-report=html
```

### Run with verbose output
```bash
uv run pytest -v
```

### Use the test runner script
```bash
uv run python tests/run_all_tests.py --coverage
```

## Test Principles

All tests preserve the existing dependency injection wiring pattern:

1. **No Breaking Changes**: Tests use the same dependency injection structure as production code
2. **Fixture-Based**: Common test data is provided via pytest fixtures
3. **Isolated**: Each test is independent and doesn't rely on external state
4. **Preserve Wiring**: Tests use `_build_*_dependencies()` functions or mock equivalents

## Adding New Tests

### Unit Tests

Create test files in `tests/unit/` following the naming pattern `test_<module_name>.py`:

```python
"""Unit tests for exam.some_module."""

import pytest
from exam.some_module import some_function
from tests.helpers import build_minimal_state


class TestSomeFunction:
    """Tests for some_function."""
    
    def test_some_function_basic(self):
        """Test basic functionality."""
        state = build_minimal_state()
        result = some_function(state)
        assert result is not None
```

### Integration Tests

Create test files in `tests/integration/` for cross-module workflows:

```python
"""Integration tests for workflow."""

import pytest
from tests.conftest import mock_dependencies_exam_flow


def test_workflow_with_dependencies():
    """Test workflow with injected dependencies."""
    dependencies = mock_dependencies_exam_flow()
    # Test workflow using dependencies
```

## Fixtures

### Available Fixtures

- `mock_state`: Minimal state dictionary with all required fields
- `mock_openai_client`: Mock OpenAI client for testing
- `mock_gradio_module`: Mock Gradio module for testing
- `mock_dependencies_exam_flow`: Mock dependencies for exam flow functions
- `mock_dependencies_dash`: Mock dependencies for dash handlers
- `mock_dependencies_prof`: Mock dependencies for prof handlers

### Using Fixtures

```python
def test_something(mock_state, mock_openai_client):
    """Test using fixtures."""
    # Use mock_state and mock_openai_client
    result = some_function(mock_state, mock_openai_client)
    assert result is not None
```

## Test Coverage Goals

- **Core Business Logic** (`exam/flow/`, `exam/ai/`): 80%+
- **State Management** (`exam/state/`): 90%+
- **Security** (`exam/security/`): 95%+
- **Critical Paths**: 100%

## Preserving Dependency Injection

When writing tests, always:

1. Use the same dependency structure as production
2. Mock dependencies via fixtures or `mock_dependencies_*` functions
3. Never change function signatures that receive `dependencies: Dict[str, Any]`
4. Extract dependencies the same way: `func = dependencies["func"]`

Example:

```python
def test_handler_with_dependencies(mock_dependencies_exam_flow):
    """Test handler preserves dependency injection."""
    dependencies = mock_dependencies_exam_flow()
    
    # Extract dependencies the same way as production code
    ensure_state = dependencies["ensure_state"]
    rate_limiter = dependencies.get("rate_limiter")
    
    # Use dependencies
    state = ensure_state({})
    if rate_limiter:
        allowed, _ = rate_limiter.check_rate_limit(state["session_id"])
        assert allowed is True
```

