# ─── API Gateway Dockerfile ──────────────────────────────────────────────────
# The gateway routes requests to internal services and handles
# rate limiting, CORS, and request logging.

FROM python:3.11-slim

LABEL maintainer="Quantioa Team"

RUN groupadd -r quantioa && useradd -r -g quantioa -m quantioa

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "."

ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER quantioa

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); r.raise_for_status()" || exit 1

EXPOSE 8000

CMD ["uvicorn", "quantioa.services.gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
