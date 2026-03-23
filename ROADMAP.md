# Boyce Roadmap

> Ops layer roadmap. See CM root CLAUDE.md for protocol definition.
> Will authors phases and gate types. CC maintains status and proposes amendments.

## Current Phase
Phase: Pre-Publish Finalization
Status: in progress

## Phases

### Phase 1: Pre-Publish Finalization
- **Done condition:** All RELEASING.md pre-publish gates checked. Uncommitted Track 1 + Track 2 work committed. Cursor cross-platform test passed. All 8 public surfaces updated to reflect current state (tool count 8, `check_health`, `boyce doctor`, `ready_filter`, DataGrip/Codex). `git status` clean on main.
- **Gate to next phase:** HITL
- **Status:** in progress
- **Notes:** ~1,316 lines of uncommitted work need review and commit. 8 surfaces are stale (noted in MASTER.md as of 2026-03-21). Cursor test is the last technical gate. Will makes the publish go/no-go call.

### Phase 2: Publish to PyPI
- **Done condition:** `pip install boyce` works from a clean env. PyPI page live and renders correctly. GitHub release tagged (`vX.Y.Z`). Release commit pushed to main.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Follows RELEASING.md runbook steps 1-7. Irreversible public action — version number, tag, and PyPI page are permanent. Will decides version number and gives final go.

### Phase 3: Distribution & Community Launch
- **Done condition:** All 4 MCP directories submitted (Smithery, PulseMCP, mcp.so, Glama). JetBrains ACP Registry submitted. HN post live. Reddit posts (r/dataengineering, r/database). dbt Slack + Dev.to cross-posts. Launch-day social posts published.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** CEO-driven. Content pre-drafted in `_strategy/mcp-directory-submissions.md`. Social post drafts in MASTER.md Stage 2.5. All public-facing, reputation-affecting. Will controls timing and tone.

### Phase 4: Post-Publish Audit
- **Done condition:** Agent SEO baseline doc written (`_strategy/research/agent-seo-baseline.md`) with results across Claude, GPT, Gemini. All 8 public surfaces verified current and version-consistent.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** CEO work (first 48h post-publish). Agent SEO establishes the measurement framework. Content review catches anything that drifted during publish. Agent-gated because findings inform but don't block engineering work.

### Phase 5: Telemetry Hooks
- **Done condition:** Telemetry call sites in every MCP tool in server.py. `BOYCE_TELEMETRY` env var documented, default `off`. All hooks are no-ops. Zero data collection, zero backend. Plan doc at `_strategy/plans/telemetry-design.md`.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Pure engineering against clear spec. No public surface, no privacy implications (hooks are dark). Lays groundwork for future collection without shipping anything user-visible.

### Phase 6: Platform Expansion
- **Done condition:** `boyce init` supports Codex (`config.toml`). DataGrip integration guide published. DataGrip demo content targeting DBA/analyst personas. Platform docs updated on convergentmethods.com.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** DataGrip MCP is already live (2025.1+). Codex config format researched (commit `87ec8ea`). Both are day-one platform targets. HITL because new public docs and integration guides.

### Phase 7: Test Warehouse Infrastructure
- **Done condition:** Tier 2 Docker Compose runs. 50-200 tables with realistic problems (NULLs, naming collisions, type drift, stale data). Setup script at `test_warehouses/tier2/setup.sh`. Tests exercise Tier 2 against Boyce.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Internal infrastructure. No public surface. Prerequisite for benchmark program. Agent-gated — well-specified engineering.

### Phase 8: Benchmark Program
- **Done condition:** 20-50 ground-truth queries defined against Tier 2 warehouse. Benchmark harness built (plug-and-play per platform). First battery run across Claude Code, Cursor, Codex. "With Boyce / Without Boyce" comparison table ready for README + product page.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Results become marketing material (README, PyPI, product page). HITL because Will decides what gets published and how it's framed. Plan doc at `_strategy/plans/benchmark-program.md`.

### Phase 9: Protocol & Parsers (Block 2)
- **Done condition:** SemanticSnapshot JSON Schema published as standalone spec. StructuredFilter spec published. SQLMesh + Alembic parsers passing. `boyce scan ./any-project/` produces a snapshot from any common source.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Public spec publication. Changes the project's external contract. HITL because spec decisions are hard to reverse once adopted.

### Phase 10: Data Quality & Agentic Ingestion (Block 3)
- **Done condition:** `ingest_source` returns `classification_needed` payload. Host LLM classifies, `enrich_snapshot` stores enrichments. Zero API keys in MCP context. Ingest-time profiling. Drift detection on re-ingest. Protocol v0.2 published with migration guide.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** The competitive wedge against dbt MCP. Protocol version bump is a public commitment. HITL because architecture and public spec.

### Phase 11: Behavioral Hardening (Block 3.5)
- **Done condition:** `query_database` provides full safety parity with `ask_boyce` path. Ingest-time null profiling makes `data_reality` report actual percentages (not just nullable booleans). Measurable improvement in non-Claude model safety outcomes.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Builds on Phase 10 ingest-time profiling. Agent-gated because measurable, testable, no public surface change. "The Arrogant Agent Problem" essay provides the empirical baseline.

### Phase 12: Ecosystem & Adoption (Block 4)
- **Done condition:** At least one external tool produces or consumes SemanticSnapshot. 2+ essays published (Null Trap + Arrogant Agent minimum). Conference talk submitted to at least one venue (dbt Coalesce, Data Council, or AI Engineer Summit). Entity `priority_score` computed at ingest.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** The "moat" phase. Adoption is the goal. Conference submissions, content series, and external partnerships all require Will's judgment and voice.

## Amendments Log
<!-- CC appends proposed amendments here. Will reviews and approves/rejects. -->
<!-- Format: [Date] [Proposed by CC] [Description] [Status: proposed | approved | rejected] -->
