#!/usr/bin/env bash
# Looks up the current digests and writes them into the Dockerfiles and docker-compose.yml.
# Needs Docker with buildx. Read the result with `git diff` before you commit.
set -euo pipefail
cd "$(dirname "$0")/.."

PY_TAG="${PY_TAG:-3.15-slim}"
UV_TAG="${UV_TAG:-}"            # e.g. 0.13.5  (check https://github.com/astral-sh/uv/releases)
PG_TAG="${PG_TAG:-pg17}"        # pgvector/pgvector tag
CADDY_TAG="${CADDY_TAG:-2}"     # pick an exact release tag from Caddy's Docker Hub page for real use

digest() { docker buildx imagetools inspect "$1" --format '{{json .Manifest.Digest}}' | tr -d '"' | sed 's/^sha256://'; }

[ -n "$UV_TAG" ] || { echo "Set UV_TAG, e.g. UV_TAG=0.13.5 $0"; exit 1; }
PY=$(digest "python:$PY_TAG")
PG=$(digest "pgvector/pgvector:$PG_TAG")
CD=$(digest "caddy:$CADDY_TAG")

sed -i "s/<PYTHON_DIGEST>/$PY/g; s/<UV_TAG>/$UV_TAG/g" Dockerfile langgraph_lab/Dockerfile
sed -i "s/<PGVECTOR_DIGEST>/$PG/g; s/<CADDY_DIGEST>/$CD/g" docker-compose.yml
echo "python $PY"; echo "pgvector $PG"; echo "caddy $CD"
