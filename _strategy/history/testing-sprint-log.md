# Block 1 Phase B — Testing Sprint Log

**Archived:** 2026-03-16
**Source:** Extracted from `MASTER.md` and `block-1-ship-it.md` to reduce CC context window load.
**Period:** 2026-03-09 through 2026-03-16 (7 testing sessions)

---

## Summary

- **24 bugs found and fixed** across 7 sessions
- **316 tests, 20 CLI smoke checks**, all green
- **Gates passed:** Claude Code (6 consecutive clean passes), live DB round-trip (Pagila), clean venv install, NULL trap demo
- **Opus refactor** (pre-Battery 6): extracted `_resolve_field_ref()`, eliminated root cause of 5 builder bugs, net -94 lines
- **Remaining gate:** Cursor cross-platform test (last must-have before version decision)

---

## Session 1 — March 13 PM (MCP Integration)

**Bugs found and fixed:**
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

## Session 2 — March 13 Evening

**Bugs found and fixed:**
- [x] `temporal_filters` at StructuredFilter top level dropped — never passed to WHERE builder (commit `9ee8008`)
- [x] `ask_boyce` docstring missing `date_trunc_field`/`date_trunc_unit` guidance — host LLM didn't know about it
- [x] LookML parser: directory ingest failed — `detect()` only matched files, not directories
- [x] LookML parser: model file produced 0 entities — `include` directives not followed; fix: parse all `.lkml` files in dir and merge
- [x] LookML join builder: used explore base_view instead of sql_on src_view for source_entity/field → validation failure
- [x] `ingest_source` (source_path path) didn't validate snapshot before saving — silent invalid snapshots possible

**Tests passing (after fixes):**
- [x] Multi-hop joins (3+ tables) — order_items → inventory_items → products
- [x] Temporal filters (DATE_TRUNC + between filter for 1997)
- [x] `validate_sql` tool (unchecked without DB = correct)
- [x] dbt parser — jaffle_shop ingested, LTV SQL correct
- [x] LookML parser — thelook_lookml directory ingested (5e/53f/6j), revenue by brand SQL correct
- [x] NULL trap demo (`demo/magic_moment/verify_demo.py`) — both dangers fire, all assertions pass

## Session 3 — March 13 Late Evening

**Bugs found and fixed:**
- [x] `safety.py` missing 4 Redshift lint rules: CONCAT, STRING_AGG, FILTER(WHERE), RECURSIVE CTE
- [x] `concept_map.fields` ignored in SELECT — builder fell back to `SELECT *` for raw queries (no dimensions/metrics); fix: use fields for projection
- [x] Filter operator aliases rejected — `NOT_IN`, `IS_NULL`, `IS_NOT_NULL` etc. normalized to SQL spacing at both validator and builder
- [x] Django parser FK target resolution used class_name.lower() — diverged from db_table override (e.g. "Customer" → "customer" vs entity registered as "customers")

**6 consecutive passes, no new failures:**
- [x] LIKE filter — correct SQL, `concept_map.fields` projection fix verified
- [x] NOT_IN alias (`NOT_IN` → `NOT IN`) + fields projection — `SELECT "EmployeeID", "LastName", "FirstName", "City"` correct
- [x] policy_context.resolved_predicates injection — verbatim, correct ordering, composable with empty filters
- [x] validate_sql CONCAT lint detection — compat_risks populated correctly
- [x] Django models parser — 5e/31f/5j, all FK joins resolved to correct db_table targets
- [x] Northwind DDL (13e/88f/8j) — 8 core tables clean; 5 dbo-schema tables degrade silently (T-SQL bracket notation — noted, not blocking)

**Total after session 3: 13 bugs found and fixed. 289 tests green throughout.**

## Session 4 — March 13 Late Night

