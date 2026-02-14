# ─── Generic Microservice Dockerfile ─────────────────────────────────────────
# Used by: auth, trading-engine, data, risk, ai, analytics, broker services
# The SERVICE_MODULE env var determines which service to start.

FROM python:3.11-slim

LABEL maintainer="Quantioa Team"

RUN groupadd -r quantioa && useradd -r -g quantioa -m quantioa

WORKDIR /app

# Copy everything needed for pip install (pyproject.toml needs README.md + src/)
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "."

ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER quantioa

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); r.raise_for_status()" || exit 1

EXPOSE 8000

# SERVICE_MODULE is set per-service in docker-compose.yml
# e.g. SERVICE_MODULE=quantioa.services.auth.main
CMD ["sh", "-c", "uvicorn ${SERVICE_MODULE}:app --host 0.0.0.0 --port 8000"]
