# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- GitHub issue templates (bug report, feature request, task) (#4)
- Pull request template with merge checklist (#4)
- Pre-commit hooks for ruff, mypy, and file hygiene (#5)
- CONTRIBUTING.md, CHANGELOG.md, and MIT LICENSE (#7)
- ADR-001: Streaming architecture — SSE over WebSocket to browser (#9)
- ADR-002: HTMX over single-page application framework (#9)
- Full README with Mermaid architecture diagrams and roadmap (#8)
- Project directory structure with package init files (#1)
- .dockerignore to minimize Docker build context (#6)
- render.yaml for Render deployment (#30)
- FastAPI health endpoint at /health (#2)
- Application config via pydantic-settings (#2)
- Test fixtures with async httpx client (#3)
- Health endpoint tests (status, payload, content type) (#3)

### Changed

- Dockerfile CMD respects PORT env var for Render compatibility (#30)
- Dockerfile copies static/ directory into image (#30)