**Bugs found and fixed:**
- [x] `concept_map.fields` ignored in SELECT — builder fell back to `SELECT *` with no dimensions/metrics; fix: use fields[] for projection
- [x] Filter operator aliases rejected — `NOT_IN`, `IS_NULL`, `IS_NOT_NULL` not normalized to SQL spacing at validator + builder
- [x] Django parser FK target_table used `class_name.lower()` — diverged from `db_table` override; fix: first-pass `class_to_table` map
- [x] `SemanticSnapshot.find_join_path` unidirectional — BFS blocked all M:N junction table queries (film_category, film_actor etc.); fix: bidirectional BFS with reversed JoinDef objects

**New capability:**
- [x] `ingest_source` now accepts live PostgreSQL DSNs (`postgresql://...`) — introspects schema via PostgresAdapter + FK constraints → SemanticSnapshot. `query_database` + `profile_data` were already live.

**Live DB round-trip — PASSING (Pagila Docker):**
- [x] `ingest_source("postgresql://boyce:password@localhost:5433/pagila")` → 29e/171f/36j
- [x] `ask_boyce` Mode A — 6-entity join chain through junction table (film_category) → SQL verified
- [x] `query_database` — real results returned (Documentary $531.70 top revenue category)
- [x] `profile_data` — `rental.return_date`: 183 nulls / 1.14%

**`pip install boyce` in clean venv — PASSING:**
- [x] `uv venv /tmp/boyce-cleantest && uv pip install -e boyce/` → 69 packages, no errors
- [x] `/tmp/boyce-cleantest/bin/boyce --help` → CLI starts
- [x] Public API imports (`process_request`, `SemanticSnapshot`, `lint_redshift_compat`, `SemanticGraph`) → OK
- [x] `verify_eyes.py` → 15/15

**Total after session 4: 15 bugs found and fixed. 289 tests green. Commit: `63ddeaa`**

## Session 5 — March 14 Early Morning (Battery 4)

**Bugs found and fixed:**
- [x] Bug 16: `COUNT_DISTINCT` emitted verbatim — fixed in `builder.py`
- [x] Bug 17: Stale definitions survive snapshot overwrite — `DefinitionStore.clear()` added, called on save
- [x] Bug 18: DDL directory not handled — `DDLParser.detect()/parse()` extended for directories
- [x] Bug 18b: UTF-8 BOM breaks T-SQL DDL parsing — stripped at top of `_parse_ddl_sql()`
- [x] Bug 18c: Bracket-quoted multi-word column names misparse — `_extract_col_name_and_rest()` added
- [x] NULL trap warning: int filter value rendered as '1' not 1 — fixed with `repr()`
- [x] Doc discrepancies: 4 files updated (tool counts, build_sql/solve_path references removed)

**Battery 4 results (all 8 tests run):**

| Test | Result |
|------|--------|
| 1 Prisma parser | PASS |
| 2 SQLAlchemy parser | PASS |
| 3 Multiple dims + COUNT_DISTINCT | PASS (Bug 16 fixed) |
| 4 Redshift dialect | PASS |
| 5 solve_path | N/A (internal only, by design) |
| 6 Snapshot overwrite | PASS (Bug 17 fixed) |
| 7 WWI DDL directory | PASS (Bugs 18/18b/18c fixed) |
| 8 NULL trap on live DB | PASS (fires at 100% NULLs, threshold=5%) |

**Total after session 5: 21 bugs found and fixed. 289 tests green. Commits: `725c85f` → `6313744`**

## Session 6 — March 14 (Battery 5)

**Battery 5 results (10 tests):**

| # | Test | Result |
|---|---|---|
| 1 | Column collision: multi-join SELECT | BUG 22 found + fixed |
| 2 | Filter on non-joined entity | BUG 23 found + fixed |
| 3 | Multi-metric (SUM + COUNT + AVG) | PASS |
| 4 | validate_sql with valid SQL | PASS |
| 5 | validate_sql with invalid SQL | PASS |
| 6 | query_database write rejection | PASS |
| 7 | ingest_definition lifecycle | PASS |
| 8 | ask_boyce with bad field_id | PASS |
| 9 | Multiple filters (4 AND conditions) | PASS |
| 10 | 3-entity join GROUP BY qualification | PASS |

