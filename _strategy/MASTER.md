# Boyce — Master Directive
**This is the single source of truth for planning and execution.**
**Last updated:** 2026-03-07
**All other planning documents are subordinate to this file.**
**Product name:** Boyce — named for [Raymond F. Boyce](https://en.wikipedia.org/wiki/Raymond_F._Boyce), co-inventor of SQL (1974)
**Domain:** boyce.io (purchased 2026-03-04)

---

## What We Are Building

One open protocol. One reference implementation. MIT-licensed engine, monetizable experience layer.

### The Protocol: SemanticSnapshot
A standard for expressing what a database *means* — not just structure, but semantic meaning,
data quality profiles, join confidence, policy rules, and provenance. Free. MIT licensed. The
goal: SemanticSnapshot becomes the canonical format for expressing database intelligence to AI
agents. The way OpenAPI standardized API descriptions. The way dbt standardized data
transformations. The way MCP standardized agent-to-tool communication.

### The Reference Implementation
A headless MCP server and pip-installable Python library that implements the protocol. Includes:
- A deterministic SQL kernel (same inputs → same SQL, byte-for-byte, every time)
- A safety layer (EXPLAIN pre-flight, NULL trap detection, Redshift compatibility linting)
- A semantic graph (Dijkstra join-path resolution via NetworkX)
- A pluggable parser system (dbt, LookML, raw DDL, SQLite, ORMs, and more)
- A query planner (NL → StructuredFilter via BYOK LiteLLM — the only LLM in the pipeline)

**Wins by:** Adoption. Being so useful that agents select it automatically. Being the tool that
AI agents recommend to other agents when database access is needed.

**Monetization stance:** The protocol and core library are MIT forever — adoption IS the return.
Monetization lives in the experience layer: IDE extensions (VS Code, JetBrains) ship free + pro
tiers; a hosted service may follow. The engine never has paywalls. Same pattern as Docker
(engine free, Desktop paid), Terraform (CLI free, Cloud paid), Grafana (server free, Cloud paid).

---

## The Moat

Once a company's business semantics — certified metrics, join logic, data quality baselines,
policy rules — are encoded in a SemanticSnapshot, that asset is theirs but it speaks our
protocol. The more the protocol spreads, the more every agent tool needs to speak it to be
useful. Network effects compound.

**The protocol only becomes a moat if the schema is better than alternatives.**
The differentiator is the data quality layer: null distributions, cardinality profiles,
drift thresholds, anomaly flags. This is what makes a SemanticSnapshot richer than a dbt
manifest. Build this into the protocol itself.

---

## Design Philosophy

### The Bitter Lesson Filter

Every component of this product must pass the Bitter Lesson test:
*"Will a better model make this unnecessary?"*

| Component | Bitter Lesson verdict | Why |
|-----------|----------------------|-----|
| **Deterministic kernel** | DURABLE | Models are probabilistic by definition. Byte-for-byte SQL reproducibility is a mathematical guarantee no model can provide. |
| **Safety layer** (EXPLAIN, NULL trap, Redshift lint) | DURABLE | Validation against reality, not approximation. Better models don't eliminate the need to check SQL before running it. |
| **SemanticSnapshot protocol** | DURABLE | Structured metadata is information that doesn't exist unless someone captures it. No context window expansion creates business definitions or data quality baselines. |
| **Audit trail** | DURABLE | Compliance requires knowing what happened. Not a model task. |
| **Parser system** | DURABLE | Source-specific extraction logic. Models can help generate parsers but can't replace the need for them. |
| **QueryPlanner** (NL→StructuredFilter) | SCAFFOLDING | Models will natively handle NL→SQL for well-documented schemas within 12-18 months. This is the demo, not the product. Keep the model-compensation layer thin. |
| **Prompt engineering** | SCAFFOLDING | Every prompt template is tech debt that the next model release wipes out. |

**Rule:** Build the protocol layer thick. Build the model-compensation layer thin.
The planner gets people in the door. The protocol makes them stay.

### Designed for Agent Discovery

In 6-12 months, AI agents will be the primary tool selectors. When a developer asks their
agent to query a warehouse safely, the agent searches registries, evaluates tools, and
integrates — all before the developer reviews the choice. The discovery flow:

1. Developer tells agent: "I need to query our warehouse safely"
2. Agent searches MCP servers / PyPI / tool registries
3. Agent evaluates: documentation quality, API predictability, safety guarantees, composability
4. Agent installs, configures, integrates
5. Agent uses the tool on behalf of the developer

This shapes how we design. Developers remain the audience — but the agent is an equal
participant in evaluation and integration. Both must be served well:
- Machine-readable documentation alongside human-readable prose
- Predictable, deterministic behavior — agents and humans both benefit from consistency
- Structured error messages that both agents and developers can act on
- Self-describing capabilities via MCP tool descriptions
- Composable primitives that agents can combine and humans can understand

### Two LLM Roles — Zero-Config for MCP Hosts

Boyce has two delivery paths, and they use LLMs completely differently:

| Path | Who has the LLM? | What Boyce needs | User configures |
|------|------------------|-----------------|-----------------|
| **MCP hosts** (Claude Code, Cursor, Claude Desktop, Cline) | The host has it | Nothing — host LLM calls `get_schema`, reasons, calls `build_sql` | Just `boyce-init` (no API key) |
| **Non-MCP clients** (VS Code ext, CLI `ask`/`chat`, HTTP API) | Nobody | Boyce uses its internal planner (`ask_boyce`) | `BOYCE_PROVIDER` + `BOYCE_MODEL` + API key |

**If you use an MCP host, you do not need to configure any LLM provider or API key for Boyce.**
The host's LLM reads the schema via `get_schema`, constructs a `StructuredFilter`, and passes
it to `build_sql`. Boyce compiles deterministic SQL with zero LLM calls. This is the primary
adoption path and the reason `get_schema` + `build_sql` exist as separate tools.

`ask_boyce` and the internal planner are not backward compat — they are essential for non-MCP
delivery where no host LLM exists. The VS Code extension, Direct CLI, and HTTP API all depend
on the internal planner. `BOYCE_PROVIDER` is required only for those surfaces.

### Structure Is the Ladder Rung Above Context

Infinite context windows don't kill the protocol — they make it more valuable.
Context says "here are 4,000 tables." Structure says "these tables form a graph where
`orders` joins to `customers` via `customer_id` with confidence 1.0, and `orders.status`
has 30% NULLs that will silently drop rows, and 'revenue' means `SUM(amount) WHERE
status != 'cancelled'` per the finance team's certified definition."

Context is noise at scale. Structure is signal. Determinism requires structure.
Trust requires auditability. Auditability requires structure.

---

## Competitive Position

**We are not a Text-to-SQL tool.** That market is table stakes — every IDE, agent,
and BI tool will have NL→SQL built in within 18 months.

**We are the semantic protocol and safety layer for agentic database workflows.**

> Don't let your Agents guess. Give them Eyes.

### Key Competitors (as of Feb 2026)
| Competitor | What they do | Their advantage | Our advantage |
|-----------|-------------|-----------------|---------------|
| dbt MCP Server (GA) | Semantic layer → SQL via dbt Cloud. Shipping "dbt Agents." Remote MCP server (no local install). Fusion engine integration (column-level lineage, compiler diagnostics). | Massive distribution (every dbt Cloud customer). Community. Zero-friction remote MCP onboarding. | Headless, privacy-first, vendor-neutral, works without dbt. Data quality profiling they don't have. |
| Vanna AI 2.0 | RAG-based NL→SQL, user-aware, enterprise security | Production-ready, 10+ DB platforms | Deterministic kernel (reproducible), protocol standard, not RAG |
| DBHub | Universal database MCP bridge, 100K+ downloads | Simple, broad, fast adoption | Semantic understanding vs. raw schema relay |
| OpenAI Kepler (internal) | 6-layer context system over 600PB, GPT-5.2 | Unlimited resources, deep context | Open source, self-hosted, protocol standard |
| Official Anthropic Postgres MCP | Raw query executor | Anthropic backing | Full semantic layer, safety, NL→SQL |

**The real competitive threat** is not that someone ships a better NL→SQL tool. It's that dbt
standardizes their manifest format as *the* way agents understand databases, and SemanticSnapshot
never gets the chance to be adopted. The race is against dbt's ecosystem momentum. dbt's remote
MCP server (no local install required) is a significant UX advantage — our "5 minutes to value"
competes against their "30 seconds if you already use dbt."

**The counter-positioning:** Don't compete with dbt. Complement it. "dbt tells agents what to
query. We tell agents whether the answer will be trustworthy." Being the safety layer that dbt
users *add* is a faster adoption path than being the thing they switch to.

### Market Structure (MCP Landscape)
MCP has won: 10,000+ servers, ~100M monthly SDK downloads, Linux Foundation governance (AAIF).
The question is differentiation among 10,000+ servers, not protocol choice.

Three tiers in the database MCP space:
1. **Platform plays** (dbt, Oracle, Google) — bundled with data infra
2. **Bridge tools** (DBHub) — thin connection, no semantic intelligence
3. **Semantic/safety layer** (us, Vanna) — understanding + guardrails

We are tier 3. The deterministic kernel, safety layer, and open protocol are the differentiators.

---

## The Three ICPs (in priority order)

**1. AI Engineers building agents that touch production databases.**
They need a guardrail layer. They'll adopt for safety. They won't build it themselves.
Developer tool / SDK motion. Reached via open source adoption and technical content.

**2. Data Platform Leads giving LLM access to company data.**
Their nightmare is an agent that runs a naive query at 2am and silently returns wrong results.
Our demo IS their nightmare, solved. Reached via the Null Trap story.

**3. dbt users who want safety on top of dbt MCP.**
Already have NL→SQL. Need the guardrail layer. A 30-second MCP config addition.
Reached via dbt community and content.

---

## Parser Strategy

### Design Principle: 5 Minutes to Value
The user goes from "I'm just toying around" to "this is already working on my database"
in under 5 minutes. The parser system makes this possible by auto-detecting whatever the
user has and producing a SemanticSnapshot from it.

### Auto-Discovery CLI (Operational)
```bash
boyce-scan ./my-project/
# Scans all files, auto-detects parseable sources, produces JSON report
boyce-scan ./my-project/ -v          # per-file progress to stderr
boyce-scan ./my-project/ --save      # persist snapshots to _local_context/
boyce-scan ./my-project/ | jq '.'    # stdout is clean JSON, pipeable
```

Project-scoped (trustworthy), automatic (frictionless), comprehensive (catches everything).

### Parser Priority (sequenced by onboarding impact)
| Priority | Parser | Why | Status |
|----------|--------|-----|--------|
| 1 | dbt manifest.json | Canonical semantic layer, 80% of target audience | ✅ Done |
| 2 | dbt project directory (YAML sources) | dbt users without Cloud/manifest export | ✅ Done |
| 3 | LookML files | Looker ecosystem | ✅ Done |
| 4 | Raw JSON SemanticSnapshot | Direct protocol consumers | ✅ Done |
| 5 | Live Postgres/Redshift introspection | Zero-config for anyone with a database | ✅ Partial (PostgresAdapter) |
| 6 | Raw DDL / CREATE TABLE | Universal — everyone has .sql files | ✅ Done |
| 7 | SQLite direct introspection | Zero-config, ubiquitous | ✅ Done |
| 8 | Django models.py | Huge Python ecosystem | ✅ Done |
| 9 | SQLAlchemy models | Flask/FastAPI ecosystem | ✅ Done |
| 10 | Prisma schema | TypeScript/Node ecosystem | ✅ Done |
| 11 | SQLMesh models | Signals vendor neutrality (dbt alternative) | 🔧 Block 2 |
| 12 | Alembic migrations | Schema reconstruction from migration history | 🔧 Block 2 |
| 13 | CSV/Parquet headers | Data science onramp | ✅ Done |
| 14 | Airflow DAGs | Pipeline SQL extraction | 🔧 Block 3 |

### Parser Plugin Interface
Community-extensible parser system:
```python
class SnapshotParser(Protocol):
    def detect(self, path: Path) -> float:  # confidence 0.0-1.0
    def parse(self, path: Path) -> SemanticSnapshot:
    def source_type(self) -> str:  # "dbt_manifest", "prisma", etc.
```
Build core parsers in-house. Let community contribute the rest. Same pattern as LSP
(Microsoft built the protocol + reference implementations; community built 150+ language servers).

### Protocol Bootstrapping via scan CLI
Every run of `boyce-scan ./` produces a SemanticSnapshot. Every user who runs
the scan CLI is a producer of the format — even if they never think of themselves as
"adopting a standard." External producers emerge organically from utility, not from outreach.
The scan CLI is the sneaky bootstrapping mechanism for protocol adoption.

---

## Core Directives

### 1. Frictionless Above All Else
Under 5 minutes from zero to first useful result. `pip install`, point at project, go.
If a non-technical person can't do it, the directive is not satisfied.
This is not UX polish — it is the adoption mechanism.

### 2. The Protocol Schema Must Be Built for the Future
Design these dimensions into the schema now as additions, not breaking changes:

| Dimension | What it expresses | Block |
|-----------|------------------|-------|
| **Data Quality** | Null profiles, cardinality, drift thresholds, freshness | Block 3 |
| **Policy** | PII flags, access roles, aggregation-only columns | Block 3 |
| **Provenance** | Metric approval chain, version history, audit trail | Block 4+ |
| **Workflow** | Multi-step agent intent sequences | Future |

### 3. SQL Generation Is Table Stakes, Not the Product
Every competitor generates SQL. Nobody else profiles data reality before the query runs.
Nobody else captures business definitions and applies them automatically. The safety layer
and semantic protocol are the product. NL→SQL is the demo.

### 4. Open Source Is Non-Negotiable, Forever
MIT licensed. No dual licensing. No open-core. No paywalls.
The moat is adoption. Adoption requires trust. Trust requires openness.

### 5. Ingest Everything
Build parsers for every common schema source. The tool that ingests the most formats
wins the most users. Err on the side of plug-and-play. Every new parser is another entry
point to the protocol ecosystem.

### 6. Build in Public, Aggressively
"Here is a real failure mode in AI + database workflows. Here is how the protocol prevents it."
The Null Trap essay is first. More follow the same pattern. The protocol wins by adoption.
Adoption comes from visibility. Visibility comes from stories that make data engineers say
"I need this."

---

## Execution Plan (Compressed Timeline)

### Block 0 — Name [COMPLETE]
**Status:** Done. Name confirmed as **Boyce**. Domain `boyce.io` purchased. Codebase fully renamed.
**Completed:** 2026-03-05
- PyPI: https://pypi.org/project/boyce/0.0.1/ (namespace placeholder)
- GitHub org: https://github.com/boyce-io
- Domain: boyce.io

### Block 1 — Ship It [ACTIVE]
**Goal:** Published on PyPI, deployed on a real warehouse, discoverable by agents and developers.

See `_strategy/plans/block-1-ship-it.md` for detailed plan.

#### Phase A — Engineering [COMPLETE]
- [x] Rename codebase (package, imports, CLI, pyproject.toml, docs)
- [x] Secure namespace (PyPI placeholder, GitHub org, domain)
- [x] `get_schema` + `build_sql` MCP tools (host-LLM path — no Boyce LLM needed)
- [x] `boyce-init` setup wizard (Claude Desktop, Cursor, Claude Code auto-config)
- [x] Direct CLI (`boyce ask "..."` and `boyce chat "..."`)
- [x] HTTP API mode (`boyce serve --http`, Starlette + Bearer auth, `/chat` endpoint)
- [x] Public API exports (`from boyce import process_request, SemanticSnapshot`)
- [x] `src` layout migration (namespace conflict eliminated)
- [x] Client reference strip + pre-commit hook (repo is clean)
- [x] 260 tests passing, ~10s, zero external dependencies

#### Phase B — Testing Sprint [ACTIVE — week of March 9]
**Hard requirement: Will personally tests before anything is published or submitted.**

*Mon-Tue March 9-10 (Claude Code prep):*
- [x] Integration guides written and verified (Claude Desktop, Cursor, Claude Code, Cline, Continue.dev)
- [x] Docker Compose for Pagila operational (`docker compose up` → Postgres + 15 tables)
- [x] Validation query battery written (structured capability tests + real-world prompts by persona)
- [x] Testing runbook ready (what to do, in what order, what to record)

**COMPLETE — Prior-Name Scrub (CEO Directive, 2026-03-11)**

Executed 2026-03-11. All references to prior product names, prior client names,
and origin-context terminology have been removed from active code, config, and docs.

Actions taken:
- `legacy_v0/` deleted entirely (328 files — preserved in git history)
- All `__pycache__/` directories deleted
- 5 stale management documents deleted (pre-rename brainstorming, session briefings, strip plan)
- 5 stale handoff archives deleted
- Root `uv.lock` deleted (stale artifact from deleted root pyproject.toml)
- Demo files, `.gitignore`, `CLAUDE.md`, strategy docs — all scrubbed
- grep verification: zero hits in active tracked files

**COMPLETE — Semantic Review Pass (CEO Directive, 2026-03-11)**

Full semantic scan of active codebase (`boyce/`, `demo/`) for music/media/streaming/
advertising/entertainment fingerprints. Zero findings. All test fixtures use
neutral domains (generic e-commerce, SaaS subscriptions, spy-thriller integration test).
No artist/label/track schemas, no video streaming context, no advertising/ad delivery
references, no music industry terminology anywhere in active code or docs.
CEO Directive fully satisfied.

*Wed March 11 (Will — full day):*
- [ ] Integration test: `boyce-init` + MCP connection across all hosts
- [ ] Query battery: full run across all working surfaces (fixes applied live)

*Thu March 12 (Will — full day):*
- [ ] Retest fixes from Wednesday
- [ ] Version decision (v1.0 or iterate)
- [ ] PyPI publish (Will executes — credentials required) — if version decision is go

*Fri March 13 (Will — flex):*
- [ ] Close gaps from Wed-Thu / retest if needed
- [ ] Begin Phase C if published Thursday

#### Phase C — Amplification [AFTER PUBLISH]
- [ ] MCP directory submissions (Smithery, PulseMCP, mcp.so, Glama)
- [ ] Integration guides published as public docs
- [ ] Local LLM setup guide (Ollama/vLLM via LiteLLM)
- [ ] Content: Story 1 (adoption/IC) — clean README, 30-second demo
- [ ] Content: Story 2 (trust/C-suite) — Null Trap technical essay
- [ ] **VS Code extension** — thin TypeScript GUI over HTTP API, marketplace publish (Block 1b)

**COMPLETE — Support Readiness (2026-03-11)**

Pre-publish support infrastructure in place:
- `.github/ISSUE_TEMPLATE/bug_report.yml` — structured bug report form
- `.github/ISSUE_TEMPLATE/feature_request.yml` — feature request form
- `.github/ISSUE_TEMPLATE/setup_help.yml` — setup/connection troubleshooting form
- `.github/ISSUE_TEMPLATE/config.yml` — links to FAQ and support email
- `docs/troubleshooting.md` — comprehensive FAQ covering install, boyce-init, MCP setup,
  snapshot issues, NL→SQL, DB connection, HTTP API
- `README.md` — Support section added, links to issue templates and FAQ

**ACTION NEEDED:** Issue templates and docs currently reference will@boyce.io,
but boyce.io email is not yet functional (domain in transfer). Temporarily
replace all will@boyce.io references with will@convergentmethods.com before
publish. Swap back to will@boyce.io once domain DNS is configured.

**Gate:** Will has personally tested all surfaces. `pip install boyce` works in a clean env. Real queries produce correct results. Version decision made by Will on Thursday March 12.

#### Block 1b — VS Code Extension
See `_strategy/plans/block-1b-vscode-extension.md` for detailed plan.

The HTTP API (`boyce serve --http`) was built specifically to unlock this. The extension is a
thin TypeScript wrapper — chat panel, schema tree, query runner — calling Boyce's HTTP
endpoints. All LLM and SQL logic stays inside Boyce. The extension never touches credentials
or models directly.

**First monetization vehicle.** Core library stays MIT forever. The extension ships free on
the VS Code Marketplace, with a pro tier (visual schema explorer, team sharing, unlimited
history) added later once organic demand is established. Same pattern as Docker, Terraform,
Grafana: engine free, experience layer paid.

Legacy reference implementation (schema tree, SQL editor, completions, query console) was
used as reference for the scaffold and is preserved in git history.
The `extension/` scaffold (built 2026-03-11) replaces it with HTTP API calls.

### Block 2 — Protocol & Parsers (Days 11-25)
**Goal:** SemanticSnapshot spec published standalone. Remaining parsers. Spec documentation.

See `_strategy/plans/block-2-protocol-and-parsers.md` for detailed plan.

- [ ] Publish SemanticSnapshot JSON Schema as standalone specification
- [x] Define and implement parser plugin interface
- [x] Build parsers: DDL, SQLite, Django, SQLAlchemy, Prisma, CSV/Parquet (6/8 done)
- [ ] Build parsers: SQLMesh, Alembic (remaining 2)
- [x] Build auto-discovery CLI (`boyce-scan` command)
- [ ] Build standalone dbt→snapshot converter CLI
- [x] Test suite audit: validate all parsers against `test_warehouses/` fixtures
- [ ] Publish StructuredFilter spec as NL-to-SQL intermediate representation

**Gate:** `boyce-scan ./any-project/` produces a SemanticSnapshot from any common source. Spec published.

### Block 3 — Data Quality & Protocol v0.2 (Days 26-35)
**Goal:** Data quality becomes a first-class protocol feature. The competitive wedge against dbt MCP.

See `_strategy/plans/block-3-governance-and-ecosystem.md` for detailed plan.

- [ ] Schema extension: FieldDef gains `quality_profile` (null_pct, cardinality, freshness, drift_threshold)
- [ ] Ingest-time profiling (move from query-time to ingest-time)
- [ ] Drift detection on re-ingest
- [ ] Enhanced `ask_boyce` response with quality signals
- [ ] Policy stubs: `pii_flag`, `access_roles`, `aggregation_only` on FieldDef
- [ ] Planner accuracy eval suite (20+ benchmark queries)
- [ ] Protocol v0.2 release with migration guide

**Gate:** SemanticSnapshot self-describes data quality. Protocol v0.2 published.

### Block 4 — Ecosystem & Adoption (Days 36-45)
**Goal:** Entity intelligence, pipeline parser coverage, content series, external adoption signals.

See `_strategy/plans/block-4-ecosystem-and-adoption.md` for detailed plan.

- [ ] Entity `priority_score` computed at ingest time (FK centrality, join fanout)
- [ ] Airflow DAG parser
- [ ] Technical content series beyond the Null Trap (3 essays)
- [ ] Adoption outreach — StructuredFilter as IR for other NL-to-SQL tools

**Gate:** At least one external tool produces or consumes SemanticSnapshot. 2+ essays published.

---

## What This Is Not

- Not a BI tool (no dashboards, no charts, no visualizations)
- Not a data warehouse (no storage, no compute)
- Not a standalone query UI (no frontend — the interface IS the MCP protocol and the library API)
- Not a competitor to dbt (complement — dbt describes transformations, we describe meaning)
- Not an open-core bait-and-switch (the engine is MIT forever; monetization lives in the experience layer — IDE extensions, hosted services)

---

## Development Workflow

**Claude Code only.** Plans, builds, reviews, ships. Follows the four-phase protocol in `~/.claude/CLAUDE.md`: Assess & Plan → Build → Verify → Ship. Model tiering by task — top tier for planning and architecture, cheaper tiers for mechanical execution.

---

## Current Technical State (as of 2026-03-05)

### What works end-to-end
- Full NL → SQL pipeline: QueryPlanner (LiteLLM) → kernel → SQL (`ask_boyce`)
- Host-LLM path: `get_schema` returns full schema + StructuredFilter docs; `build_sql` compiles deterministically — no Boyce LLM needed
- Deterministic multi-dialect SQL: Redshift, Postgres, DuckDB, BigQuery
- Dijkstra join-path resolution (NetworkX SemanticGraph)
- Live Postgres adapter: read-only, asyncpg, EXPLAIN pre-flight, column profiling
- Null Trap detection at query time (Stage 2.5 in `ask_boyce` and `build_sql`)
- Redshift guardrails: lint + NULLIF cast rewrites
- Snapshot persistence (`_local_context/`) — survives restarts
- 10 parsers: dbt_manifest, dbt_project, lookml, sqlite, ddl, csv, parquet, django, sqlalchemy, prisma
- Parser plugin interface: `SnapshotParser` protocol, `ParserRegistry`, auto-detection via `parse_from_path()`
- Scan CLI (`boyce-scan`): walks directories, auto-detects sources, JSON report to stdout
- Init wizard (`boyce-init`): detects + configures Claude Desktop, Cursor, Claude Code
- Direct CLI: `boyce ask "..."` (NL→SQL, stdout), `boyce chat "..."` (conversational, intent routing)
- HTTP API: `boyce serve --http` (Starlette, Bearer auth, `/schema` `/build-sql` `/ask` `/chat` `/query` `/profile` `/ingest`)
- Business definitions: `ingest_definition` MCP tool + `DefinitionStore`
- Audit logging: `AuditLog` append-only JSONL, called from `server.py`
- Demo kit: docker scenario, seed data, DEMO_SCRIPT.md
- **260 pytest tests (256 pass, 4 skipped when pyarrow absent), all passing in ~10s**

### Delivery surface
| Surface | Entry point | Use case |
|---------|------------|----------|
| MCP stdio | `boyce` (no args) | Claude Desktop, Cursor, Claude Code, Cline, Continue.dev, Windsurf |
| Direct CLI | `boyce ask "..."` | Shell scripts, one-off queries |
| Conversational CLI | `boyce chat "..."` | Interactive terminal use |
| HTTP REST | `boyce serve --http` | VS Code extension, web dashboards, cron jobs |
| VS Code extension | Marketplace install | 30M+ VS Code users — first monetization surface (Block 1b, scaffold built 2026-03-11) |
| Python library | `from boyce import kernel` | Custom agent integrations |

### Recent completions
- **2026-03-11:** VS Code extension scaffold — `extension/` directory, 11 files, 1,424 LOC TypeScript, compiles clean. Steps 1-4 of Block 1b (scaffold, HTTP client, chat panel, schema tree) built in one session.
- **2026-03-07:** `src` layout migration — `boyce/boyce/` → `boyce/src/boyce/`; CWD namespace conflict eliminated; 260 tests green
- **2026-03-07:** Client reference strip (Phases 1-3) + git history squash — repo is clean, pre-commit hook active
- **2026-03-07:** Sprint plan locked — Phase A complete, Phase B testing sprint week of March 9
- **2026-03-06:** Delivery surface expansion — `get_schema`, `build_sql`, `boyce-init`, Direct CLI, HTTP API (52 new tests)
- **2026-03-05:** Full codebase rename to `boyce` (package, module, env vars, MCP tools, docs, CI)
- **2026-03-04:** Name confirmed as Boyce. Domain `boyce.io` purchased.
- **2026-03-01:** Scan CLI (`boyce-scan`) implemented — 10 tests
- **2026-03-01:** All 10 parsers operational with 177 parser tests
- **2026-02-28:** Legacy code quarantined, CI/CD rewritten, docs aligned

### Key files
| File | Role |
|------|------|
| `boyce/src/boyce/server.py` | 8 MCP tools; `get_schema`, `build_sql`, `ask_boyce`, etc. |
| `boyce/src/boyce/kernel.py` | Deterministic SQL kernel |
| `boyce/src/boyce/types.py` | Protocol contract (SemanticSnapshot, Entity, FieldDef) |
| `boyce/src/boyce/cli.py` | Unified CLI dispatcher (`boyce ask`, `boyce chat`, `boyce serve`) |
| `boyce/src/boyce/http_api.py` | Starlette REST API with Bearer auth + `/chat` endpoint |
| `boyce/src/boyce/init_wizard.py` | `boyce-init` — MCP host config wizard |
| `boyce/src/boyce/scan.py` | Scan CLI (`boyce-scan`) — directory walker + auto-detect |
| `boyce/src/boyce/adapters/postgres.py` | Read-only DB adapter |
| `boyce/src/boyce/planner/planner.py` | NL → StructuredFilter |
| `boyce/src/boyce/parsers/dbt.py` | dbt manifest + YAML parsers |
| `boyce/src/boyce/parsers/detect.py` | Auto-detect + parse_from_path |
| `boyce/tests/conftest.py` | Ensures real `mcp` package loaded before stub guards |
| `boyce/tests/test_kernel_tools.py` | 30 tests for `get_schema`, `build_sql`, `_validate_structured_filter` |
| `boyce/tests/test_init.py` | 22 tests for init wizard |
| `boyce/tests/verify_eyes.py` | 15 offline tests (~4s) |
| `boyce/tests/test_parsers.py` | Parser tests (all 10 parsers) |
| `boyce/tests/test_scan.py` | Scan CLI tests (10 tests) |
| `extension/src/extension.ts` | VS Code extension entry point (5 commands, status bar) |
| `extension/src/client.ts` | `BoyceClient` — HTTP client for all 8 API endpoints |
| `extension/src/process.ts` | `BoyceProcess` — auto-spawns `boyce serve --http` |
| `_strategy/MASTER.md` | **This file** |

---

## Using This File

**Start a coding session (Claude Code):** CLAUDE.md loads automatically. It points here.
For detailed technical context, read `server.py` and `types.py` directly.

**Start a planning session (Opus/GPT):** Paste this file. It is self-contained.
No other document is required to begin a productive strategic conversation.

**Update discipline:**
- Decision made → update relevant section
- Work completed → check the box in the execution plan
- New open question → add inline with `[OPEN]` tag
- Significant new information → update "Current Technical State"
- Do not create new strategy documents. Update this one.
