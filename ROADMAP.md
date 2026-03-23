# Boyce Roadmap

> Ops layer roadmap. See CM root CLAUDE.md for protocol definition.
> Will authors phases and gate types. CC maintains status and proposes amendments.

## Current Phase
Phase: Pre-Publish Finalization
Status: in progress

## Phases

### Phase 1: Pre-Publish Finalization
- **Done condition:** All RELEASING.md pre-publish gates checked. Uncommitted Track 1 + Track 2 work committed. Cursor cross-platform test passed. All 8 public surfaces updated to reflect current state (tool count 8, `check_health`, `boyce doctor`, `ready_filter`, DataGrip/Codex). `git status` clean on main. Public surface manifest generated and reviewed by Will.
- **Gate to next phase:** HITL
- **Status:** in progress
- **Notes:** Track 1 + Track 2 work committed (8 commits, 2026-03-23). All 8 surfaces refreshed. Packaging fix landed (README.md symlink). 395 tests green. Clean venv install + uv build verified. Remaining: Cursor cross-platform test, version lifecycle features (version check + `boyce update`), version number decision. Will makes the publish go/no-go call. CC must generate a manifest of every public-facing file: READMEs, docstrings, CLI help text, website copy, PyPI metadata, MCP tool descriptions, CHANGELOG, tool description strings in code, and any other surface a user, agent, or community member will see. Each entry: file path, surface type, one-line summary. Will reviews the manifest and signs off. This is a HITL sub-task within Phase 1.

### Phase 2: Publish to PyPI
- **Done condition:** `pip install boyce` works from a clean env. PyPI page live and renders correctly. GitHub release tagged (`vX.Y.Z`). Release commit pushed to main.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Follows RELEASING.md runbook steps 1-7. Irreversible public action — version number, tag, and PyPI page are permanent. Will decides version number and gives final go.

### Phase 3: Distribution & Community Launch
- **Done condition:** All 4 MCP directories submitted (Smithery, PulseMCP, mcp.so, Glama). JetBrains ACP Registry submitted. Null Trap essay posted to Hacker News (standalone link post or Show HN). Null Trap essay cross-posted to r/dataengineering (technical observation framing, not product launch), r/database (shorter framing), and Dev.to (full essay, long-tail SEO). Brief intro posted to dbt Slack #tools channel with links to PyPI + essay. Brief intro posted to Locally Optimistic Slack if appropriate for channel norms. 3-4 launch-day social posts published on Will's personal accounts (Twitter/X, Bluesky, LinkedIn). Social post drafts prepared before publish day.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** This phase is predominantly Will-executed, not agent-executed. CC can draft social posts and community intros for Will's review, but Will controls timing, tone, and posting. The Null Trap essay already exists at convergentmethods.com/boyce/null-trap/ — distribution is the bottleneck, not content. Content pre-drafted in `_strategy/mcp-directory-submissions.md`. Social post drafts in MASTER.md Stage 2.5. Social post themes (for CC to draft against): (1) The Null Trap observation — AI agents generate syntactically correct SQL against incomplete data distributions, wrong answers with false confidence. (2) The arrogant archetype — GPT-5.4 bypassed the entire safety pipeline because raw SQL was one fewer API call, what that teaches about behavioral design for agent tools. (3) The behavioral advertising insight — MCP tool descriptions aren't docstrings, they're ads; LLMs respond to the same behavioral patterns as humans: loss aversion, reciprocity, authority bias. After publish, file USPTO trademark application for "Boyce" under International Class 009 (software). TEAS Plus application, ~$250. This is a post-publish administrative task — not a done condition for this phase, but should be initiated during or shortly after Phase 3 while the mark is actively in commerce. Use ™ on materials until registration completes. Will handles this — 90-minute online form, not a CC task.

