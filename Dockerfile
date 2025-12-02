# Phase 3.3: Production Dockerfile for VivaAI Assessment System
# Multi-stage build for optimized image size

# Stage 1: Build dependencies
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
# ADD: MediaPipe and OpenCV system dependencies
# libgomp1: OpenMP support for MediaPipe
# libgl1: OpenGL library required by OpenCV (libGL.so.1)
# libglib2.0-0: GLib library required by OpenCV
RUN apt-get update && apt-get install -y \
    curl \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p exam_state ferpa_audit_logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose ports
EXPOSE 8000 7860 7861 7862

# Health check (uses PORT env var, defaults to 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD sh -c "curl -f http://localhost:${PORT:-8000}/health || exit 1"

# Make start.sh executable
RUN chmod +x start.sh

# Default command (can be overridden)
# Uses Railway's PORT environment variable, defaults to 8000 if not set
CMD ["./start.sh"]
