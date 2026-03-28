# Boyce Roadmap

> Ops layer roadmap. See CM root CLAUDE.md for protocol definition.
> Will authors phases and gate types. CC maintains status and proposes amendments.

## Current Phase
Phase: Phase 5 — Agentic Ingestion Sprint
Status: in progress (sprint planning complete, execution starting)

## Phases

### Phase 1: Pre-Publish Finalization
- **Done condition:** All RELEASING.md pre-publish gates checked. Uncommitted Track 1 + Track 2 work committed. Cursor cross-platform test passed. All 8 public surfaces updated to reflect current state (tool count 8, `check_health`, `boyce doctor`, `ready_filter`, DataGrip/Codex). `git status` clean on main. Public surface manifest generated and reviewed by Will.
- **Gate to next phase:** HITL
- **Status:** COMPLETE (2026-03-24)
- **Notes:** Track 1 + Track 2 work committed (8 commits, 2026-03-23). All 8 surfaces refreshed. Packaging fix landed (README.md symlink). Version lifecycle built (12 items: PyPI check, disk cache, `boyce update`, stale-process detection, cooldown, nudge filtering, self-termination). 438 tests green, 24 CLI smoke checks. Clean venv install + uv build verified. Remaining: Cursor cross-platform test (restart from ground up), manual testing of wizard + install + version flows, version number decision. Will makes the publish go/no-go call. CC must generate a manifest of every public-facing file: READMEs, docstrings, CLI help text, website copy, PyPI metadata, MCP tool descriptions, CHANGELOG, tool description strings in code, and any other surface a user, agent, or community member will see. Each entry: file path, surface type, one-line summary. Will reviews the manifest and signs off. This is a HITL sub-task within Phase 1.

### Phase 2: Publish to PyPI
- **Done condition:** `pip install boyce` works from a clean env. PyPI page live and renders correctly. GitHub release tagged (`vX.Y.Z`). Release commit pushed to main.
- **Gate to next phase:** HITL
- **Status:** COMPLETE (2026-03-24). v0.1.0 on PyPI. GitHub release tagged. UV_PUBLISH_TOKEN in .zshrc for zero-HITL future publishes.
- **Notes:** Follows RELEASING.md runbook steps 1-7. Irreversible public action — version number, tag, and PyPI page are permanent. Will decides version number and gives final go.

### Phase 3: Platform Expansion (pre-distribution)
- **Done condition:** `boyce init` supports Codex (`config.toml`). DataGrip integration guide published. Platform docs updated. `boyce init` tested for each target platform.
- **Gate to next phase:** agent
- **Status:** COMPLETE (2026-03-27). Codex added as 7th platform. TOML read/write. 448 tests, 25 CLI smoke.
- **Notes:** Pulled forward from original Phase 6. Adds Codex to the "works with" list before distribution — 7 platforms (Claude Code, Cursor, VS Code, DataGrip, Windsurf, Claude Desktop, Codex). DataGrip MCP is already live (2025.1+). Codex config format researched (commit `87ec8ea`). ~0.5 day Sonnet work.

### Phase 4: Preliminary Benchmark (pre-distribution)
- **Done condition:** 10-15 ground-truth queries defined against Pagila (Tier 1). Benchmark harness built. First battery run across Claude Code + Cursor. Preliminary "With Boyce / Without Boyce" comparison numbers ready for distribution copy.
- **Gate to next phase:** agent
- **Status:** complete (Phase 4 benchmark run 2026-03-27; Phase 4b bug fix pass 2026-03-27)
- **Notes:** Phase 4b final: Mode A 3.5/4 (up from 2.33), row count 100% (up from 33%), EXPLAIN 100%, join correctness 75%. 9 bugs fixed, StructuredFilter v0.2, 465 tests. Q09 now correctly concatenates: `first_name || ' ' || last_name`. Q08 null trap confirmed: Boyce LEFT JOIN returns 1,000 rows vs direct LLM INNER JOIN returns 0. Distribution copy number stands. Known gap: HAVING clause (deferred — no benchmark query exercises it).