- [x] Bug 22: `_build_select_clause` emitted bare field names for dimensions — no table qualification, alias on collision. Fixed in builder.py (SELECT + GROUP BY + metrics).
- [x] Bug 23: `_validate_structured_filter` did not check filter `entity_id` vs join scope — filter on non-joined entity produced invalid SQL. Fixed: validator now rejects out-of-scope filter entities with actionable error.

**Decision gate: 2 bugs found → Battery 6 required (gate was ≤1).**

**Total after session 6: 23 bugs found and fixed. 289 tests green. Commit: `1113d22`**

## Opus Refactor (pre-Battery 6)

- [x] Extracted `_resolve_field_ref()` — single helper replacing 6 inline field resolution sites (116 lines)
- [x] Extracted `_resolve_grouping_field()` — static helper for GROUP BY field mapping
- [x] Refactored `_build_select_clause`, `_render_filter_def`, `_build_group_by_clause` through helpers
- [x] Deleted dead code: `_build_from_clause` + `_build_join_clauses` (66 lines, never called)
- [x] Proactive fix: concept_map.fields collision bug (same gap as Bug 22 in fields[] path)
- [x] Net: -94 lines (164 added, 258 removed). Commit: `ec8bd15`

## Session 7 — March 14 (Battery 6)

**Battery 6 results (4 tests — Test 1 eliminated by proactive fix in refactor):**

| # | Test | Result |
|---|---|---|
| 1 | IN operator with list value | PASS — `IN ('PG', 'PG-13', 'R')`, table-qualified, EXPLAIN verified |
| 2 | Redshift dialect lint via validate_sql | PASS — compat_risks: CONCAT() flagged correctly |
| 3 | NULL trap on equality filter | PASS — film.original_language_id 100% NULL (1000/1000), warning fired |
| 4 | Mode C fallback (NL, no credentials) | BUG 24 found + fixed + re-test verified |

- [x] Bug 24: Auth errors (litellm.AuthenticationError) hit generic Exception handler instead of Mode C fallback. Fix: check exception class name for Auth/Permission → route to `_build_schema_guidance()`. Commit: `fb37f6b`

**Decision gate: 1 bug found → fixed → re-test passed → proceed to Cursor.**

**Total: 24 bugs found and fixed across 7 sessions. 289 tests green. Commits: `ec8bd15` → `fb37f6b`**

---

## Testing Plans (Original Schedule)

### Tonight (March 13 late) — Close Remaining Gates

- [x] Finish compiler testing on Claude Code — 20 tests, 6 consecutive passes, all green
- [x] Confirm NULL trap fires on demo scenario (`demo/magic_moment/`) — both dangers fire, all assertions pass
- [x] `pip install boyce` in clean venv — PASSED
- [x] Live DB round-trip (Pagila Docker + `query_database` + `profile_data` + `ingest_source` via MCP) — PASSED
- [x] Commit + push all session fixes (15 bugs + live DB ingest)

### March 14 Morning — Cursor Cross-Platform Test

**This is the last must-have gate before version decision + publish.**

**Prerequisites:**
1. Docker running: `docker compose up -d` in `boyce/tests/validation/` (Pagila on `localhost:5433`)
2. Cursor installed with MCP support enabled

