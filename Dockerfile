FROM python:3.12-slim@sha256:a1ac36591340dd894eca48a9b77eaa9e37b37dd6dcc4c524e1861920b1e5b359 AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Update and install security patches
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev, no editable)
RUN uv sync --frozen --no-dev --no-editable

# Copy source and static assets
COPY src/ src/
COPY static/ static/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Respect Render's PORT env var, default to 8000 locally
CMD ["sh", "-c", "uv run uvicorn pulse.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
