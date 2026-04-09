FROM python:3.12-slim@sha256:c4a7c0f9b8c8e3b3f3e3b3f3e3b3f3e3b3f3e3b3f3e3b3f3e3b3f3e3b3f3e3 AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Update and install security patches
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock ./

# Install production deps only (no dev, no editable)
RUN uv sync --frozen --no-dev --no-editable

# Copy source
COPY src/ src/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Run through uv so it picks up the venv
CMD ["uv", "run", "uvicorn", "pulse.main:app", "--host", "0.0.0.0", "--port", "8000"]
