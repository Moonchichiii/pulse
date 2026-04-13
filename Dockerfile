FROM python:3.12-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/

# Copy static files
COPY static/ ./static/

# Expose port
EXPOSE 8000

# Run application
CMD ["uv", "run", "uvicorn", "pulse.main:app", "--host", "0.0.0.0", "--port", "8000"]
