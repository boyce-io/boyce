# Plan: Block 1 — Ship It
**Status:** Active — Phase A complete, Phase B in progress
**Created:** 2026-02-28
**Updated:** 2026-03-13
**Depends on:** Block 0 (naming) — COMPLETE

## Goal
Published on PyPI, deployed on a real warehouse, discoverable by agents and developers.
The world can `pip install boyce` and have a working semantic protocol + safety layer
for their database in under 5 minutes.

**Hard requirement:** Will personally tests all surfaces before anything is published
or submitted to any public directory. This is not optional polish — it is the gate.

---

## Phase A — Engineering [COMPLETE as of 2026-03-07]

All engineering work done. No open items.

- [x] Rename codebase (all imports, CLI, pyproject.toml, docs → `boyce`)
- [x] Secure namespace (PyPI 0.0.1 placeholder, GitHub org `boyce-io`, domain `boyce.io`)
- [x] 7 MCP tools: `ingest_source`, `ingest_definition`, `get_schema`, `ask_boyce` (tri-modal Mode A/B/C), `validate_sql`, `query_database`, `profile_data`
  - `build_sql` and `solve_path` internalized (not MCP tools; host LLM constructs StructuredFilter and calls `ask_boyce` Mode A)
- [x] `boyce-init` setup wizard (auto-detects and configures **6 platforms**: Claude Desktop, Cursor, Claude Code, VS Code, JetBrains/DataGrip, Windsurf)
- [x] Direct CLI (`boyce ask "..."` and `boyce chat "..."`)
- [x] HTTP API (`boyce serve --http`, Starlette + Bearer auth, `/chat` intent routing)
- [x] Public API exports (`from boyce import process_request, SemanticSnapshot, lint_redshift_compat, SemanticGraph`)
- [x] `src` layout migration (`boyce/src/boyce/`) — CWD namespace conflict eliminated
- [x] Client reference strip + git history squash — repo is sterile
- [x] Pre-commit hook active (blocks sensitive terms from future commits)
- [x] 289 tests passing (~10s, zero external dependencies); 17 CLI smoke checks

---

## Phase B — Testing Sprint [ACTIVE — week of March 9]

**Model assignments:** Prep work is Sonnet. Testing is Will. Live fixes during testing are Sonnet.

### Mon-Tue March 9-10 — Claude Code prep

- [x] Integration guides written and verified:
  - Claude Desktop (`claude_desktop_config.json` snippet, 3 steps)
  - Cursor (`.cursor/mcp.json` config)
  - Claude Code (`.claude/settings.json` MCP config)
  - Cline (VS Code — MCP-native, Path 1, no LLM key needed)
  - Continue.dev (VS Code — same as Cline)
  - Local LLM (Ollama/vLLM via `BOYCE_PROVIDER=ollama`)
- [x] Docker Compose for Pagila operational (`docker compose up` → Postgres with 15 tables, realistic FK graph)
- [x] Validation query battery written (`boyce/tests/validation/query_battery.md`):
  - Category A: structured capability tests (simple aggregation, multi-join, NULL trap, schema exploration, dialect edge case)
  - Category B: real-world prompts by persona (junior analyst, staff engineer, non-technical stakeholder)
- [x] Testing runbook written (`boyce/tests/validation/testing_runbook.md`): what to do, in what order, what to record, how to log failures

### Fri March 13 — MCP Integration Testing (Will + Claude Code)

**Architectural overhaul completed** (10 changes from CEO/Opus directive) before testing began.

**Bugs found and fixed during testing:**
- [x] `boyce-init` wrote `.claude/settings.json` — should be `.mcp.json` for Claude Code
- [x] `ingest_source` description only listed 3 formats — host LLM couldn't find the tool for DDL files
- [x] Snapshot hash mismatch — source_path injection broke hash determinism (recompute after mutation)
- [x] `COUNT("metric_name")` — builder used alias instead of resolving field_id to column name
- [x] `GROUP BY "field:Table:Col"` — builder leaked raw field_id instead of column name
- [x] ORDER BY/LIMIT gap — added guidance in ask_boyce docstring (host LLM appends these)

**Queries tested (Mode A — StructuredFilter via Claude Code as host LLM):**
- [x] "How many products does each supplier provide?" — correct SQL (after builder fixes)
- [x] "Top 5 most expensive products and their categories" — correct SQL (ORDER BY/LIMIT noted as gap)
- [x] "Employees in London who processed orders shipped to France" — correct cross-entity WHERE + JOIN

**Still untested:**
- [ ] Multi-hop joins (3+ tables)
- [ ] Temporal filters (trailing_interval, date ranges)
- [ ] NULL trap detection (LEFT JOIN + WHERE silently becoming INNER JOIN — gap noted)
- [ ] `validate_sql` tool
- [ ] dbt and LookML parsers (only DDL tested so far)
- [ ] Live DB execution (Pagila Docker + `query_database`)
- [ ] `pip install boyce` in a clean venv

### Remaining — Version Decision + Publish

- [ ] Finish compiler testing (multi-hop, temporal, validate_sql, dbt/LookML parsers)
- [ ] Confirm NULL trap fires on demo scenario (`demo/magic_moment/`)
- [ ] Version decision: v0.1.0 (ship, iterate) or iterate further
- [ ] If go: `cd boyce && python -m build && uv publish` (Will executes)
- [ ] Verify: `pip install boyce` in a clean venv, `boyce` CLI starts, imports work

---

## Phase C — Amplification [AFTER PUBLISH]

Sequenced strictly after publish. No amplification before the product is tested and shipped.

### Content — Two Stories
**Story 1 (adoption, ICs):** "Install this. Your AI tools can now answer questions about your
database. Correctly." — Clean README, 30-second demo GIF, `pip install` as the hero action.

**Story 2 (trust, C-suite):** "Here is a specific, reproducible failure mode in AI-generated SQL.
Here is how deterministic compilation prevents it." — The Null Trap essay. Conference-talk quality.
Uses `demo/magic_moment/` as the reproducible demo — reader can run it themselves.

- [ ] Null Trap essay written (Will) + technical accuracy review (Claude Code)
- [ ] Publish: personal blog + Hacker News + dbt community + r/dataengineering + dev.to
- [ ] Integration guides published as public docs

### Directories
- [ ] Submit to Smithery (smithery.ai)
- [ ] Submit to PulseMCP (pulsemcp.com)
- [ ] Submit to mcp.so
- [ ] Submit to Glama (glama.ai)
- Positioning: "complementary safety layer" not "alternative to dbt"
- Lead with: null profiling, EXPLAIN pre-flight, deterministic SQL, protocol standard

### Block 1b — VS Code Extension
See `_strategy/plans/block-1b-vscode-extension.md`.
Starts after Phase C content and directories are done.

---

## Acceptance Criteria
- [x] Phase A: all engineering complete, 289 tests green (post-architecture-revision)
- [ ] Phase B: Will has personally tested all MCP hosts and at least 2 non-MCP surfaces
- [ ] Phase B: query battery run — results recorded, failures resolved
- [ ] Phase B: version decision made by Will on Thursday March 12
- [ ] Phase B: `pip install boyce` works in a clean environment post-publish
- [ ] Phase C: Null Trap essay published to at least 3 channels
- [ ] Phase C: listed on at least 2 MCP directories
- [ ] Phase C: all integration guides live as public docs

## Risks
- Planner may produce poor SQL on complex Pagila joins — surfaces during Phase B; fix in planner or document limitations before publish
- Version decision may push to "iterate" — Friday flex day absorbs this
- Null Trap essay reception is unpredictable — have follow-up content ideas ready
