#!/bin/bash
set -m
cd "$(dirname "$0")"

# Determine Python to use (prefer venv if it exists)
PYTHON="python3"
if [ -f "backend/venv/bin/python" ]; then
    PYTHON="backend/venv/bin/python"
fi

# Start backend
DATABASE_URL="sqlite:///./dev.db" \
REDIS_URL="" \
TESTING="true" \
SECRET_KEY="dev-secret" \
ENV="development" \
ALLOWED_ORIGINS="http://localhost:8000" \
FEATURES_ENABLE_CSRF="false" \
ENABLE_CACHE="false" \
nohup "$PYTHON" -m backend.api.main \
  --host 0.0.0.0 --port 8000 \
  > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID) — http://localhost:8000"
