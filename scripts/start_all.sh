#!/bin/bash
# Unified startup script for all VivaAI Assessment services
# Starts API server, Exam interface, Professor URL generator, and Dashboard

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting VivaAI Assessment Services...${NC}"

# Check if .env file exists and source it if present
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found. Some services may not work correctly.${NC}"
    echo -e "${YELLOW}   Create a .env file with required environment variables.${NC}"
else
    # Source .env file to load environment variables (for bash script)
    # Note: This is a simple approach - for production, use a proper .env parser
    set -a
    source .env 2>/dev/null || true
    set +a
    echo -e "${GREEN}✓ Loaded environment variables from .env${NC}"
fi

# Function to check if port is available
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        echo -e "${RED}✗ Port $port is already in use${NC}"
        return 1
    else
        return 0
    fi
}

# Check ports before starting
echo "Checking ports..."
check_port 8000 || exit 1
check_port 7860 || exit 1
check_port 7861 || exit 1
check_port 7862 || exit 1
echo -e "${GREEN}✓ All ports available${NC}"

# Start API server in background
echo ""
echo -e "${GREEN}Starting API server...${NC}"
uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/api_server.log 2>&1 &
API_PID=$!
echo "API server PID: $API_PID"

# Wait for API to be ready
echo "Waiting for API server to start..."
sleep 3

# Check if API is responding
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API server is ready${NC}"
else
    echo -e "${YELLOW}⚠️  API server may not be ready yet${NC}"
fi

# Start Exam with API mode (if configured)
echo ""
echo -e "${GREEN}Starting Exam interface...${NC}"
# Check if API_BASE_URL is set (your existing variable) - auto-enables API mode
if [ -n "${API_BASE_URL:-}" ] || [ -n "${EXAM_API_URL:-}" ]; then
    # Use API_BASE_URL if set, otherwise EXAM_API_URL
    API_URL=${API_BASE_URL:-${EXAM_API_URL:-http://localhost:8000}}
    # Use API_KEY if set, otherwise EXAM_API_KEY
    API_KEY_VAL=${API_KEY:-${EXAM_API_KEY:-}}
    
    export API_BASE_URL=${API_BASE_URL:-}
    export API_KEY=${API_KEY:-}
    export EXAM_API_URL=${EXAM_API_URL:-}
    export EXAM_API_KEY=${EXAM_API_KEY:-}
    
    if [ -n "$API_KEY_VAL" ]; then
        echo "API Mode: Enabled (URL: $API_URL)"
    else
        echo -e "${YELLOW}⚠️  API Mode: Enabled but API_KEY/EXAM_API_KEY not set${NC}"
        echo "API Mode: Enabled (URL: $API_URL, but missing API key)"
    fi
else
    echo "API Mode: Disabled (standalone mode - API_BASE_URL/EXAM_API_URL not set)"
fi
python exam.py > /tmp/exam.log 2>&1 &
EXAM_PID=$!
echo "Exam PID: $EXAM_PID"

# Start Prof
echo ""
echo -e "${GREEN}Starting Professor URL Generator...${NC}"
python prof.py > /tmp/prof.log 2>&1 &
PROF_PID=$!
echo "Prof PID: $PROF_PID"

# Start Dash
echo ""
echo -e "${GREEN}Starting Dashboard...${NC}"
python dash.py > /tmp/dash.log 2>&1 &
DASH_PID=$!
echo "Dash PID: $DASH_PID"

# Wait a bit for services to start
sleep 2

# Summary
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}All services started successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "Service URLs:"
echo -e "  ${GREEN}API Server:${NC}    http://localhost:8000 (PID: $API_PID)"
echo -e "  ${GREEN}Exam:${NC}          http://localhost:7860 (PID: $EXAM_PID)"
echo -e "  ${GREEN}Professor:${NC}     http://localhost:7861 (PID: $PROF_PID)"
echo -e "  ${GREEN}Dashboard:${NC}     http://localhost:7862 (PID: $DASH_PID)"
echo ""
echo "Logs:"
echo "  API:    /tmp/api_server.log"
echo "  Exam:   /tmp/exam.log"
echo "  Prof:   /tmp/prof.log"
echo "  Dash:   /tmp/dash.log"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Stopping all services...${NC}"
    kill $API_PID $EXAM_PID $PROF_PID $DASH_PID 2>/dev/null || true
    echo -e "${GREEN}All services stopped${NC}"
    exit 0
}

# Trap Ctrl+C
trap cleanup INT TERM

# Wait for all processes
wait

