# Plan: Init Wizard Overhaul
**Status:** COMPLETE. Build done, acceptance criteria verified via Cursor cross-platform testing (2026-03-23).
**Created:** 2026-03-16
**Updated:** 2026-03-16

---

## Problem
`boyce init` was jargon-heavy, non-interactive, and left users with broken configs.

## Goal
After `boyce init`: editor wired, database connected, schemas loaded. First question just works.

---

## Build Progress — ALL STEPS COMPLETE

- [x] Step 0: `wizard = ["questionary>=2.0"]` optional dep
- [x] Step 1: `_resolve_boyce_command()` returns full path (critical bug fix)
- [x] Step 2: Full `init_wizard.py` rewrite — 3-step flow, questionary + fallback
- [x] Step 3: Editor detection (Cursor app, `~/.cursor/`, `code` on PATH, etc.)
- [x] Step 4: DB connection (field-by-field, paste URL, asyncpg test, retry)
- [x] Step 5: `discovery.py` new module + auto-discovery in wizard
- [x] Step 6: "Something else" manual config instructions
- [x] Step 7: CLI smoke tests updated
- [x] Opus review: 6 issues found and fixed
- [x] CLI convention: `boyce init` / `boyce scan` subcommands
- [x] Discovery→ingestion bug: `_resolve_parse_path()` for Django/SQLAlchemy/Prisma
- [x] Nested LookML false-positive fix
- [x] Test fixtures: `airflow_analytics/` + `sample_sqlite/`
- [x] `test_discovery.py`: 27 automated tests

Commits: `35edfa5`, `428d4bb`, `7a8577e`, `7e96bbe`

---

## Remaining Acceptance Criteria

1. [x] Wizard end-to-end: install → configure editors → connect DB → discover sources → summary
2. [x] Install/uninstall cycle: `pip uninstall boyce && pip install boyce` → wizard identical results

---

## Files Modified

| File | Change |
|---|---|
| `boyce/pyproject.toml` | `wizard = ["questionary>=2.0"]` optional dep |
| `boyce/src/boyce/init_wizard.py` | Full rewrite — 3-step flow, questionary + fallback |
| `boyce/src/boyce/discovery.py` | NEW — data source auto-discovery logic |
| `boyce/src/boyce/cli.py` | `init` and `scan` subcommands |
| `boyce/src/boyce/scan.py` | argparse prog fix |
| `boyce/tests/test_cli_smoke.py` | 20 smoke checks (4 new) |
| `boyce/tests/test_discovery.py` | NEW — 27 tests |

## Files NOT Modified
- `server.py`, `kernel.py`, `builder.py` — no changes
- Parser files — used as-is via registry
- `store.py` — used as-is

---

## Next Steps (as of 2026-03-16)

1. **Database Object Selection** — Opus Chat: which 3-4 additional real-world data source types for `test_warehouses/`?
2. **SQL Regression Test Suite** — 20-30 Mode A test cases against known snapshots
3. **Wizard Interactive Walkthrough** — Steps 2 (DB) and 3 (data sources) live testing
4. **Platform Integration Tests** — `boyce init` → MCP → query on Claude Code, Cursor, VS Code, JetBrains
5. **Publish Gate** — all above pass → version decision → PyPI
