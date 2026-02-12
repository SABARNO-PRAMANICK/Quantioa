# ─── Quantioa Base Image ─────────────────────────────────────────────────────
# Multi-stage build for smaller production images
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir build \
    && pip wheel --no-cache-dir --wheel-dir /build/wheels ".[dev]"

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

LABEL maintainer="Quantioa Team"
LABEL description="Quantioa AI Trading Platform"

# Security: non-root user
RUN groupadd -r quantioa && useradd -r -g quantioa -m quantioa

WORKDIR /app

# Install wheels from builder
COPY --from=builder /build/wheels /tmp/wheels
RUN pip install --no-cache-dir /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels

# Copy application source
COPY src/ ./src/
COPY .env.example ./.env.example

# Set PYTHONPATH
ENV PYTHONPATH=/app/src
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Switch to non-root
USER quantioa

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import quantioa; print('ok')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "quantioa.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
