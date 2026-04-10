# ADR-002: HTMX over Single-Page Application Framework

## Status

Accepted

## Date

2026-04-10

## Context

Pulse needs a browser UI that displays real-time streaming data (price tables,
event feeds) and supports user interactions (selecting symbols, adjusting
parameters). We need to decide the frontend approach.

The options considered:

1. **SPA framework (React / Vue / Svelte)** — client-side rendering, JSON
   APIs, JS build toolchain.
2. **HTMX + server-side rendering** — server returns HTML fragments, HTMX
   swaps them into the DOM, no JS build step.
3. **Vanilla JS + fetch** — manual DOM manipulation, no framework.

## Decision

We use **HTMX** (14 KB, served from CDN) combined with **Jinja2 server-side
rendering** for all UI updates. Alpine.js (15 KB) is permitted as an optional
addition for client-side-only interactions like dropdown toggles and tab
switches.

There is **no JavaScript build step**. No `node_modules`. No bundler. No
framework.

## Rationale

### The core thesis

> You don't need a JavaScript SPA framework to build a real-time dashboard.
> The server owns all state and computation. The browser receives
> ready-to-render HTML fragments.

This project exists to prove this thesis. Choosing an SPA would contradict the
project's purpose.

### Technical comparison

| Criterion | SPA (React) | HTMX + Jinja2 |
|-----------|-------------|----------------|
| State ownership | Duplicated (server + client) | Server only |
| Real-time updates | Custom WebSocket handlers + state merge | `sse-swap` attribute |
| Build toolchain | Node, Vite/Webpack, npm | None |
| Bundle size | 40–150 KB min (framework) | 14 KB (HTMX CDN) |
| Type safety | TypeScript required for safety | Python types (mypy strict) |
| SEO / initial load | Requires SSR/hydration | Server-rendered by default |
| Developer count | 1 (this is a solo project) | 1 |
| Debugging | Browser DevTools + React DevTools | Browser DevTools only |

### Why HTMX fits this project specifically

1. **All computation is server-side.** Returns, volatility, regime detection,
   and correlation are computed in Python. An SPA would receive JSON and
   re-render — HTMX receives the final `<tr>` or `<div>` and swaps it in.

2. **SSE is a first-class HTMX feature.** The `sse-connect` and `sse-swap`
   attributes handle the entire real-time pipeline declaratively:

   ```html
   <div hx-ext="sse" sse-connect="/stream/pulse">
     <tbody sse-swap="pulse" hx-swap="innerHTML">
       <!-- rows appear here -->
     </tbody>
   </div>
