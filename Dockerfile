# Dockerfile for isolated test runs of the Art of Agents companion.
# Mirrors the Linux CI path. Mac and Windows developers use this to reproduce
# the exact environment the book targets.
#
# Build:   docker build -t aoa-companion .
# Run all: docker run --rm aoa-companion
# Shell:   docker run --rm -it --entrypoint bash aoa-companion
#
# No API keys required. Every example in the book's companion runs offline.

FROM python:3.14-slim-bookworm AS base

# Pinned to the uv version the book targets. Bump this as a deliberate choice.
ARG UV_VERSION=0.11.7
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_LINK_MODE=copy

# uv replaces pip for speed and reproducibility. Single binary, no Python
# dependency of its own, identical behaviour on Linux, macOS, and Windows.
# build-essential stays in the image: a handful of April 2026 libraries
# (scikit-network via ragas, some native extensions in pandas 3.x) still
# compile on install. Removing the toolchain after install saves ~200MB but
# breaks `uv pip install` for users who extend the image. Keep it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
    && curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt pyproject.toml ./
RUN uv pip install --system -r requirements.txt

# Copy the source last so code edits don't invalidate the dep layer.
COPY . .

# Smoke test runs both solved chapters on build. Fails fast if deps break.
RUN python chapters/01-laying-plans/run-eval.py \
    && python chapters/02-waging-war/run-eval.py

# Default: run the whole suite.
ENTRYPOINT ["python", "scripts/run_all.py"]
