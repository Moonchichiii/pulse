# ADR-001: Streaming Architecture — SSE over WebSocket to Browser

## Status

Accepted

## Date

2026-04-10

## Context

Pulse is a real-time market dashboard that ingests live price data from EODHD
WebSocket feeds (stocks, forex, crypto) and surfaces computed metrics to the
browser. We need to decide how the server pushes updates to the client.

The three viable options are:

1. **WebSocket (server ↔ browser)** — full-duplex, persistent connection.
2. **Server-Sent Events (SSE, server → browser)** — half-duplex, HTTP-native,
   auto-reconnect built into the EventSource API.
3. **Polling (browser → server)** — simple HTTP requests on a timer.

Meanwhile, the server must also *consume* data from EODHD, which only offers
WebSocket feeds. So the ingestion side is locked to WebSocket regardless of
this decision.

## Decision

We use **SSE (Server-Sent Events)** for all server-to-browser streaming, via
the `sse-starlette` library on top of FastAPI.

WebSocket connections are used **only** on the ingestion side (server →
EODHD), never exposed to the browser.

For data that changes slowly (e.g., the correlation matrix), we use
**HTMX polling** (`hx-get` with `hx-trigger="every 5s"`) instead of a
dedicated SSE channel.

## Architecture

```text
EODHD (WebSocket) ──► FastAPI backend ──SSE──► Browser (HTMX)
                         │                        │
                         │                        ├─ /stream/pulse (SSE)
                         │                        ├─ /stream/stress (SSE)
                         │                        └─ /fragments/corr (polling)
                         │
                         ├─ PulseStore (in-memory)
                         ├─ StressDetector → EventStore
                         └─ Correlation engine
```

## Rationale

### Why SSE over WebSocket to the browser

| Criterion | SSE | WebSocket |
|-----------|-----|-----------|
| Direction | Server → client (sufficient for dashboards) | Bidirectional |
| Protocol | Plain HTTP/1.1 or HTTP/2 | Upgrade handshake, separate protocol |
| Auto-reconnect | Built into EventSource API | Must implement manually |
| Proxy/CDN compatibility | Excellent (it is just HTTP) | Often blocked or misconfigured |
| HTMX integration | Native `sse-connect` / `sse-swap` | Requires custom JS extension |
| Complexity | Minimal — one async generator per channel | Connection lifecycle management |
| Browser support | All modern browsers | All modern browsers |

The dashboard is **read-only from the browser's perspective**. The user does
not send real-time data back to the server — they only configure filters via
standard HTTP requests (handled by HTMX `hx-get` / `hx-post`). Full-duplex
WebSocket would add complexity with no benefit.

### Why WebSocket on the ingestion side

EODHD provides real-time data exclusively via WebSocket. There is no SSE or
REST polling alternative with equivalent latency. The server maintains one
WebSocket connection per asset class (stocks, forex, crypto) in a background
daemon thread running its own asyncio event loop.

### Why polling for correlation

The correlation matrix recomputes over a 15–60 minute window and changes
slowly. A dedicated SSE channel would push redundant identical payloads.
Polling every 5 seconds with HTMX is simpler and wastes fewer resources.

## Consequences

### Positive

- The browser needs zero custom JavaScript for real-time updates — HTMX
  handles SSE natively.
- SSE connections survive proxy restarts and network blips via automatic
  reconnection.
- The server controls all rendering — it pushes ready-to-swap HTML fragments,
  not raw JSON.
- Clear separation: WebSocket is an internal implementation detail of the
  ingestion layer, invisible to the frontend.

### Negative

- SSE is unidirectional. If we ever need the browser to stream data *to* the
  server (e.g., collaborative annotations), we would need to add WebSocket
  or use standard POST requests.
- SSE over HTTP/1.1 is limited to ~6 concurrent connections per domain in
  some browsers. With only 2–3 SSE channels this is not a concern, but it
  would be if we added many more.

### Risks

- If EODHD changes their WebSocket API, the ingestion layer must be updated.
  This is isolated to `feeds.py` and does not affect the browser-facing
  architecture.

## References

- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
- [HTMX SSE Extension](https://htmx.org/extensions/sse/)
- [sse-starlette](https://github.com/sysid/sse-starlette)
- [EODHD WebSocket API](https://eodhd.com/financial-apis/real-time-api)
