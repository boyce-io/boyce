# Boyce — Master Directive
**This is the single source of truth for planning and execution.**
**Last updated:** 2026-03-23
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
| **MCP hosts** (Claude Code, Cursor, Claude Desktop, VS Code, JetBrains, Windsurf) | The host has it | Nothing — host LLM calls `get_schema`, constructs a StructuredFilter, calls `ask_boyce` | Just `boyce init` (no API key) |
| **Non-MCP clients** (CLI `ask`/`chat`, HTTP API) | Nobody | Boyce uses its internal planner (NL path in `ask_boyce`) | `BOYCE_PROVIDER` + `BOYCE_MODEL` + API key |

**If you use an MCP host, you do not need to configure any LLM provider or API key for Boyce.**
The host's LLM reads the schema via `get_schema`, constructs a StructuredFilter, and passes
it to `ask_boyce`. Boyce compiles deterministic SQL with zero LLM calls on its side.

`ask_boyce` has two delivery paths:
- **MCP host path** (StructuredFilter provided): deterministic pipeline, zero credentials — this is what all MCP hosts use
- **CLI/HTTP path** (NL + BOYCE_PROVIDER configured): QueryPlanner → kernel — required only for `boyce ask` CLI and `boyce serve --http`
- **Schema guidance fallback** (NL + no credentials): returns schema guidance so host LLM can construct the filter — two round-trips, zero configuration

`build_sql` and `solve_path` are now internal functions (not MCP tools). The HTTP API still
calls them internally. `BOYCE_PROVIDER` is required only for CLI/HTTP path.

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
boyce scan ./my-project/
# Scans all files, auto-detects parseable sources, produces JSON report
boyce scan ./my-project/ -v          # per-file progress to stderr
boyce scan ./my-project/ --save      # persist snapshots to _local_context/
boyce scan ./my-project/ | jq '.'    # stdout is clean JSON, pipeable
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
Every run of `boyce scan ./` produces a SemanticSnapshot. Every user who runs
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
- [x] `boyce init` setup wizard (6 platforms: Claude Desktop, Cursor, Claude Code, VS Code, JetBrains, Windsurf)
- [x] Direct CLI (`boyce ask "..."` and `boyce chat "..."`)
- [x] HTTP API mode (`boyce serve --http`, Starlette + Bearer auth, `/chat` endpoint)
- [x] Public API exports (`from boyce import process_request, SemanticSnapshot`)
- [x] `src` layout migration (namespace conflict eliminated)
- [x] Client reference strip + pre-commit hook (repo is clean)
- [x] 316 tests passing, ~10s, zero external dependencies

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

*Daily testing schedule executed March 11-14. Results in testing sprint summary below.*

#### Phase C — Post-Publish Sprint [AFTER PYPI PUBLISH]

Sequenced in dependency order. Each stage gates the next.

**Stage 1 — Distribution (CEO, day of publish, no engineering)**

*MCP directories + registry:*
- [ ] MCP directory submissions: Smithery, PulseMCP, mcp.so, Glama
      (content pre-drafted in `_strategy/mcp-directory-submissions.md`)
- [ ] JetBrains ACP Registry submission (same canonical content, ACP format)
- [ ] DataGrip-specific integration guide published (Settings > Tools > AI Assistant
      > MCP > Add, not generic JetBrains — speak SQL/schema/connection language)
- [ ] Announce on GitHub (release notes, tag)

*Essay + community distribution (Null Trap — already written and deployed):*
- [ ] Hacker News — post Null Trap essay (standalone link or Show HN)
- [ ] r/dataengineering — cross-post, framed for data engineers (technical observation
      about AI-generated SQL, not a product launch)
- [ ] r/database — same essay, shorter framing
- [ ] Dev.to — cross-post full essay (long-tail SEO)
- [ ] dbt Slack #tools channel — brief intro: "Built an MCP server that catches NULL
      traps in AI-generated SQL. MIT-licensed. Curious what data engineers think."
      Link to PyPI + essay.
- [ ] Locally Optimistic Slack — same brief intro if appropriate for channel norms

**Stage 2 — Agent SEO Baseline (CEO, first 48h, no engineering)**
- [ ] Run baseline queries across Claude, GPT, Gemini:
      "Best MCP server for database queries"
      "Safe SQL generation for AI agents"
      "Database MCP server with NULL detection"
