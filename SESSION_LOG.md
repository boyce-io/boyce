# Boyce Session Log

> Ops layer session log. Append-only. See CM root CLAUDE.md for protocol definition.
> CC appends an entry at the end of every execution session.

---

<!-- Entry format:
## [ISO 8601 Date] — [Phase Name]

**Accomplishments:**
- [item]

**Incomplete:**
- [item] (or "None")

**Next step:** [description]
**Gate status:** [agent-gated | HITL-gated]

**Proposed amendments:**
- [amendment] (or "None")

---
-->

## 2026-03-23 — Pre-Publish Finalization

**Accomplishments:**
- Committed 1,300+ lines of uncommitted Track 1 + Track 2 work in 4 granular commits (ops layer, connections+doctor, server integration, docs)
- Refreshed all 8 stale public surfaces across Boyce repo and convergentmethods site (tool count 7→8, check_health, boyce doctor, ready_filter, DataGrip naming)
- Found and fixed packaging blocker: pyproject.toml `../README.md` reference fails in sandboxed builds; fixed with symlink + local reference
- Verified clean venv install (CLI, imports, uv build all pass)
- Full test suite: 395 passed, 6 skipped, 10s
- Created ops layer files (ROADMAP.md, SESSION_LOG.md)
- Pushed 8 commits to main, verified git status clean
- Began Cursor cross-platform test — identified lifecycle experience gap: no upgrade discovery or self-update mechanism
- Created handoff doc for version lifecycle review (`.claude/handoffs/CC_HANDOFF_LIFECYCLE_TESTING.md`)

**Incomplete:**
- Cursor cross-platform test (in progress — blocked on version lifecycle decision)
- Version check + `boyce update` subcommand (handoff written, awaiting Opus review)
- Version number decision (HITL)