### Phase 5: Agentic Ingestion Sprint
- **Done condition:** Enriched SemanticSnapshots that demonstrably beat vanilla LLM SQL generation on GPT-4o class models. Haiku regression root-caused and either fixed or documented. Live database profiling engine operational. "Never worse than vanilla" gate (Directive #7) passed on recommended model tier.
- **Gate to next phase:** HITL
- **Status:** in progress (sprint planning complete, execution starting)
- **Notes:** Full replacement of prior "Agentic Ingestion Light" scope. The Phase 4 benchmark revealed the product gap: 10 parsers extract structural info the LLM already gets from information_schema. The ingestion layer is the product. Sprint builds: (1) Haiku regression root cause with explicit branch determination, (2) schema extensions for profiling data, (3) live database profiling engine, (4) parser deepening for dbt/LookML/ORM semantic extraction, (5) optional host-LLM classification loop, (6) benchmark validation against dirty fixture. Distribution (Phase 6) paused until this phase passes Directive #7 gate. Sprint plan: `_strategy/plans/agentic-ingestion-sprint.md`.

### Phase 6: Distribution & Community Launch
- **Done condition:** All 4 MCP directories submitted (Smithery, PulseMCP, mcp.so, Glama). JetBrains ACP Registry submitted. Null Trap essay posted to HN. Cross-posted to r/dataengineering, r/database, Dev.to. dbt Slack #tools intro. 3-4 social posts (Twitter/X, Bluesky, LinkedIn).
- **Gate to next phase:** HITL
- **Status:** not started — **BLOCKED on Phase 5** (Agentic Ingestion Sprint must complete and pass Directive #7 "never worse than vanilla" gate before distribution proceeds)
- **Notes:** Predominantly Will-executed. CC drafts, Will posts. NOW launches with: 7 platforms, null trap anecdote (1,000 vs 0 rows), agentic ingestion in feature list, refreshed terminology (SQL Compiler, Database Inspector, Query Verification). Aggregate benchmark scores NOT for distribution (Boyce ties direct LLM on clean schemas — misleading as "accuracy improvement"). Content pre-drafted in `_strategy/mcp-directory-submissions.md`. Social post themes in MASTER.md. Terminology refreshed 2026-03-24. After publish, file USPTO trademark application for "Boyce" (~$250, TEAS Plus).

### Phase 7: Post-Publish Audit
- **Done condition:** Agent SEO baseline across Claude/GPT/Gemini. All 8 public surfaces verified current. "The Arrogant Agent Problem" essay draft complete.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** First 48h post-distribution. Agent SEO establishes measurement framework. Essay documents cross-platform bypass pattern findings.

### Phase 8: Telemetry Hooks
- **Done condition:** Telemetry call sites in every MCP tool. `BOYCE_TELEMETRY` env var, default `off`. All hooks are no-ops. Zero data collection.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Pure engineering, no public surface. Dark hooks for future collection.

### Phase 9: Test Warehouse Infrastructure
- **Done condition:** Tier 2 Docker Compose. 50-200 tables with realistic problems. Setup script at `test_warehouses/tier2/setup.sh`.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Internal infrastructure. Prerequisite for full benchmark.

### Phase 10: Full Benchmark Program
- **Done condition:** 20-50 ground-truth queries against Tier 2. Full battery across Claude Code, Cursor, Codex. "With Boyce / Without Boyce" table for README + product page.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Builds on Tier 2 warehouse (Phase 9). Results become marketing material. Feeds into Arrogant Agent essay empirical claims.

### Phase 11: Protocol & Parsers (Block 2)
- **Done condition:** SemanticSnapshot JSON Schema published standalone. StructuredFilter spec. SQLMesh + Alembic parsers. `boyce scan ./any-project/` works.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Public spec publication. Hard to reverse once adopted.

### Phase 12: Agentic Ingestion — Full (Block 3)
- **Done condition:** `enrich_snapshot` tool stores host LLM classifications. Ingest-time profiling (actual NULL percentages, cardinality). Drift detection on re-ingest. Policy stubs (`pii_flag`, `access_roles`). Protocol v0.2 published with migration guide.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Second half of agentic ingestion (Phase 5 was the light version). The competitive wedge against dbt MCP. Protocol version bump is public commitment.

### Phase 13: Behavioral Hardening (Block 3.5)
- **Done condition:** `query_database` provides full safety parity with `ask_boyce` path. Ingest-time null profiling makes `data_reality` report actual percentages (not just nullable booleans). Measurable improvement in non-Claude model safety outcomes.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Builds on Phase 12 ingest-time profiling. Agent-gated because measurable, testable, no public surface change. The Arrogant Agent essay (Phase 7 deliverable) provides the empirical baseline.

### Phase 14: Ecosystem & Adoption (Block 4) → v1.0.0
- **Done condition:** At least one external tool produces or consumes SemanticSnapshot. 2+ essays published (Null Trap + Arrogant Agent minimum). Conference talk submitted to at least one venue (dbt Coalesce, Data Council, or AI Engineer Summit). Entity `priority_score` computed at ingest.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** The "moat" phase. Adoption is the goal. Conference submissions, content series, and external partnerships all require Will's judgment and voice. Talk title: "Behavioral Design for AI Agent Tool Surfaces" — not a product pitch, a research presentation on empirical findings about how LLMs interact with tool descriptions. Draws on the bypass pattern data, behavioral hook conversion rates, and three-archetype framework. The "SEO for agents" research paper (already scoped separately) is the academic/rigorous version of this work, positioned as a Convergent Methods brand asset.

## Amendments Log
<!-- CC appends proposed amendments here. Will reviews and approves/rejects. -->
<!-- Format: [Date] [Proposed by CC] [Description] [Status: proposed | approved | rejected] -->