### Phase 4: Post-Publish Audit
- **Done condition:** Agent SEO baseline doc written (`_strategy/research/agent-seo-baseline.md`) with results across Claude, GPT, Gemini. All 8 public surfaces verified current and version-consistent. "The Arrogant Agent Problem" essay draft complete, ready for Will's review.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** CEO work (first 48h post-publish). Agent SEO establishes the measurement framework. Content review catches anything that drifted during publish. Agent-gated because findings inform but don't block engineering work. The Arrogant Agent essay documents the cross-platform test findings: non-Claude models systematically bypass MCP tool safety pipelines when they can write raw SQL directly. Content outline: (1) Test setup — 9-test battery, 6 platform/model combinations. (2) The two camps — Claude follows the funnel, GPT bypasses it. (3) Why the bypass is rational — path of least resistance. (4) Why the bypass is dangerous — safety pipeline only runs through ask_boyce. (5) The fix — make the bypass path safe (query_database parity). (6) Implications for MCP tool design broadly. Raw material exists in cross-platform test results — this is a write-up, not new research. Publish timing is independent of other phases — can go live anytime after PyPI publish. This is the second publication after the Null Trap essay, deepening the narrative and positioning Convergent Methods as the authority on agent-tool behavioral dynamics. Cross-reference: link from the Null Trap essay ("See also: what happens when the agent bypasses the safety layer entirely").

### Phase 5: Telemetry Hooks
- **Done condition:** Telemetry call sites in every MCP tool in server.py. `BOYCE_TELEMETRY` env var documented, default `off`. All hooks are no-ops. Zero data collection, zero backend. Plan doc at `_strategy/plans/telemetry-design.md`.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Pure engineering against clear spec. No public surface, no privacy implications (hooks are dark). Lays groundwork for future collection without shipping anything user-visible.

### Phase 6: Platform Expansion
- **Done condition:** `boyce init` supports Codex (`config.toml`). DataGrip integration guide published. DataGrip demo content targeting DBA/analyst personas. Platform docs updated on convergentmethods.com. `boyce init` tested from the perspective of each target platform (Claude Code, Cursor, Codex) and verified clean for agent-driven setup.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** DataGrip MCP is already live (2025.1+). Codex config format researched (commit `87ec8ea`). Both are day-one platform targets. HITL because new public docs and integration guides. No formal universal standard for agent-driven MCP server installation yet. Emerging convention: stdio transport, config file generation, minimal interactive prompts. Verify that `boyce init` follows these conventions for each platform. If the flow is broken for any platform, fix it as a bug within this phase.

### Phase 7: Test Warehouse Infrastructure
- **Done condition:** Tier 2 Docker Compose runs. 50-200 tables with realistic problems (NULLs, naming collisions, type drift, stale data). Setup script at `test_warehouses/tier2/setup.sh`. Tests exercise Tier 2 against Boyce.
- **Gate to next phase:** agent
- **Status:** not started
- **Notes:** Internal infrastructure. No public surface. Prerequisite for benchmark program. Agent-gated — well-specified engineering.

### Phase 8: Benchmark Program
- **Done condition:** 20-50 ground-truth queries defined against Tier 2 warehouse. Benchmark harness built (plug-and-play per platform). First battery run across Claude Code, Cursor, Codex. "With Boyce / Without Boyce" comparison table ready for README + product page.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** Results become marketing material (README, PyPI, product page). HITL because Will decides what gets published and how it's framed. Plan doc at `_strategy/plans/benchmark-program.md`. Benchmark results feed into the Arrogant Agent essay's empirical claims and any future publications. Ensure result format supports both README/marketing use and essay citation.

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
- **Notes:** Builds on Phase 10 ingest-time profiling. Agent-gated because measurable, testable, no public surface change. The Arrogant Agent essay (Phase 4 deliverable) provides the empirical baseline for this work. Phase 11 iterates on the behavioral layer based on those test findings.

### Phase 12: Ecosystem & Adoption (Block 4)
- **Done condition:** At least one external tool produces or consumes SemanticSnapshot. 2+ essays published (Null Trap + Arrogant Agent minimum). Conference talk submitted to at least one venue (dbt Coalesce, Data Council, or AI Engineer Summit). Entity `priority_score` computed at ingest.
- **Gate to next phase:** HITL
- **Status:** not started
- **Notes:** The "moat" phase. Adoption is the goal. Conference submissions, content series, and external partnerships all require Will's judgment and voice. Talk title: "Behavioral Design for AI Agent Tool Surfaces" — not a product pitch, a research presentation on empirical findings about how LLMs interact with tool descriptions. Draws on the arrogant archetype data, behavioral hook conversion rates, and three-archetype framework. The "SEO for agents" research paper (already scoped separately) is the academic/rigorous version of this work, positioned as a Convergent Methods brand asset.

## Amendments Log
<!-- CC appends proposed amendments here. Will reviews and approves/rejects. -->
<!-- Format: [Date] [Proposed by CC] [Description] [Status: proposed | approved | rejected] -->
