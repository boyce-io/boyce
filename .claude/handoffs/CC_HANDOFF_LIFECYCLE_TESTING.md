# Handoff: Lifecycle Testing & Version Management

**From:** Opus session (pre-publish finalization, 2026-03-23)
**To:** Fresh Opus for architectural review before implementation

---

## Context

We're in Phase 1 (Pre-Publish Finalization). All code is committed, tests green (395/6), 8 surfaces refreshed, clean venv install verified, packaging fix landed. The last technical gate is the Cursor cross-platform test.

During Cursor test setup, Will identified a critical **experience bug**: there is no mechanism for a user to discover or apply Boyce upgrades. A non-Python user who installed Boyce months ago has no way to know v0.2.0 exists, and no agentic path to upgrade. This is a bounce reason — a bug in the broadest sense.

## What Exists Today

- **Install:** `pip install boyce` → `boyce init` → MCP config written with `"command": "boyce"` (bare name on PATH). Works.
- **Daily use:** MCP host spawns `boyce` on stdio each session. Automatic. Works.
- **Upgrade:** Nothing. User must manually know to run `pip install --upgrade boyce`. No version check, no notification, no self-update.
- **`check_health` MCP tool:** Already exists. Returns DB connectivity, snapshot freshness, suggestions. Natural home for version check.
- **`environment_suggestions`:** First-call-per-session advertising field. Already exists in `_build_advertising_layer()`. Natural home for upgrade nudge.
- **`boyce doctor` CLI:** Already exists. 5 check functions. Natural home for version check on CLI side.

## Proposed Plan

### 1. PyPI Version Check (agentic upgrade discovery)

**Where:** New utility function, wired into `check_health`, `environment_suggestions`, and `boyce doctor`.

**Mechanism:**
- Hit `https://pypi.org/pypi/boyce/json` → `.info.version`
- Compare against `boyce.__version__`
- Cache result per session (don't hit PyPI on every tool call)
- Non-blocking, non-fatal (if PyPI unreachable, skip silently)
- Timeout: 2-3 seconds max

**In `check_health` response:**
```json
{
  "version": {"current": "0.1.0", "latest": "0.2.0", "update_available": true},
  "suggestions": ["Boyce 0.2.0 is available. Run `boyce update` to upgrade."]
}
```

**In `environment_suggestions` (first-call-per-session):**
```json
{
  "environment_suggestions": ["Boyce 0.2.0 available — run `boyce update` to upgrade."]
}
```

**In `boyce doctor` CLI output:**
```
Version .............. 0.1.0 (0.2.0 available — run `boyce update`)
```

### 2. `boyce update` Subcommand (agentic self-update)

**What:** CLI command that upgrades Boyce in place.

**Mechanism:**
- Detect installation method:
  - `pipx` environment → `pipx upgrade boyce`
  - `uv` on PATH → `uv pip install --upgrade boyce`
  - Fallback → `pip install --upgrade boyce`
- Report old → new version
- Handle errors (permissions, network, etc.)
- Exit codes: 0 (success), 1 (already latest), 2 (error)

**Agentic flow:**
Agent calls `check_health` → sees "update available" → tells user → user approves → agent runs `boyce update` via shell → done. Or user runs `boyce update` themselves from terminal.

### 3. CLI Contract Updates

- Add `boyce update` to cli.py `_parse_args()` and `main()`
- Add smoke tests to `test_cli_smoke.py`
- Update help text / usage string

## Files to Touch

**New or heavily modified:**
- `boyce/src/boyce/version_check.py` (new — PyPI check + install method detection + update logic)
- `boyce/src/boyce/cli.py` (add `update` subcommand)
- `boyce/src/boyce/server.py` (wire version check into `check_health` and `environment_suggestions`)
- `boyce/src/boyce/doctor.py` (wire version check into doctor output)

**Tests:**
- `boyce/tests/test_cli_smoke.py` (add `update` smoke tests)
- `boyce/tests/test_doctor.py` (add version check test)
- Possibly new `boyce/tests/test_version_check.py`

## Questions for Opus Review

1. **Is `version_check.py` the right module boundary?** Or should this live in `doctor.py` since doctor already does health checks?

2. **Should the version check be async?** `check_health` is async, `boyce doctor` runs in asyncio. But `environment_suggestions` fires inside sync tool functions. We might need both sync and async paths, or use a thread pool.

3. **How aggressive should the upgrade nudge be?** Options:
   - Only in `check_health` (user/agent must ask)
   - In `environment_suggestions` first-call-per-session (proactive but once)
   - In `present_to_user` on every response when outdated (aggressive)

   Current proposal: `check_health` + `environment_suggestions` (proactive but not noisy).

4. **Should `boyce update` verify the upgrade worked?** i.e., after running pip/uv upgrade, import the new version and confirm it changed? Or just run the command and trust it?

5. **Any other lifecycle friction points we're missing?** Think about: first-time user with no Python experience, user who installed 6 months ago, user switching editors, user with multiple projects.

## What NOT to Build

- Auto-update (runs without user consent) — NO. Security and trust issue.
- Update check on every tool call — NO. Latency and noise.
- Complex installer (homebrew formula, .pkg, etc.) — post-publish.

---

## Read These Files for Full Context

Core architecture:
- `boyce/src/boyce/server.py` — MCP tools, advertising layer, `_build_advertising_layer()`, `check_health`
- `boyce/src/boyce/doctor.py` — 5 check functions, `run_doctor()`
- `boyce/src/boyce/cli.py` — subcommand dispatch, `_parse_args()`, `main()`
- `boyce/src/boyce/__init__.py` — `__version__`
- `boyce/src/boyce/connections.py` — ConnectionStore (for understanding the _local_context pattern)

Tests:
- `boyce/tests/test_cli_smoke.py` — CLI contract registry
- `boyce/tests/test_doctor.py` — doctor check tests

Strategy:
- `_strategy/MASTER.md` (offset 278+) — execution plan, advertising layer docs
- `ROADMAP.md` — current phase
