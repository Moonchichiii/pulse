# Contributing to Pulse

Thank you for considering contributing to Pulse! This document explains how
to get started.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [Docker](https://www.docker.com/) (optional, for container builds)
- [gh CLI](https://cli.github.com/) (optional, for GitHub workflow)

## Setup

```bash
git clone https://github.com/Moonchichiii/pulse.git
cd pulse
uv sync --dev
uv run pre-commit install
```

## Development workflow

1. **Pick an issue** — check the
   [issue board](https://github.com/Moonchichiii/pulse/issues) and assign
   yourself.

2. **Create a branch** from `main`:

   ```bash
   git checkout main && git pull origin main
   git checkout -b feat/<issue-number>-short-description
   ```

   Branch prefixes:
   - `feat/` — new features or infrastructure
   - `fix/` — bug fixes
   - `docs/` — documentation only

3. **Write code** — follow the existing style. All Python code must:
   - Pass `ruff check` and `ruff format`
   - Pass `mypy --strict`
   - Have tests (unless docs/config only)

4. **Run checks locally**:

   ```bash
   uv run ruff check src/ tests/
   uv run ruff format --check src/ tests/
   uv run mypy src/
   uv run pytest -v --tb=short
   ```

5. **Commit** — use
   [Conventional Commits](https://www.conventionalcommits.org/):

   ```text
   feat: add WebSocket reconnect logic
   fix: correct volatility window calculation
   docs: update architecture diagram
   ```

6. **Push and open a PR** against `main`. Fill in the PR template completely.

7. **CI must pass** before merge. All PRs are squash-merged.

## Project structure

```text
src/pulse/       — application source code
tests/           — pytest test suite
docs/            — architecture docs and ADRs
static/          — CSS and static assets
```

## Code style

- **Formatter:** ruff format (line length 80)
- **Linter:** ruff check with select rules (E, F, I, N, UP, B, SIM, TCH)
- **Type checker:** mypy strict mode
- **Pre-commit hooks** enforce all of the above automatically

## Running the app

```bash
uv run uvicorn pulse.main:app --reload --port 8000
```

Or with Docker:

```bash
docker compose up --build
```

## Questions?

Open a [discussion](https://github.com/Moonchichiii/pulse/issues) or reach
out via an issue.
