# syntax=docker/dockerfile:1
# LangGraph agent service. Fill the digests first:  ../scripts/pin_digests.sh
# Build (from the repo root):  docker build -t langgraph-agent:release-a langgraph_lab
FROM python:3.15-slim@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5 AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM python:3.15-slim@sha256:63bb298d2b7b88f176f51b5189f54ce6535c997682ea70885d2132f5d473a8a5
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=appuser:appuser llm.py tools.py agent_plain.py agent_graph.py api.py ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "15"]