**Step 1 — Run `boyce init` from project root:**
```bash
cd /Users/willwright/ConvergentMethods/products/Boyce
.venv/bin/boyce init
```
- Should detect Cursor (looks for `.cursor/` dir or Cursor app)
- Writes `.cursor/mcp.json` with boyce server entry
- When prompted for DB URL: `postgresql://boyce:password@localhost:5433/pagila`
- Skip LLM config (not needed — Cursor's own LLM is the planner)

**Step 2 — Verify MCP connection in Cursor:**
- Open the Boyce project in Cursor
- Check MCP server status (Cursor Settings → MCP or equivalent)
- Boyce should show as connected with 7 tools available

**Step 3 — Ingest Pagila snapshot:**
Ask Cursor: "Use the boyce ingest_source tool to ingest the database at postgresql://boyce:password@localhost:5433/pagila with snapshot name pagila"
- Pass: returns snapshot with ~29 entities, ~171 fields, ~36 joins

**Step 4 — Query 1 (single entity, simple aggregation):**
Ask Cursor: "Using boyce, how many films are in each rating category?"
- Pass: Cursor calls get_schema, constructs StructuredFilter, calls ask_boyce Mode A
- SQL should be: `SELECT "film"."rating", COUNT("film"."film_id") ... FROM "film" GROUP BY ...`
- Validation status: "verified"

**Step 5 — Query 2 (multi-entity join):**
Ask Cursor: "Using boyce, what are the top 10 customers by total rental count?"
- Pass: Cursor constructs a StructuredFilter joining rental → customer
- SQL should have JOIN, GROUP BY, correct table qualification

**Decision gate after Cursor:**
- If both queries produce correct SQL → proceed to version decision
- If Cursor MCP doesn't connect or queries fail → debug, fix, retry

**After Cursor passes:**
- [ ] Test on **VS Code** (stretch): boyce init → MCP connection → 1+ query (uses `"servers"` key)
- [ ] Version decision: v0.1.0 (ship, iterate) or iterate further — after Cursor passes
- [ ] If go: version bump in `pyproject.toml`, `cd boyce && python -m build && uv publish` (Will executes)
- [ ] Verify: `pip install boyce` from PyPI in a fresh venv, `boyce` CLI starts, imports work

---

## Recent Completions Timeline (from MASTER.md)

- **2026-03-16:** Init wizard overhaul + discovery system + CLI convention change:
  - Full `init_wizard.py` rewrite: 3-step interactive flow (editors → DB → data sources), questionary + fallback
  - New `discovery.py` module: auto-detect data source projects on filesystem (8 parser types)
  - CLI convention: `boyce init` / `boyce scan` subcommands (legacy hyphenated entry points preserved)
  - Bug fixes: discovery→ingestion path resolution, nested LookML false positive, DSN encoding, manifest detection
  - Test fixtures: `airflow_analytics/` (8 DDL tables), `sample_sqlite/` (5 tables + seed data)
  - `test_discovery.py`: 27 new automated tests (detection, resolution, walk, ingestion)
  - 316 tests, 20 CLI smoke checks, all green
- **2026-03-14 (early morning):** Battery 5-6 + Opus refactor:
  - Battery 5 (10 tests): 2 bugs found — Bug 22 (column collision, bare field names), Bug 23 (filter on non-joined entity). Both fixed.
  - Opus refactor: extracted `_resolve_field_ref()` helper, eliminated root cause of 5 builder bugs (4, 5, 10, 16, 22). Deleted 66 lines dead code. Net -94 lines. Commit: `ec8bd15`.
  - Battery 6 (4 tests): 1 bug found — Bug 24 (auth errors hit generic handler instead of Mode C fallback). Fixed. Commit: `fb37f6b`.
  - **Total: 24 bugs found and fixed across 7 sessions. 289 tests green. Cursor cross-platform test is next gate.**
- **2026-03-13 (late evening):** MCP integration testing session 3 — 6 consecutive passes, no new failures:
  - 4 bugs found and fixed: safety.py missing 4 Redshift lint rules (CONCAT, STRING_AGG, FILTER, RECURSIVE),
    concept_map.fields ignored in SELECT (builder fell back to SELECT *), filter operator aliases
    (NOT_IN/IS_NULL/IS_NOT_NULL) rejected by validator + builder, Django FK target resolution diverged
    from db_table override.
  - Tests passing: LIKE, NOT_IN (alias), policy_context.resolved_predicates, validate_sql CONCAT lint,
    Django models (5e/31f/5j), Northwind DDL (13e/88f/8j). **13 total bugs fixed across 3 sessions.**
  - Untested: live DB (Pagila), clean venv install, Cursor cross-platform. CEO version decision pending.
- **2026-03-13 (evening):** MCP integration testing session 2 — 6 more bugs found and fixed:
  - temporal_filters dropped, DATE_TRUNC docstring gap, LookML directory ingest, LookML model file 0 entities,
    LookML join source view wrong, ingest_source validation gap.
  - Tests passing (after fixes): multi-hop joins, temporal DATE_TRUNC, validate_sql, dbt jaffle_shop, LookML thelook, NULL trap demo.
- **2026-03-13 (PM):** MCP integration testing session 1 — 6 bugs found and fixed:
  - boyce-init config path, ingest_source description, snapshot hash recomputation, builder COUNT field
    resolution, builder GROUP BY field resolution, ORDER BY/LIMIT guidance.
  - 3 queries tested successfully (Mode A): supplier product counts, top-5 expensive products, cross-entity WHERE filters.
- **2026-03-13 (AM):** Architectural overhaul (CEO/Opus directive, 10 changes):
  - ask_boyce tri-modal (Mode A/B/C), validate_sql new tool, build_sql/solve_path internalized (7-tool surface),
  - StructuredFilter docs updated with examples, intent classifier removed, boyce-init expands to 6 platforms,
  - Schema freshness Tier 2 (mtime check + auto re-ingest) + Tier 3 (live DB drift detection),
  - Source path tracking in parsers. 289 tests green.
- **2026-03-11:** VS Code extension scaffold — `extension/` directory, 11 files, 1,424 LOC TypeScript, compiles clean. Deprioritized same day (VS Code native MCP is the path).
- **2026-03-11:** Full repo audit — deleted stale docs, fixed stale references, `legacy_v0/` deleted, semantic review complete
- **2026-03-07:** `src` layout migration — `boyce/boyce/` → `boyce/src/boyce/`; CWD namespace conflict eliminated; 260 tests green
- **2026-03-07:** Client reference strip (Phases 1-3) + git history squash — repo is clean, pre-commit hook active
- **2026-03-06:** Delivery surface expansion — `get_schema`, `build_sql`, `boyce-init`, Direct CLI, HTTP API (52 new tests)
- **2026-03-05:** Full codebase rename to `boyce` (package, module, env vars, MCP tools, docs, CI)
- **2026-03-04:** Name confirmed as Boyce. Domain `boyce.io` purchased.
- **2026-03-01:** Scan CLI (`boyce-scan`) implemented — 10 tests
- **2026-03-01:** All 10 parsers operational with 177 parser tests
- **2026-02-28:** Legacy code quarantined, CI/CD rewritten, docs aligned

---

## CEO Directives Completed During Sprint

**Prior-Name Scrub (2026-03-11):**
- `legacy_v0/` deleted entirely (328 files — preserved in git history)
- All `__pycache__/` directories deleted
- 5 stale management documents deleted (pre-rename brainstorming, session briefings, strip plan)
- 5 stale handoff archives deleted
- Root `uv.lock` deleted (stale artifact from deleted root pyproject.toml)
- Demo files, `.gitignore`, `CLAUDE.md`, strategy docs — all scrubbed
- grep verification: zero hits in active tracked files

**Semantic Review Pass (2026-03-11):**
Full semantic scan of active codebase (`boyce/`, `demo/`) for music/media/streaming/
advertising/entertainment fingerprints. Zero findings. All test fixtures use
neutral domains (generic e-commerce, SaaS subscriptions, spy-thriller integration test).

**Support Readiness (2026-03-11):**
- `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml`, `setup_help.yml`, `config.yml`
- `docs/troubleshooting.md` — comprehensive FAQ
- `README.md` — Support section added
- Email references updated to will@convergentmethods.com (swap to will@boyce.io when DNS configured)
