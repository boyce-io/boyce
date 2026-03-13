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

### Wed March 11 — Will (full day, morning start)

**Morning — Integration:**
- [ ] Run `boyce-init` — does it detect Claude Desktop / Cursor / Claude Code correctly?
- [ ] Verify MCP connection comes up in each host
- [ ] `get_schema` returns Pagila tables
- [ ] One plain-English question per host → SQL back
- [ ] Record: what broke, what was confusing, what would cause a new user to quit

**Afternoon — Query Battery (on working surfaces):**
- [ ] Run full Category A battery
- [ ] Run Category B battery (messy, conversational prompts)
- [ ] Claude Code fixes failures in real time; Will retests

### Thu March 12 — Will (full day, morning start)

**Morning:**
- [ ] Retest all failures fixed overnight
- [ ] Run any Category B queries not completed Wednesday
- [ ] Confirm NULL trap fires on the demo scenario (`demo/magic_moment/`)

**Afternoon — Decision:**
- [ ] Version decision: v1.0 (interface is stable, product works) or iterate (planner has gaps)
- [ ] If go: `cd boyce && python -m build && uv publish` (Will executes — PyPI credentials required)
- [ ] Verify: `pip install boyce` in a clean venv, `boyce` CLI starts, imports work

### Fri March 13 — Will (flex)
- [ ] Close gaps from Wed-Thu that need retesting
- [ ] Begin Phase C if published Thursday
- [ ] Open items from Wednesday/Thursday that couldn't be addressed live

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
