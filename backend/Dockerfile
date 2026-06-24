# syntax=docker/dockerfile:1.4.0
# Multi-stage build for optimized image
FROM python:3.11-slim as builder

# Build arguments
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=1.0.0

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Metadata labels
LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.authors="Universal Dependency Resolver Team" \
      org.opencontainers.image.url="https://github.com/code-with-zeeshan/universal-dependency-resolver" \
      org.opencontainers.image.documentation="https://github.com/code-with-zeeshan/universal-dependency-resolver/blob/main/README.md" \
      org.opencontainers.image.source="https://github.com/code-with-zeeshan/universal-dependency-resolver" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.vendor="Your Organization" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="Universal Dependency Resolver API" \
      org.opencontainers.image.description="A comprehensive API for resolving dependencies across multiple package ecosystems"

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    # Add these for production needs
    ca-certificates \
    # PostgreSQL client (for migrations)
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app directory and set permissions
WORKDIR /app

# Create non-root user first
RUN useradd -m -u 1000 -s /bin/bash appuser

# Copy application code with correct ownership
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/logs /app/data && \
    chown -R appuser:appuser /app/logs /app/data

# Environment variables with defaults
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # API settings
    PORT=8000 \
    HOST=0.0.0.0 \
    # Workers (can be overridden)
    WEB_CONCURRENCY=4 \
    # Log level
    LOG_LEVEL=info

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# Create entrypoint script for flexibility
COPY --chown=appuser:appuser <<'EOF' /app/entrypoint.sh
#!/bin/bash
set -e

# Run database migrations if needed
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

# Start the application
if [ "$ENVIRONMENT" = "development" ]; then
    echo "Starting in development mode..."
    exec uvicorn backend.api.main:app \
        --host $HOST \
        --port $PORT \
        --reload \
        --log-level debug
else
    echo "Starting in production mode..."
    exec uvicorn backend.api.main:app \
        --host $HOST \
        --port $PORT \
        --workers $WEB_CONCURRENCY \
        --log-level $LOG_LEVEL \
        --access-log
fi
EOF

RUN chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]