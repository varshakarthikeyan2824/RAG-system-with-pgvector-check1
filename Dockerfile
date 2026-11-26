# syntax=docker/dockerfile:1
# RAG app image. Fill the digests first:  ./scripts/pin_digests.sh
# Build:  docker build -t water-rag:release-a .
# Both stages use the SAME path (/app) so the venv's script paths stay valid after COPY.

# --- stage 1: install the libraries -----------------------------------------------------
FROM python:3.15-slim@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# --- stage 2: the small image that runs ---------------------------------------------------
FROM python:3.15-slim@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser templates ./templates
COPY --chown=appuser:appuser static ./static
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER appuser
EXPOSE 8000
# No curl in slim images: a short Python call. /health = alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# exec form: uvicorn receives SIGTERM and shuts down cleanly.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
