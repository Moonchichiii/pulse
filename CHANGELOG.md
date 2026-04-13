# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-04-13

### Added

**Infrastructure & Setup**
- Project directory structure with package init files (#1)
- FastAPI health endpoint with config and async test (#2, #3)
- GitHub issue templates (bug report, feature request, task) (#4)
- Pull request template with merge checklist (#4)
- Pre-commit hooks for ruff, mypy, and file hygiene (#5)
- .dockerignore to minimize Docker build context (#6)
- CONTRIBUTING.md, CHANGELOG.md, and MIT LICENSE (#7)
- Full README with Mermaid architecture diagrams and roadmap (#8)
- ADR-001: Streaming architecture — SSE over WebSocket to browser (#9)
- ADR-002: HTMX over single-page application framework (#9)
- render.yaml and Dockerfile PORT env var support (#30)

**Core Engine**
- Tick domain model and AssetClass enum (#11)
- EODHD WebSocket feed consumers with reconnect/backoff (#11)
- Tick parsers for stock, forex, crypto feeds (#11)
- Feed symbol config: SEK and EUR forex pairs (#11)
- PulseStore with rolling buffers, returns, volatility, trend, regime (#12)
- Background worker thread with async event loop and queue dispatcher (#13)
- Lifespan-managed worker start/stop in FastAPI app (#13)
- EventType enum (move_1m, move_5m, vol_spike) (#16)
- StressEvent frozen dataclass with factory method (#16)
- EventStore with thread-safe rolling buffer (#16)
- StressDetector with asset-aware thresholds and cooldown (#17)
- Regime-aware threshold multipliers (1.5× in high_vol) (#17)
- StressEvent carries regime tag (#18)
- Detector integration in worker dispatch loop (#18)
- Time-bucketed price alignment with forward-fill (#19)
- Return matrix builder with log-returns (#20)
- Pearson correlation function (#21)
- Regime-aware CorrelationEngine (15m high_vol / 60m normal) (#21)
- PulseStore.get_ticks() and get_stock_symbols() methods (#19)
- CorrelationEngine wired into FastAPI app (#21)

**Dashboard**
- Server-rendered UI with Jinja2 templates (#23)
- SSE streams for pulse table and stress feed (#23)
- HTMX fragments for pulse rows, stress cards, correlation table (#23)
- Tailwind CSS dark theme with consistent colors (#27)
- Alpine.js control panel with localStorage (#25)
- Top-k filter, base symbol picker, bucket size selector (#25)
- Responsive design (375px mobile → 1920px desktop) (#27)
- Skeleton loading states and smooth transitions (#27)

**Testing & Quality**
- 176 passing tests (~8s runtime) (#14, #22, #28)
- Strict mypy type checking across all modules
- Integration test suite — 4 end-to-end tests (#28)
- Zero test hangs or flakiness

**Documentation**
- Comprehensive README with badges, quick start, deployment guide (#29)
- CHANGELOG finalized for v1.0.0 (#29)

### Changed

- Dockerfile CMD respects PORT env var for Render compatibility (#30)
- Dockerfile copies static/ directory into image (#30)

[Unreleased]: https://github.com/Moonchichiii/pulse/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Moonchichiii/pulse/releases/tag/v1.0.0
