#!/bin/sh
# Startup script for Railway deployment
# Handles both backend (uvicorn) and frontend (Gradio) services

set -e  # Exit on error

if [ -n "$SERVICE_NAME" ]; then
    # Frontend service - run Python script
    echo "Starting frontend service: $SERVICE_NAME"
    exec python "$SERVICE_NAME"
else
    # Backend service - run uvicorn
    echo "Starting backend service"
    # Railway always sets PORT, but use default if somehow missing
    PORT=${PORT:-8000}
    echo "PORT environment variable: $PORT"
    echo "Starting uvicorn on port $PORT"
    exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
fi