**Next step:** Opus reviews lifecycle handoff, then build version check + `boyce update`. Resume Cursor test with full lifecycle flow.
**Gate status:** HITL-gated (version number + publish go/no-go are Will's call)

**Proposed amendments:**
- Phase 1 done condition should include "version lifecycle features (PyPI version check in check_health, `boyce update` subcommand)" — these were identified during Cursor testing as experience bugs that would cause user bounce. Not net-new scope; they're behavioral fixes for the existing check_health and CLI surfaces.

---

## 2026-03-23 (continued) — Pre-Publish Finalization: Version Lifecycle Build

**Accomplishments:**
- Built all 12 version lifecycle items from Opus-reviewed plan (CC_HANDOFF_VERSION_LIFECYCLE.md)
- New module: `version_check.py` — PyPI check, 24h disk cache, install detection (pipx/uv/pip), stale-process detection, 48h supply chain cooldown, nudge filtering, restart instructions
- New CLI: `boyce update [--yes]` — self-update with confirmation, verification, editor-specific restart instructions
- Enhanced `boyce --version` — shows update availability from cache
- `check_version()` added as 6th doctor check (renders first in output)
- Version info wired into `check_health()` response and `environment_suggestions`
- Graceful self-termination gated behind `BOYCE_AUTO_RESTART_ON_UPDATE`
- Added `packaging>=21.0` as explicit dependency
- 43 new tests (37 version_check + 6 doctor), 438 total, 24 CLI smoke checks
- Updated CLAUDE.md with new module, env vars, test inventory
- Integrated Opus feedback: packaging as explicit dep, Cursor restart instruction fixed, self-termination caveat documented, post-build doc updates planned

**Incomplete:**
- Cursor cross-platform test (needs restart from ground up — initial attempt used wrong config)
- Manual testing of wizard + install + version flows
- Doc updates: README, RELEASING template still need version lifecycle mentions (Will's voice)

**Next step:** Resume Cursor test from scratch with proper setup. Manual test `boyce doctor` and `boyce update` UX.
**Gate status:** HITL-gated (Cursor test + version number + publish go/no-go)

**Proposed amendments:**
- None (prior amendment re: version lifecycle features was implemented this session)

---

## 2026-03-27 — Phase 4: Preliminary Benchmark Build

**Accomplishments:**
- Reconstructed interrupted build plan after terminal crash
- Committed all Phase 3 + Phase 4 setup work (3 commits, previously uncommitted)
  - Phase 3 source: Codex/TOML, response guidance tests, 448 tests green
  - Phase 3 docs: ROADMAP, MASTER, CLAUDE.md, handoff archive, OPUS_BRIEF
  - Phase 4 setup: phase-4 plan doc, phase-5 plan doc, queries.json (12 queries)
- Built `boyce/tests/benchmark/run_benchmark.py` — Phase 4 harness
  - Mode A: plan_query → kernel.process_request → execute → score
  - Mode B: direct LiteLLM → SQL → execute → score
  - Metrics: row count (±5%), top result, join correctness, EXPLAIN verified
  - Safety flags: Q08 null trap (LEFT JOIN), Q09 dialect (|| vs CONCAT())
  - Output: Markdown + JSON to _strategy/research/preliminary-benchmark.md
- Pushed 4 commits to main (3bc64f2 → 7d21460)
- Flagged: .claude/handoffs/_archive/the actual convo with opus.md has a sensitive client name — blocked by pre-commit hook, needs sensitive-term scrub before it can be committed

**Incomplete:**
- Benchmark not yet executed (requires Pagila Docker + LLM API key at runtime)

**Next step:** Run the benchmark.
    BOYCE_PROVIDER=anthropic BOYCE_MODEL=claude-haiku-4-5-20251001 \
    ANTHROPIC_API_KEY=... \
    python boyce/tests/benchmark/run_benchmark.py
**Gate status:** Agent-gated (execution is mechanical once env vars are set)

**Proposed amendments:**
- None

---

## 2026-03-27 — Phase 4b: Benchmark Bug Fix Pass

**Accomplishments:**
- Root cause analysis → 9 bugs classified (BUG-A through BUG-I), 2 discovered by Opus beyond CC's original 7
- Executed Opus's 14-step bug fix plan in one pass (Sonnet · high):
  - BUG-A (CRITICAL): Metric validation rewrite — decoupled metric_name from field lookup. Affected 6/12 queries.
  - BUG-B (HIGH): ORDER BY + LIMIT support added — planner, kernel, builder (new `_build_order_by_clause()`)
  - BUG-C (MEDIUM): Entity over-scoping — nx.has_path() reachability check; join_resolver degrades gracefully
  - BUG-D (LOW): grouping_fields now emits field_ids, not bare names (table-qualified GROUP BY)
  - BUG-E (LOW): Harness LEFT OUTER JOIN regex fix
  - BUG-F (LOW): Expression columns (concatenation) — `col1 || ' ' || col2 AS alias`
  - BUG-G (MEDIUM): Field resolution keyword scoring — `_score_field_match()` splits on underscores
  - BUG-H (HIGH): COUNT_DISTINCT added to planner prompt
  - BUG-I (MEDIUM): COUNT(*) sentinel — empty field_id + COUNT → `COUNT(*)`
  - Prompt fix: limit/order_by made strictly conditional on Top-N intent (fixed gpt-4o-mini overuse)
- StructuredFilter bumped to v0.2 (order_by, limit, expressions fields)
- 17 new tests in test_bugfix_phase4b.py — 465 total, 6 skipped, all pass
- Benchmark v2 results (gpt-4o-mini, Pagila):
  - Mode A avg: **3.5/4** (up from 2.33) — TARGET HIT
  - Row count accuracy: **100%** (up from 33%)
  - Top result accuracy: 75% (up from 42%)
  - Join correctness: 75% (up from 67%)
  - EXPLAIN verified: 100% (up from 92%)
  - Q09 (dialect): BUG-F working — `first_name || ' ' || last_name` renders correctly
- 6 commits pushed to main (ae9421f → 24e8e26)

**Incomplete:**
- Q08 null_trap_detected still False (language entity resolves to primary language FK not original_language_id — Pagila's join graph only has one FK from film→language)
- Q02, Q03, Q05 each 3/4 (not 4/4 — COUNT vs COUNT DISTINCT, view-based results)
- Q07, Q09 each 3/4 (Q07: temporal join missing; Q09: returns 599 rows not 5 — no Top-N so correct, scored partial)

**Next step:** Phase 4 complete. Proceed to Phase 5 (Agentic Ingestion Light) — agent-gated.
**Gate status:** Agent-gated

**Proposed amendments:**
- ROADMAP Phase 4 status updated to "complete" (done this session)
- Known gap added: HAVING clause (no benchmark query exercises it; defer to when a query requires it)

---

## 2026-03-28 — Phase 5: Agentic Ingestion Sprint (Sprint 0 + Sprint 1a)

**Accomplishments:**
- Sprint 0: Haiku regression root cause diagnosed — Branch A confirmed
  - Diagnostic script (sprint0_diagnosis.py) runs stripped StructuredFilter benchmark
  - Stripped mode scores 2.50 vs full 3.42 vs vanilla 3.83 — stripping makes it WORSE
  - Join correctness identical (83%) in both stripped and full — entity selection not improved
  - Conclusion: Haiku fails at metrics/dimensions categorization, not abstraction complexity
  - Three specific failure patterns: join keys in dimension slots (Q02), wrong metric column (Q05), missing dimensions entirely (Q06)
  - Deliverable: `_strategy/research/sprint0-haiku-diagnosis.md`
- Sprint 1a: Schema extensions (types.py, validation.py, parsers/base.py)
  - FieldDef: null_rate, distinct_count, sample_values, business_description, business_rules
  - Entity: object_type, row_count, view_sql, view_lineage
  - JoinDef: join_confidence, orphan_rate
  - SemanticSnapshot: profiled_at
  - canonicalize_snapshot_for_hash() is single source of truth for hash exclusions
  - 16 new tests — 481 total pass, 6 skipped
- 1 commit pushed to main (24bd30a)

**Incomplete:**
- Sprint 2: Live database profiling engine (next)
- Sprint 1b/c/d: Parser deepening (parallel, lower priority)

**Next step:** Build `boyce/src/boyce/profiler.py` — Sprint 2 (critical path). DONE — see next entry.
**Gate status:** Agent-gated (continued in same session)

**Proposed amendments:**
- None

---

## 2026-03-28 — Phase 5: Agentic Ingestion Sprint (Sprint 2 — Profiling Engine)

**Accomplishments:**
- Built `boyce/src/boyce/profiler.py` — `profile_snapshot(adapter, snapshot) → SemanticSnapshot`
  - Row counts per entity (SELECT COUNT(*))
  - NULL rates per column — one batch query per entity, not N round-trips
  - Enum detection: columns with distinct_count ≤ 25 → sample_values
  - Object type detection via information_schema.tables
  - FK confidence + orphan_rate via LEFT JOIN match-rate query (Redshift-compatible)
  - Sequential execution (asyncpg single-connection, no asyncio.gather)
  - snapshot_id preserved: profiling fields excluded by canonicalize_snapshot_for_hash()
- All Opus smoke tests passed on Pagila:
  - original_language_id null_rate = 1.0 ✓ (THE smoke test)
  - film.rating sample_values = ['G', 'NC-17', 'PG', 'PG-13', 'R'] ✓
  - All FK joins: confidence=1.0, orphan_rate=0.0 ✓
- 32 new tests (test_profiler.py): 24 unit (mocked adapter), 8 Pagila integration
- 513 total tests pass, 6 skipped (unchanged)
- 2 commits pushed (24bd30a Sprint 0+1a, c8042a8 session log)

**Incomplete:**
- Sprint 1b/c/d: Parser deepening (parallel, lower priority)
- Sprint 3: Host-LLM classification loop (HITL-gated)
- Sprint 4: Benchmark validation against dirty fixture

**Next step:** Sprint 3 (HITL-gated — awaiting Will + Opus classification prompt spec).
Meanwhile Sprint 1b/c/d parser deepening available as parallel work.
**Gate status:** HITL-gated (Sprint 3 classification prompt)

**Proposed amendments:**
- None

---

## 2026-03-27 — Phase 5: Agentic Ingestion Light

**Accomplishments:**
- Reviewed `_extract_referenced_columns` test coverage in `boyce/tests/test_response_guidance.py` against the implementation in `boyce/src/boyce/server.py`
- Confirmed missing negative-coverage cases around string literals, subquery/table-name leakage, and type-name leakage; also identified missing direct coverage for quoted identifiers, multi-column clauses, and duplicate-column precedence behavior
- Wrote persistent review notes to `_local_context/2026-03-27-extract-referenced-columns-test-review.md`
- Updated `/Users/willwright/ConvergentMethods/MASTER.md` to reflect Codex onboarding as a secondary execution engine in the CM operating stack

**Incomplete:**
- No test changes implemented yet

**Next step:** If requested, add the missing `_extract_referenced_columns` test cases without changing implementation behavior.
**Gate status:** agent-gated

**Proposed amendments:**
- None

---
