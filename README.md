# VivaAI Assessment API

[![Coverage](https://codecov.io/gh/ShishirShakya/knock/branch/main/graph/badge.svg)](https://codecov.io/gh/ShishirShakya/knock)
[![CI](https://github.com/ShishirShakya/knock/actions/workflows/ci.yml/badge.svg)](https://github.com/ShishirShakya/knock/actions/workflows/ci.yml)

FastAPI service for VivaAI Secure Exam Proctoring System.

## Overview

This is the proprietary backend API service that handles all assessment processing logic. The service is deployed to Railway and accessed by the public UI (deployed to Hugging Face Spaces).

## Architecture

- **Backend**: FastAPI service (this repository)
- **Frontend**: Gradio UI (deployed to Hugging Face Spaces)
- **Communication**: HTTPS with API key authentication

## Setup

1. **Install dependencies:**
   ```bash
   # Using uv (recommended)
   uv pip install -e .
   
   # Or using pip
   pip install -r requirements.txt
   
   **Note**: `pyproject.toml` is the single source of truth for dependencies. `requirements.txt` is kept for compatibility with Docker and older tools. See `docs/DEPENDENCY_MANAGEMENT.md` for details.
   # Or using uv (recommended):
   uv sync
   ```

2. **Set environment variables:**
   
   Create a `.env` file in the project root with the following variables:
   ```bash
   # Required for production
   VIVA_HMAC_SECRET=your-secret-key-here-min-32-chars
   
   # Optional: Rate limiting configuration
   RATE_LIMIT_PER_MINUTE=60
   RATE_LIMIT_PER_HOUR=1000
   RATE_LIMIT_BURST=10
   
   # Optional: Environment
   ENVIRONMENT=development  # or "production"
   ```

3. **Run locally:**
   ```bash
   uvicorn app.main:app --reload
   ```

## Deployment

### Railway

**Quick Start**:
1. Connect your GitHub repository to Railway
2. Set environment variables in Railway dashboard (see `RAILWAY_CHECKLIST.md`)
3. Railway will automatically detect Dockerfile and deploy

**Required Environment Variables**:
- `VIVA_HMAC_SECRET` - HMAC secret (min 32 characters)
- `OPENAI_API_KEY` - OpenAI API key

**Recommended for Production**:
- `VALID_API_KEYS` - Comma-separated list of valid API keys
- `ENVIRONMENT=production` - Disables API docs

**Full Deployment Guide**: See `RAILWAY_CHECKLIST.md` for complete deployment instructions and troubleshooting.

## API Endpoints

All endpoints require `X-API-Key` header for authentication (except health, metrics, and root endpoints).

### Assessment Endpoints
- `POST /api/v1/assessments/generate-question` - Generate question
- `POST /api/v1/assessments/grade` - Grade answer
- `POST /api/v1/assessments/process-audio` - Process audio
- `POST /api/v1/assessments/analyze-proctor` - Analyze proctoring
- `POST /api/v1/assessments/parse-link` - Parse professor link

### System Endpoints
- `GET /health` - Enhanced health check with dependency monitoring
- `GET /metrics` - API metrics and observability data
- `GET /` - Root endpoint

## Security

- API key authentication required for all endpoints
- Rate limiting: 100 requests per minute per API key (configurable)
- CORS configured to only allow Hugging Face Spaces
- API documentation disabled in production
- Generic error messages (no internal details exposed)

## Features

- **Request Tracing**: All requests include unique request IDs for debugging
- **Rate Limiting**: Per-API-key rate limiting with configurable limits
- **Circuit Breakers**: Automatic failure detection and recovery for external services
- **Health Monitoring**: Enhanced health check with dependency status
- **Metrics**: Built-in metrics endpoint for observability
- **Error Handling**: Comprehensive error handling with sanitized messages
- **Idempotency**: Request ID tracking for safe retries
- **Selective Serialization**: Efficient state persistence with bounded collections

## Testing

Run the test suite:
```bash
pytest tests/ -v
pytest tests/ --cov=exam --cov=shared --cov-report=html
```

See `tests/README.md` for detailed testing documentation.

## Architecture Principles

This codebase follows 26 core engineering principles (see `z-thoughts/cp.txt`):
- Minimal, clear, high-value code
- Single source of truth (SSOT)
- Business logic isolation
- Dependency injection throughout
- Error sanitization
- Deterministic behavior
- And 20 more...

## Documentation

- **Module Organization**: See `docs/MODULE_ORGANIZATION.md` for package structure
- **Naming Conventions**: See `docs/NAMING_CONVENTIONS.md` for abbreviations and patterns
- **Graceful Failure**: See `docs/GRACEFUL_FAILURE.md` for error handling strategy

## Versioning

- **API Versioning**: URL-based (`/api/v1/`, `/api/v2/`)
- **App Version**: Defined in `exam/config.py` (`APP_VERSION`)
- **Receipt Version**: Defined in `exam/config.py` (`RECEIPT_VERSION`)
- **Backward Compatibility**: Maintained for at least one major version cycle

## License

Proprietary - All rights reserved
