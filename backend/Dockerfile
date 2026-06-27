# syntax=docker/dockerfile:1.4.0
FROM python:3.11-slim as builder

ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=1.0.0

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    gcc g++ git libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir ".[system,postgres,monitoring]"

FROM python:3.11-slim

LABEL org.opencontainers.image.created=$BUILD_DATE \
      org.opencontainers.image.authors="Universal Dependency Resolver Team" \
      org.opencontainers.image.url="https://github.com/code-with-zeeshan/universal-dependency-resolver" \
      org.opencontainers.image.source="https://github.com/code-with-zeeshan/universal-dependency-resolver" \
      org.opencontainers.image.version=$VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="Universal Dependency Resolver API" \
      org.opencontainers.image.description="Resolve dependencies across multiple package ecosystems"

RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN useradd -m -u 1000 -s /bin/bash appuser

COPY --chown=appuser:appuser backend/ backend/

RUN mkdir -p /app/logs /app/data && \
    chown -R appuser:appuser /app/logs /app/data

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    WEB_CONCURRENCY=4 \
    LOG_LEVEL=info

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

COPY --chown=appuser:appuser <<'EOF' /app/entrypoint.sh
#!/bin/bash
set -e
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi
if [ "$ENVIRONMENT" = "development" ]; then
    echo "Starting in development mode..."
    exec uvicorn backend.api.main:app --host $HOST --port $PORT --reload --log-level debug
else
    echo "Starting in production mode..."
    exec uvicorn backend.api.main:app --host $HOST --port $PORT --workers $WEB_CONCURRENCY --log-level $LOG_LEVEL --access-log
fi
EOF

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
