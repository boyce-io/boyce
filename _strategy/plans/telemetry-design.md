# Plan: Telemetry Architecture
**Status:** Planned — Stage 4 post-publish
**Created:** 2026-03-17
**Depends on:** PyPI publish complete

## Goal
Instrument telemetry hooks in the codebase that ship dark (off by default).
No data collection at launch. Architecture in place so telemetry can be
activated in a future release with a privacy policy and lightweight backend.

---

## CEO Decision (2026-03-17)

Telemetry will follow the Homebrew / Terraform / Ruff model:
- Opt-in only. Never default on. `BOYCE_TELEMETRY=on` to activate.
- Aggregate counts only. Never query content, schema content, or SQL.
- Ship hooks now, ship collection later.

## What Gets Instrumented (hooks only — no transmission)

| Signal | Where | Why |
|--------|-------|-----|
| Tool invocation count | `server.py` (each MCP tool) | Usage patterns — which tools matter |
| Error class | `server.py` (exception handlers) | Debug triage without stack traces |
| Platform identifier | `server.py` (detect MCP host) | Platform coverage — where users are |
| Parser type used | `parsers/` (on successful parse) | Which parsers matter for prioritization |
| Dialect selected | `kernel.py` | Which databases users target |

## What Never Gets Collected (hard constraints)

- Query content (NL or SQL)
- Schema content (table names, column names, data)
- Database connection strings or credentials
- File paths or directory structure
- User identity (no tokens, no IPs, no fingerprints)
- Stack traces with user paths

## Implementation

### Phase 1 — Hooks (Stage 4, this sprint)
- Add `_telemetry.py` module with a `record()` function
- `record()` checks `BOYCE_TELEMETRY` env var — if not `on`, returns immediately (no-op)
- Call `record()` at each instrumentation site in `server.py`
- No backend, no storage, no network calls
- Tests verify that `record()` is a no-op when env var is absent

### Phase 2 — Collection (future, requires CEO approval)
- Privacy policy written and published on convergentmethods.com
- Lightweight backend (Cloudflare Worker + R2 bucket or similar)
- `boyce init` mentions telemetry opt-in during setup
- `boyce telemetry status` CLI command shows what would be sent
- Aggregate dashboard for CEO visibility

## Acceptance Criteria (Phase 1 only)
- [ ] `_telemetry.py` exists with `record()` function
- [ ] `record()` is no-op when `BOYCE_TELEMETRY` is unset or not `on`
- [ ] Call sites added in `server.py` for all 7 MCP tools
- [ ] No network calls, no file writes, no side effects when off
- [ ] Tests confirm no-op behavior
