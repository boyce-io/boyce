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

**Additional bugs found and fixed (session 2 — March 13 evening):**
- [x] `temporal_filters` at StructuredFilter top level dropped — never passed to WHERE builder (commits `9ee8008`)
- [x] `ask_boyce` docstring missing `date_trunc_field`/`date_trunc_unit` guidance — host LLM didn't know about it
- [x] LookML parser: directory ingest failed — `detect()` only matched files, not directories
- [x] LookML parser: model file produced 0 entities — `include` directives not followed; fix: parse all `.lkml` files in dir and merge
- [x] LookML join builder: used explore base_view instead of sql_on src_view for source_entity/field → validation failure
- [x] `ingest_source` (source_path path) didn't validate snapshot before saving — silent invalid snapshots possible

**All compiler tests passing (session 2):**
- [x] Multi-hop joins (3+ tables) — order_items → inventory_items → products ✅
- [x] Temporal filters (DATE_TRUNC + between filter for 1997) ✅
- [x] `validate_sql` tool (unchecked without DB = correct) ✅
- [x] dbt parser — jaffle_shop ingested, LTV SQL correct ✅
- [x] LookML parser — thelook_lookml directory ingested (5e/53f/6j), revenue by brand SQL correct ✅
- [x] NULL trap demo (`demo/magic_moment/verify_demo.py`) — both dangers fire, all assertions pass ✅

**Additional bugs found and fixed (session 3 — March 13 late evening):**
- [x] `safety.py` missing 4 Redshift lint rules: CONCAT, STRING_AGG, FILTER(WHERE), RECURSIVE CTE
- [x] `concept_map.fields` ignored in SELECT — builder fell back to `SELECT *` for raw queries (no dimensions/metrics); fix: use fields for projection
- [x] Filter operator aliases rejected — `NOT_IN`, `IS_NULL`, `IS_NOT_NULL` etc. normalized to SQL spacing at both validator and builder
- [x] Django parser FK target resolution used class_name.lower() — diverged from db_table override (e.g. "Customer" → "customer" vs entity registered as "customers")

**All compiler tests passing (session 3 — 6 consecutive passes, no new failures):**
- [x] LIKE filter — correct SQL, `concept_map.fields` projection fix verified ✅
- [x] NOT_IN alias (`NOT_IN` → `NOT IN`) + fields projection — `SELECT "EmployeeID", "LastName", "FirstName", "City"` correct ✅
- [x] policy_context.resolved_predicates injection — verbatim, correct ordering, composable with empty filters ✅
- [x] validate_sql CONCAT lint detection — compat_risks populated correctly ✅
- [x] Django models parser — 5e/31f/5j, all FK joins resolved to correct db_table targets ✅
- [x] Northwind DDL (13e/88f/8j) — 8 core tables clean; 5 dbo-schema tables degrade silently (T-SQL bracket notation — noted, not blocking) ✅

**Total: 13 bugs found and fixed across 3 sessions. 289 tests green throughout.**

**Additional bugs found and fixed (session 4 — March 13 late night):**
- [x] `concept_map.fields` ignored in SELECT — builder fell back to `SELECT *` with no dimensions/metrics; fix: use fields[] for projection
- [x] Filter operator aliases rejected — `NOT_IN`, `IS_NULL`, `IS_NOT_NULL` not normalized to SQL spacing at validator + builder
- [x] Django parser FK target_table used `class_name.lower()` — diverged from `db_table` override; fix: first-pass `class_to_table` map
- [x] `SemanticSnapshot.find_join_path` unidirectional — BFS blocked all M:N junction table queries (film_category, film_actor etc.); fix: bidirectional BFS with reversed JoinDef objects

**New capability (session 4):**
- [x] `ingest_source` now accepts live PostgreSQL DSNs (`postgresql://...`) — introspects schema via PostgresAdapter + FK constraints → SemanticSnapshot. `query_database` + `profile_data` were already live.

