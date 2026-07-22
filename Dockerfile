# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS builder

RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README_PYPI.md ./
COPY backend/ backend/

RUN pip install --no-cache-dir -e ".[system,postgres]"

FROM python:3.12-slim-bookworm AS runtime

RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r udr && useradd -r -g udr -d /home/udr -m udr

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/backend /app/backend

ENV UDR_HOME=/home/udr \
    UDR_PORT=8000 \
    UDR_HOST=0.0.0.0 \
    ENV=production \
    ENABLE_AUTH=true

RUN printf '#!/bin/bash\nif [ "$SECRET_KEY" = "change-me-in-production" ] || [ -z "$SECRET_KEY" ]; then\n  export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")\nfi\nexec udr "$@"\n' > /usr/local/bin/udr-entrypoint.sh && chmod +x /usr/local/bin/udr-entrypoint.sh

EXPOSE 8000

USER udr
WORKDIR /home/udr

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

ENTRYPOINT ["/usr/local/bin/udr-entrypoint.sh"]
CMD ["--help"]