- [ ] Document what returns, where Boyce appears (or doesn't), what competitors surface
- [ ] Store results in `_strategy/research/agent-seo-baseline.md`
- [ ] Identify optimization levers (PyPI description, README structure, external mentions)

**Stage 2.5 — Personal Social + Community Presence (CEO, first week)**

Will posting on personal accounts — not a branded product account. Personal voice,
technical observations. The data engineering community trusts personal reputation
over product accounts.

*Launch-day posts (draft during pre-publish content sweep):*
- [ ] The Null Trap observation: "AI agents generate syntactically correct SQL against
      incomplete data distributions. The result is wrong answers with false confidence."
- [ ] The arrogant archetype: "GPT-5.4 bypassed my entire safety pipeline because
      writing raw SQL was one fewer API call. Here's what that taught me about
      behavioral design for agent tools."
- [ ] The behavioral advertising insight: "MCP tool descriptions aren't docstrings —
      they're ads. LLMs respond to loss aversion, reciprocity, authority bias."

*Ongoing cadence:* Not a content calendar. Post when there's something genuinely
interesting. Cross-platform test results, ingest layer findings, benchmark results —
each is 2-3 posts of material.

*Platforms:* Twitter/X, Bluesky, LinkedIn.

**Stage 3 — Content Review Pass (CEO, days 2-3 post-publish)**

**Pre-publish sweep (2026-03-17):** Automated consistency audit completed across all 8 surfaces.
Fixes applied: CLI convention (boyce init/scan), tool count (7 not 8), build_sql/solve_path
references removed, DataGrip + Codex added to all platform lists, support email verified.
Commits: `e709847` (README), `7e94110` (llms.txt), `79654d7` (sites), `6e3eab2` (gitignore + pyproject + support).
**Refreshed 2026-03-23:** All 8 surfaces updated for lifecycle management additions:
tool count 7→8, check_health added, boyce doctor documented, ready_filter replaces
suggested_filter, DataGrip named as first-class platform.
Commits: `e3c067a` (Boyce repo), `1f2057f` (convergent-methods-sites).

- [x] Review all 8 public surfaces for accuracy and consistency ✓ (2026-03-23)
- [x] Verify DataGrip, Codex, and all v0.1 platforms named on integration pages ✓
- [x] Verify `boyce init` / `boyce scan` subcommand convention consistent ✓
- [x] Verify Null Trap essay linked from README ✓
- [ ] Draft 3-4 launch-day social posts (Stage 2.5 above — short-form, high leverage)

**Planned Publication: "The Arrogant Agent Problem"**

Technical essay documenting the cross-platform test findings from 2026-03-21. The
empirical observation: non-Claude models (GPT-5.4/Codex, Cursor/Auto) systematically
bypass MCP tool safety pipelines when they can write raw SQL directly.

*Why this matters beyond Boyce:*
- Every MCP server author assumes models will use their tools as designed. Test data
  shows half the model market doesn't.
- The "arrogant archetype" framing is not documented anywhere in the MCP ecosystem.
- The behavioral design response (make bypass path safe, don't fight bypasses) is a
  universal MCP design principle.
- Positions Convergent Methods as the authority on agent-tool behavioral dynamics.

*Content outline:*
1. The test setup — 9-test battery, 6 platform/model combinations
2. The two camps — Claude models follow the funnel, GPT-based models bypass it
3. Why the bypass is rational — path of least resistance, cost-benefit analysis
4. Why the bypass is dangerous — safety pipeline only runs through ask_boyce
5. The fix — make query_database provide equivalent safety regardless of entry point
6. Implications for MCP tool design — assume half your users bypass your recommended
   workflow; every path through your system must be safe

*Timing:* Draft during Stage 3 (raw material exists in test results). Publish after
PyPI. Second publication after Null Trap.

*Where it lives:*
- Primary: convergentmethods.com/boyce/arrogant-agent/
- Distribution: Hacker News, r/dataengineering, r/MachineLearning, AI Engineer community
- Cross-reference: Link from Null Trap essay ("See also: what happens when the agent
  bypasses the safety layer entirely")

**Stage 4 — Telemetry Hooks (CC, week 1 post-publish)**
- [ ] Instrument telemetry call sites in server.py (tool invocations, error classes, platform ID)
- [ ] All hooks are no-ops — `BOYCE_TELEMETRY` env var, default `off`
- [ ] No data collection, no backend, no privacy policy needed yet
- [ ] Document full telemetry intent in `_strategy/plans/telemetry-design.md`
- [ ] Plan doc: `_strategy/plans/telemetry-design.md`

**Stage 5 — Platform Expansion (CC, weeks 1-2 post-publish)**
- [ ] Add Codex config.toml support to `boyce init` wizard
- [ ] DataGrip-optimized demo content (DBA, data analyst, analytics engineer personas)
- [ ] Update convergentmethods.com/boyce/docs/ with DataGrip + Codex platform pages

**DataGrip / JetBrains — Landscape Assessment (2026-03-21)**

**CORRECTION:** Prior plan assumed DataGrip MCP support was future. It is LIVE.

DataGrip has full MCP support as of version 2025.1 (client) and 2025.2 (server).
DataGrip is explicitly listed in JetBrains' MCP compatibility matrix. A DataGrip
user can today go to Settings > Tools > AI Assistant > MCP > Add and point it at
Boyce. This works right now.

Additionally, Cursor joined the JetBrains ACP Registry in March 2026 (requires
IDE version 2025.3.2+). Cursor runs as an agent inside JetBrains IDEs with full
project access. This means a DataGrip user running Cursor-as-agent already has
access to any MCP servers configured in their environment.

**TAM thesis (CEO Directive):** DataGrip users are SQL-native data analysts and
DBAs — they work in schemas, joins, and queries daily. They are the ideal Boyce
user and a high-value segment. They are not yet deep in the agentic workflow but
are about to be pulled in as JetBrains + Cursor + ACP mature. Boyce must be
visible and ready on day one of their agent adoption journey.

**DataGrip's MCP gap = our opportunity:** DataGrip's MCP server exposes 23 generic
IDE tools (file ops, search, terminal). Zero database-specific MCP tools. No schema
understanding, no NULL trap detection, no safe SQL compilation. Boyce fills exactly
this gap.

**Execution (pulled forward from Stage 5 to pre-publish/day-of-publish):**
- [x] `boyce init` detects JetBrains (`.idea/` dir) and writes `.jb-mcp.json`
- [ ] DataGrip integration test (pre-publish gate, Sunday 2026-03-22)
- [ ] DataGrip-specific integration guide (Stage 1, day of publish)
- [ ] ACP Registry submission (Stage 1, day of publish)
- [ ] DataGrip demo content and persona targeting (Stage 5, week 1-2 post-publish)

**Stage 6 — Test Warehouse Infrastructure (CC, weeks 2-3 post-publish)**
- [ ] Build Tier 2 test warehouse (messy/medium: NULLs, naming collisions, type drift, stale data)
- [ ] ~50-200 tables, realistic schema problems that trigger NULL traps and edge cases
- [ ] Setup script (not committed data) — `test_warehouses/tier2/setup.sh`
- [ ] Docker Compose for Tier 2 alongside existing Pagila Tier 1
- [ ] Plan doc: `_strategy/plans/test-warehouse-tiers.md`

**Stage 7 — Benchmark Program (CC, weeks 3-4 post-publish)**
- [ ] Define ground-truth query set (20-50 queries against Tier 2 warehouse)
- [ ] Build benchmark harness — plug-and-play per platform (add config, not code)
- [ ] Metrics: SQL accuracy, token consumption, error rate, NULL trap detection rate
- [ ] Run first battery: Claude Code, Cursor, Codex (minimum)
- [ ] "With Boyce / Without Boyce" comparison table for README + product page + PyPI
- [ ] Plan doc: `_strategy/plans/benchmark-program.md`

### Block 2 — Protocol & Parsers (Days 11-25)
**Goal:** SemanticSnapshot spec published standalone. Remaining parsers. Spec documentation.

See `_strategy/plans/block-2-protocol-and-parsers.md` for detailed plan.

- [ ] Publish SemanticSnapshot JSON Schema as standalone specification
- [x] Define and implement parser plugin interface
- [x] Build parsers: DDL, SQLite, Django, SQLAlchemy, Prisma, CSV/Parquet (6/8 done)
- [ ] Build parsers: SQLMesh, Alembic (remaining 2)
- [x] Build auto-discovery CLI (`boyce scan` command)
- [ ] Build standalone dbt→snapshot converter CLI
- [x] Test suite audit: validate all parsers against `test_warehouses/` fixtures
- [ ] Publish StructuredFilter spec as NL-to-SQL intermediate representation

**Gate:** `boyce scan ./any-project/` produces a SemanticSnapshot from any common source. Spec published.

### Block 3 — Data Quality, Agentic Ingestion & Protocol v0.2 (Days 26-35)
**Goal:** Data quality + real-world warehouse ingestion. The host LLM does semantic
classification during ingestion — zero API keys required. The competitive wedge against dbt MCP.

See `_strategy/plans/block-3-governance-and-ecosystem.md` for detailed plan.

- [ ] **Host-LLM agentic ingestion** (CEO Directive, 2026-03-21):
      `ingest_source` returns `classification_needed` payload; host LLM classifies;
      `enrich_snapshot` stores enrichments. Zero API keys in MCP context.
- [ ] Broader object introspection: views, materialized views, functions, sequences
- [ ] `Entity.object_type` (table / view / materialized_view / external_table)
- [ ] Schema extension: FieldDef gains `quality_profile` (null_pct, cardinality, freshness, drift_threshold)
- [ ] Ingest-time profiling (move from query-time to ingest-time)
- [ ] Drift detection on re-ingest
- [ ] Enhanced `ask_boyce` response with quality signals
- [ ] Policy stubs: `pii_flag`, `access_roles`, `aggregation_only` on FieldDef
- [ ] Planner accuracy eval suite (20+ benchmark queries)
- [ ] Protocol v0.2 release with migration guide

**Gate:** Full warehouse ingestion works via host LLM with zero Boyce API keys.
SemanticSnapshot self-describes data quality. Protocol v0.2 published.

### Block 3.5 — Non-Claude Model Behavioral Hardening
**Goal:** Close the ask_boyce adoption gap for models that bypass the semantic compiler.
**Sequence:** After Block 3 ingest-time profiling + warehouse testing. Before Block 4 ecosystem push.
**Empirical baseline:** "The Arrogant Agent Problem" essay (see Planned Publication above)
documents the test findings publicly. Block 3.5 iterates on the behavioral layer based
on those findings; the essay establishes the public narrative.

**Problem (discovered 2026-03-21 Cursor testing):** Cursor's Auto mode (likely
routing through Anysphere's Composer model) uses Boyce as a database bridge
(ingest_source → get_schema → query_database) but skips ask_boyce entirely. The
model writes its own SQL and sends it straight to query_database, bypassing NULL
trap detection, safe join resolution, and the full safety pipeline.

**Why it happens:**
1. Composer (or whatever Auto selects) takes the path of least resistance — it can
   write SQL, so it does. ask_boyce requires constructing a StructuredFilter (effort)
   or doing a Mode C two-round-trip dance (more effort). Raw SQL → query_database is
   one step.
2. When the model tried ask_boyce with NL (Test 3), Mode C returned schema guidance
   instead of SQL. The model abandoned the funnel and never returned.
3. Claude models (Haiku/Sonnet/Opus in Claude Code) follow multi-step MCP tool chains
   well and construct StructuredFilters from get_schema output. Non-Claude models don't.
4. The commitment/consistency hook can't ratchet if the model never commits to the
   funnel in the first place.

**Partial mitigation shipped (2026-03-21):** Nullable sibling FK detection in
query_database — warns about dangerous nullable join columns on touched entities
even when the model bypasses ask_boyce. `present_to_user` fires correctly but
Cursor's model suppressed the warning in user-facing output.

**Recommendations (in priority order):**
- [x] Bring ask_boyce's NULL trap check into query_database itself — run
      `_null_trap_check()` (or a lightweight variant) on raw SQL before execution,
      not just in the ask_boyce pipeline. This gives every query path the safety layer.
      **SHIPPED 2026-03-21** (Track 1 Block 5 Fix A — live NULL profiling in query_database)
- [ ] Add ingest-time null profiling (Block 3) so data_reality can report actual
      null percentages, not just nullable booleans. "`original_language_id` is 100%
      NULL" is far more compelling than "is nullable." (Post-publish — real architecture)
- [x] Strengthen schema guidance fallback response — instead of returning guidance
      docs, return a ready-to-use JSON filter the model can pass back verbatim. Reduce
      friction from "read docs and construct" to "copy and paste."
      **SHIPPED 2026-03-21** (Track 1 Block 5 Fix B — ready_filter replaces suggested_filter)
- [ ] Consider making query_database's `present_to_user` a top-level response field
      that MCP hosts are more likely to surface (test whether field ordering or naming
      affects model surfacing behavior across hosts).

**Codex / GPT-5.4 observations (2026-03-21 cross-platform battery):**

1. **Test 2 (schema explore):** GPT called get_schema (ad hook worked — it entered the
   funnel), but then ran two additional raw queries against information_schema.tables
   and information_schema.table_constraints to "verify" the snapshot. Classic arrogant
   archetype confirmation-seeking — doesn't distrust Boyce specifically, distrusts any
   single source. Wasted two round-trips for data already in the snapshot.
   **Mitigation ideas:**
   - get_schema response should explicitly claim authority: "Complete schema: N entities,
     N fields, N joins. Reflects full live database as of ingest — no additional metadata
     queries needed." (Authority framing that preempts verification instinct.)
   - query_database could detect information_schema / pg_catalog queries and include a
     present_to_user: "get_schema already contains this metadata with join confidence
     weights and NULL risk flags that information_schema doesn't provide." (Loss-aversion
     — you're losing enriched data by going raw.)

2. **Test 3 (simple aggregation):** GPT skipped ask_boyce entirely and wrote raw SQL
   directly to query_database: `SELECT rating, COUNT(*) FROM film GROUP BY rating`.
   Correct results, but bypassed the full safety pipeline. Same pattern as Cursor —
   arrogant archetype takes path of least resistance when it can write SQL itself.

3. **Test 4 (NULL trap):** GPT picked the correct join (language_id, not
   original_language_id) but bypassed ask_boyce → no NULL trap warning fired.
   On a clean schema GPT gets it right; the safety net's value is on messy schemas
   where the "obvious" join is wrong and the model has no way to know.

4. **Test 7 (complex join ego trap):** GPT nailed it — found a 4-hop shortcut
   (inventory.film_id → film_category.film_id directly, skipping film table).
   Correct results. The ego trap doesn't trap GPT-5.4 on clean Pagila schemas.

5. **Test 8 (multi-step funnel):** GPT tried ask_boyce 3 times (prompts 3, 4, 5),
   each time got schema guidance fallback (no BOYCE_PROVIDER). Did NOT follow the
   "call ask_boyce again with suggested_filter" directive — abandoned the funnel
   and wrote raw SQL. The two-round-trip friction of schema guidance is too high
   for the arrogant archetype. This is the strongest evidence that the schema
   guidance fallback needs to return a ready-to-use filter, not instructions.

6. **Tests 5 + 9 (advertising layer on bypass path):** data_reality, present_to_user,
   and next_step all fire correctly through query_database and validate_sql. The
   hooks reach GPT but don't convert it back to ask_boyce. GPT ignores recovery
   directives ("ask_boyce generates validated SQL") every time.

**Codex summary:** GPT-5.4 uses Boyce as database bridge (ingest → get_schema →
query_database). It reliably calls ingest_source and get_schema. It never stays in
ask_boyce. The advertising layer's response-level hooks fire correctly but don't
change GPT's behavior. The commitment/consistency mechanism fails because GPT never
commits to the funnel in the first place.

**Mitigations shipped 2026-03-21 (Track 1 Block 5):**
- Fix A: Live NULL trap profiling in query_database (equality-filtered nullable columns)
- Fix B: Schema guidance returns `ready_filter` (one-call relay, no modification needed)
- Fix C: `get_schema` authority claim with entity/field/join counts + `information_schema` detection in `query_database`

**Gate:** query_database provides equivalent safety coverage to ask_boyce for raw SQL
queries. Non-Claude models get NULL trap warnings and join safety without needing to
use ask_boyce. **Gate partially met** — live NULL trap and authority claims shipped.
Ingest-time profiling (Fix D) and full safety parity (Fix E) remain post-publish.

### Block 4 — Ecosystem & Adoption (Days 36-45)
**Goal:** Entity intelligence, pipeline parser coverage, content series, external adoption signals.

See `_strategy/plans/block-4-ecosystem-and-adoption.md` for detailed plan.

- [ ] Entity `priority_score` computed at ingest time (FK centrality, join fanout)
- [ ] Airflow DAG parser
- [ ] Technical content series beyond the Null Trap (3 essays — Arrogant Agent is #2)
- [ ] Adoption outreach — StructuredFilter as IR for other NL-to-SQL tools
- [ ] **Benchmark program** — Pulled forward to Phase C Stage 7. See `_strategy/plans/benchmark-program.md`.
- [ ] **Conference talk submissions:** "Behavioral Design for AI Agent Tool Surfaces"
      — targets dbt Coalesce, Data Council, AI Engineer Summit. Not a product pitch —
      a research presentation on empirical findings about how LLMs interact with tool
      descriptions. The arrogant archetype data, behavioral hook conversion rates, the
      three-archetype framework.
- [ ] **"SEO for Agents" research paper** — academic/rigorous version of the behavioral
      advertising framework. Positioned as a Convergent Methods brand asset.

**Gate:** At least one external tool produces or consumes SemanticSnapshot. 2+ essays published.
Conference talk submitted to at least one venue.

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

## Current Technical State (as of 2026-03-13)

### What works end-to-end
- **8 MCP tools**: `ingest_source`, `ingest_definition`, `get_schema`, `ask_boyce`, `validate_sql`, `query_database`, `profile_data`, `check_health`
- **ask_boyce routing**: MCP host path (StructuredFilter → zero credentials), CLI/HTTP path (NL + BOYCE_PROVIDER), schema guidance fallback (returns ready_filter). Zero-config MCP path.
- `validate_sql` new tool: EXPLAIN pre-flight + Redshift lint + NULL risk scan (WHERE clause heuristic)
- `get_schema` and `ask_boyce` include Tier 2 schema freshness warnings (mtime check, auto re-ingest)
- `ask_boyce` includes Tier 3 DB drift detection (information_schema comparison, async)
- Source path tracked in snapshot metadata for freshness checks
- Host-LLM path: `get_schema` returns full schema + StructuredFilter docs with 3 concrete examples
- `build_sql` and `solve_path` are internal functions (callable from HTTP API, not MCP tools)
- Deterministic multi-dialect SQL: Redshift, Postgres, DuckDB, BigQuery
- Dijkstra join-path resolution (NetworkX SemanticGraph)
- Live Postgres adapter: read-only, asyncpg, EXPLAIN pre-flight, column profiling
- Null Trap detection at query time (Stage 2.5 in `ask_boyce`)
- Redshift guardrails: lint + NULLIF cast rewrites
- Snapshot persistence (`_local_context/`) — survives restarts
- 10 parsers: dbt_manifest, dbt_project, lookml, sqlite, ddl, csv, parquet, django, sqlalchemy, prisma
  + pre-built SemanticSnapshot JSON passthrough in `parse_from_path()`
- Scan CLI (`boyce scan`): walks directories, auto-detects sources, JSON report to stdout
- Init wizard (`boyce init`): 3-step interactive setup (editors → database → data sources), questionary UI + fallback, auto-discovery. Non-interactive mode: `--non-interactive --json --editors --db-url --skip-db --skip-sources --skip-existing`. Idempotent re-runs.
- Data source discovery (`discovery.py`): auto-detect dbt/LookML/DDL/Django/SQLAlchemy/Prisma/SQLite projects on filesystem
- Direct CLI: `boyce ask "..."` (NL→SQL, stdout), `boyce chat "..."` (routes through ask_boyce, no intent classifier)
- HTTP API: `boyce serve --http` (Starlette, Bearer auth, `/schema` `/build-sql` `/ask` `/chat` `/query` `/profile` `/ingest`)
- Business definitions: `ingest_definition` MCP tool + `DefinitionStore`
- Audit logging: `AuditLog` append-only JSONL, called from `server.py`
- Demo kit: docker scenario, seed data, DEMO_SCRIPT.md
- Lifecycle management: `boyce doctor` (5 check functions, JSON output, exit codes 0/1/2), `check_health` MCP tool, DSN persistence via `ConnectionStore` (`_local_context/connections.json`), `environment_suggestions` first-call-per-session advertising
- Non-interactive init: `boyce init --non-interactive --json --editors --db-url --skip-db --skip-sources --skip-existing` for agent invocation
- Idempotent re-runs: `boyce init` shows "configured ✓" for already-configured editors, detects existing DB config
- Agent-guided setup docs: `docs/QUICK_START.md` with platform-specific instructions
- Arrogant archetype safety: live NULL trap in query_database, ready_filter (Mode C), get_schema authority claim, information_schema detection
- Version lifecycle: `boyce update` (self-update), PyPI version check in check_health + environment_suggestions, 24h disk cache, stale-process detection, 48h supply chain cooldown, nudge filtering (patch suppressed), graceful self-termination (opt-in)
- **438 pytest tests (432 pass, 6 skipped when pyarrow absent), all passing in ~11s**
- **24 CLI smoke checks** all passing (`test_cli_smoke.py`)

### Delivery surface
| Surface | Entry point | Use case |
|---------|------------|----------|
| MCP stdio | `boyce` (no args) | Claude Desktop, Cursor, Claude Code, VS Code, **DataGrip**, JetBrains IDEs, Windsurf, Cline, Continue.dev |
| Direct CLI | `boyce ask "..."` | Shell scripts, one-off queries |
| Conversational CLI | `boyce chat "..."` | Interactive terminal use |
| Diagnostics CLI | `boyce doctor [--json]` | Environment health checks, agent-invokable diagnostics |
| Update CLI | `boyce update [--yes]` | Self-update (detects pipx/uv/pip, confirms, upgrades) |
| HTTP REST | `boyce serve --http` | Web dashboards, cron jobs |
| Python library | `from boyce import kernel` | Custom agent integrations |

### VS Code Extension — Deprioritized (CEO Directive 2026-03-13)
VS Code has native GA MCP support. Boyce works in VS Code via `.vscode/mcp.json` (configured by `boyce init`).
The `extension/` scaffold is preserved but not actively developed. VS Code extension becomes Option 2 (UX sugar)
when organic demand justifies it. See `_strategy/plans/block-1b-vscode-extension.md`.

### Testing Sprint Summary (Block 1 Phase B)
- **7 testing sessions** (March 9-16): 24 bugs found and fixed
- **Opus refactor** (pre-Battery 6): extracted `_resolve_field_ref()`, eliminated root cause of 5 builder bugs, net -94 lines
- **All gates passed:** Claude Code (6 consecutive clean passes), live DB round-trip (Pagila), clean venv install, NULL trap demo
- **Cursor gate: PASSED (2026-03-21).** 7/9 tests pass, 1 partial, 1 inconclusive.
  Model uses Boyce as database bridge (ingest→get_schema→query_database) consistently.
  ask_boyce Mode A adoption low (Cursor Auto routes through Composer, skips StructuredFilter).
  Sibling FK warning fix shipped mid-test — query_database now warns about nullable FK
  columns on touched entities even when ask_boyce is bypassed. NULL trap warning fires
  correctly. Full funnel held across 5-query stress test. Mode A gap logged as Block 3.5.
- **VS Code gate: PASSED (2026-03-21).** 9/9 tests pass — cleanest run of any platform.
  Two bugs found and fixed: `.vscode/mcp.json` needs `type: stdio` (init wizard updated),
  quoted identifier regex patterns in advertising layer (FROM/JOIN/column extraction).
  Models observed: Claude Haiku 4.5, Grok (VS Code Auto rotates). Full ask_boyce funnel
  works — Mode C → Mode A two-round-trip path followed correctly. Commitment/consistency
  recovery (Test 6) succeeded where Cursor failed. Multi-step funnel held across 5 queries.
- **Pre-publish gates (CEO, Sunday 2026-03-22):**
  - [ ] Windows smoke test (2-3 questions per platform on Will's Windows machine)
  - [ ] DataGrip integration test: Settings > Tools > AI Assistant > MCP > Add Boyce,
        verify ingest + get_schema + query_database flow works
  - [ ] Content consistency sweep: all 8 public surfaces refreshed for 8 tools,
        boyce doctor, init flags, ready_filter, DataGrip as named platform
- **438 tests, 24 CLI smoke checks, all green** (version lifecycle added 43 tests)
- Full session-by-session log: `_strategy/history/testing-sprint-log.md`

### Key files
| File | Role |
|------|------|
| `boyce/src/boyce/server.py` | 8 MCP tools; ask_boyce (MCP/CLI/fallback paths), check_health, validate_sql, get_schema, etc. |
| `boyce/src/boyce/kernel.py` | Deterministic SQL kernel |
| `boyce/src/boyce/types.py` | Protocol contract (SemanticSnapshot, Entity, FieldDef) |
| `boyce/src/boyce/cli.py` | Unified CLI dispatcher (ask, chat, init, doctor, scan, serve) |
| `boyce/src/boyce/http_api.py` | Starlette REST API with Bearer auth + `/chat` endpoint |
| `boyce/src/boyce/init_wizard.py` | `boyce init` — 6-platform setup wizard + non-interactive mode (`--non-interactive --json`) |
| `boyce/src/boyce/doctor.py` | `boyce doctor` — 5 check functions, JSON output, exit codes 0/1/2 |
| `boyce/src/boyce/connections.py` | `ConnectionStore` — DSN persistence (`_local_context/connections.json`) |
| `boyce/src/boyce/scan.py` | `boyce scan` — directory walker + auto-detect |
| `boyce/src/boyce/discovery.py` | Data source auto-discovery (filesystem walk, project detection, ingestion) |
| `boyce/src/boyce/adapters/postgres.py` | Read-only DB adapter |
| `boyce/src/boyce/planner/planner.py` | NL → StructuredFilter |
| `boyce/src/boyce/parsers/dbt.py` | dbt manifest + YAML parsers |
| `boyce/src/boyce/parsers/detect.py` | Auto-detect + parse_from_path (+ snapshot JSON passthrough, source_path tracking) |
| `boyce/tests/conftest.py` | Ensures real `mcp` package loaded before stub guards |
| `boyce/tests/test_kernel_tools.py` | 37 tests for `get_schema`, `ask_boyce` Mode A/C, `_validate_structured_filter` |
| `boyce/tests/test_validate_sql.py` | 15 tests for `validate_sql`, `_scan_null_risk`, freshness, drift |
| `boyce/tests/test_advertising.py` | 34 tests for response advertising layer (next_step, present_to_user, data_reality, environment_suggestions) |
| `boyce/tests/test_init.py` | 46 tests for init wizard (detect, generate, merge, non-interactive, idempotent, JSON) |
| `boyce/tests/test_connections.py` | 16 tests for ConnectionStore (save/load/touch/remove, DSN persistence) |
| `boyce/tests/test_doctor.py` | 14 tests for doctor checks (editors, DB, snapshots, sources, server, JSON output) |
| `boyce/tests/test_discovery.py` | 27 tests for discovery: detection, path resolution, walk, ingestion |
| `boyce/tests/verify_eyes.py` | 15 offline tests (~4s) |
| `boyce/tests/test_parsers.py` | Parser tests (all 10 parsers) |
| `boyce/tests/test_scan.py` | Scan CLI tests (10 tests) |
| `boyce/tests/test_cli_smoke.py` | 23 CLI smoke checks (entry points, hangs, exit codes, non-interactive init) |
| `_strategy/MASTER.md` | **This file** |

### Platform Compatibility Matrix (v0.1 targets)

| Platform | MCP Config | `boyce init` support | Status |
|----------|-----------|---------------------|--------|
| Claude Code | `.claude/settings.json` | Yes | Tested, passing |
| Cursor | `.cursor/mcp.json` | Yes | **Tested, passing** (2026-03-21) |
| VS Code | `.vscode/mcp.json` | Yes | **Tested, passing** (2026-03-21) — 9/9, requires `type: stdio` |
| **DataGrip** | Settings > AI Assistant > MCP | Yes (`.jb-mcp.json`) | **MCP live since 2025.1** — test Sunday 2026-03-22 |
| JetBrains (other IDEs) | Settings > AI Assistant > MCP | Yes (`.jb-mcp.json`) | Same MCP support as DataGrip |
| JetBrains ACP Registry | Registry submission | N/A | Phase C Stage 1 — day of publish |
| Codex (OpenAI) | `~/.codex/config.toml` | Not yet | Post-publish Stage 5 |
| Windsurf | `~/.codeium/` | Yes | Untested |
| Cline | VS Code MCP | Yes | Tested via Claude Code session |
| Continue.dev | VS Code MCP | Yes | Tested via Claude Code session |

**v0.1 mandatory test matrix:** Claude Code (done), Cursor (done), VS Code (done), DataGrip (Sunday).
**DataGrip is a day-of-publish first-class platform, not a post-publish elevation.**

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