**Live DB round-trip — PASSING (Pagila Docker):**
- [x] `ingest_source("postgresql://boyce:password@localhost:5433/pagila")` → 29e/171f/36j ✅
- [x] `ask_boyce` Mode A — 6-entity join chain through junction table (film_category) → SQL verified ✅
- [x] `query_database` — real results returned (Documentary $531.70 top revenue category) ✅
- [x] `profile_data` — `rental.return_date`: 183 nulls / 1.14% ✅

**`pip install boyce` in clean venv — PASSING:**
- [x] `uv venv /tmp/boyce-cleantest && uv pip install -e boyce/` → 69 packages, no errors ✅
- [x] `/tmp/boyce-cleantest/bin/boyce --help` → CLI starts ✅
- [x] Public API imports (`process_request`, `SemanticSnapshot`, `lint_redshift_compat`, `SemanticGraph`) → OK ✅
- [x] `verify_eyes.py` → 15/15 ✅

**Total: 15 bugs found and fixed across 4 sessions. 289 tests green throughout.**
**Commit pushed: `63ddeaa` — all session 3-4 fixes + live DB ingest feature.**

**Additional bugs found and fixed (session 5 — March 14 early morning):**
- [x] Bug 16: `COUNT_DISTINCT` emitted verbatim — fixed in `builder.py`
- [x] Bug 17: Stale definitions survive snapshot overwrite — `DefinitionStore.clear()` added, called on save
- [x] Bug 18: DDL directory not handled — `DDLParser.detect()/parse()` extended for directories
- [x] Bug 18b: UTF-8 BOM breaks T-SQL DDL parsing — stripped at top of `_parse_ddl_sql()`
- [x] Bug 18c: Bracket-quoted multi-word column names misparse — `_extract_col_name_and_rest()` added
- [x] NULL trap warning: int filter value rendered as '1' not 1 — fixed with `repr()`
- [x] Doc discrepancies: 4 files updated (tool counts, build_sql/solve_path references removed)

**Battery 4 complete (session 5 — all 8 tests run):**
| Test | Result |
|------|--------|
| 1 Prisma parser | ✅ PASS |
| 2 SQLAlchemy parser | ✅ PASS |
| 3 Multiple dims + COUNT_DISTINCT | ✅ PASS (Bug 16 fixed) |
| 4 Redshift dialect | ✅ PASS |
| 5 solve_path | ✅ N/A (internal only, by design) |
| 6 Snapshot overwrite | ✅ PASS (Bug 17 fixed) |
| 7 WWI DDL directory | ✅ PASS (Bugs 18/18b/18c fixed) |
| 8 NULL trap on live DB | ✅ PASS (fires at 100% NULLs, threshold=5%) |

**Total: 21 bugs found and fixed across 5 sessions. 289 tests green throughout.**
**Commits pushed: `725c85f` → `6313744`**

**Battery 5 COMPLETE (session 6 — March 14):**

| # | Test | Result |
|---|---|---|
| 1 | Column collision: multi-join SELECT | ✅ BUG 22 found + fixed |
| 2 | Filter on non-joined entity | ✅ BUG 23 found + fixed |
| 3 | Multi-metric (SUM + COUNT + AVG) | ✅ PASS |
| 4 | validate_sql with valid SQL | ✅ PASS |
| 5 | validate_sql with invalid SQL | ✅ PASS |
| 6 | query_database write rejection | ✅ PASS |
| 7 | ingest_definition lifecycle | ✅ PASS |
| 8 | ask_boyce with bad field_id | ✅ PASS |
| 9 | Multiple filters (4 AND conditions) | ✅ PASS |
| 10 | 3-entity join GROUP BY qualification | ✅ PASS |

- [x] Bug 22: `_build_select_clause` emitted bare field names for dimensions — no table qualification, alias on collision. Fixed in builder.py (SELECT + GROUP BY + metrics).
- [x] Bug 23: `_validate_structured_filter` did not check filter `entity_id` vs join scope — filter on non-joined entity produced invalid SQL. Fixed: validator now rejects out-of-scope filter entities with actionable error.

**Total: 23 bugs found and fixed across 6 sessions. 289 tests green. Commit: `1113d22`**

**Decision gate after Battery 5: 2 bugs found → Battery 6 required (gate was ≤1).**

**Opus refactor (pre-Battery 6):**
- [x] Extracted `_resolve_field_ref()` — single helper replacing 6 inline field resolution sites (116 lines)
- [x] Extracted `_resolve_grouping_field()` — static helper for GROUP BY field mapping
- [x] Refactored `_build_select_clause`, `_render_filter_def`, `_build_group_by_clause` through helpers
- [x] Deleted dead code: `_build_from_clause` + `_build_join_clauses` (66 lines, never called)
- [x] Proactive fix: concept_map.fields collision bug (same gap as Bug 22 in fields[] path)
- [x] Net: -94 lines (164 added, 258 removed). Commit: `ec8bd15`

**Battery 6 — 4 tests (Test 1 eliminated by proactive fix in refactor):**

| # | Test | Result |
|---|---|---|
| 1 | IN operator with list value | ✅ PASS — `IN ('PG', 'PG-13', 'R')`, table-qualified, EXPLAIN verified |
| 2 | Redshift dialect lint via validate_sql | ✅ PASS — compat_risks: CONCAT() flagged correctly |
| 3 | NULL trap on equality filter | ✅ PASS — film.original_language_id 100% NULL (1000/1000), warning fired |
| 4 | Mode C fallback (NL, no credentials) | ✅ BUG 24 found + fixed + re-test verified |

- [x] Bug 24: Auth errors (litellm.AuthenticationError) hit generic Exception handler instead of Mode C fallback. Fix: check exception class name for Auth/Permission → route to `_build_schema_guidance()`. Commit: `fb37f6b`

**Decision gate after Battery 6: 1 bug found → fixed → re-test passed → proceed to Cursor.**

**Total: 24 bugs found and fixed across 7 sessions. 289 tests green. Commits: `ec8bd15` → `fb37f6b`**

**Remaining for publish:**
- [x] Battery 6 (4 tests — complete)
- [ ] Cursor cross-platform (must-have for publish gate)
- [ ] VS Code cross-platform (stretch)
- [ ] Version decision + publish

### Tonight (March 13 late) — Close Remaining Gates

- [x] Finish compiler testing on Claude Code — 20 tests, 6 consecutive passes, all green
- [x] Confirm NULL trap fires on demo scenario (`demo/magic_moment/`) — both dangers fire, all assertions pass
- [x] `pip install boyce` in clean venv — PASSED
- [x] Live DB round-trip (Pagila Docker + `query_database` + `profile_data` + `ingest_source` via MCP) — PASSED
- [x] Commit + push all session fixes (15 bugs + live DB ingest)

### Tomorrow (March 14) — Cursor + Version Decision + Publish

- [ ] Test on **Cursor** (must-have): boyce-init → MCP connection → 2+ queries — hard gate for publish
- [ ] Test on **VS Code** (stretch): boyce-init → MCP connection → 1+ query (uses `"servers"` key)
- [ ] Version decision: v0.1.0 (ship, iterate) or iterate further — after Cursor passes
- [ ] If go: version bump in `pyproject.toml`, `cd boyce && python -m build && uv publish` (Will executes)
- [ ] Verify: `pip install boyce` from PyPI in a fresh venv, `boyce` CLI starts, imports work

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
- [ ] Phase B: Will has personally tested Claude Code + Cursor (must-have), VS Code (stretch)
- [x] Phase B: query battery run — 20 tests recorded, 13 bugs resolved, 6 consecutive clean passes
- [ ] Phase B: version decision — after Cursor test passes (target: March 14)
- [ ] Phase B: `pip install boyce` works in a clean environment (pre-publish: tonight; post-publish: after PyPI upload)
- [ ] Phase C: Null Trap essay published to at least 3 channels
- [ ] Phase C: listed on at least 2 MCP directories
- [ ] Phase C: all integration guides live as public docs

## Risks
- Planner may produce poor SQL on complex Pagila joins — surfaces during Phase B; fix in planner or document limitations before publish
- Version decision may push to "iterate" — Friday flex day absorbs this
- Null Trap essay reception is unpredictable — have follow-up content ideas ready
