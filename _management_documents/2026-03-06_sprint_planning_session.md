# Sprint Planning Session — 2026-03-06
**Context:** Block 1 active. Three-day sprint + VS Code weekend. Planning conversation between Will and CTO (Claude Code, Opus).

This document preserves the full planning discussion so it survives context compaction. Decisions made here feed into updated block plans.

---

## Current State (Entering This Session)

### Completed (all time, Block 0 + Block 1 partial)
- [x] Full codebase rename: datashark-protocol -> boyce
- [x] PyPI namespace placeholder (0.0.1)
- [x] GitHub org: boyce-io
- [x] Domain: boyce.io
- [x] 8 MCP tools: ingest_source, ingest_definition, get_schema, build_sql, solve_path, ask_boyce, query_database, profile_data
- [x] `boyce-init` setup wizard (Claude Desktop, Cursor, Claude Code auto-config)
- [x] Direct CLI: `boyce ask "..."` and `boyce chat "..."`
- [x] HTTP API: `boyce serve --http` (Starlette, Bearer auth, /chat intent routing)
- [x] 10 parsers operational
- [x] Scan CLI (`boyce-scan`)
- [x] 260 tests passing (~10s, no DB)

### Completed (This Session)
- [x] `__init__.py` public API exports: `from boyce import process_request, SemanticSnapshot, lint_redshift_compat, SemanticGraph` now works
- [x] Editable install path fixed (was pointing to old DataShark location)
- [x] `.gitignore` entry for `legacy_v0/extensions_mcp/.datashark/`
- [x] `block-1-ship-it.md` updated: status Active, [name] -> boyce, steps marked
- [x] VS Code extension plan written: `_strategy/plans/block-1b-vscode-extension.md`
- [x] MASTER.md updated: monetization strategy, "Designed for Agent Discovery", two-LLM-roles principle, Cline/Continue.dev, delivery surface table
- [x] README.md fixed: two-path MCP setup, correct API key guidance, all 8 tools, `pip install boyce` as primary install, non-confrontational tone
- [x] Claude Code permission settings updated: `defaultMode: "default"`, git push unblocked, uv/node/npm allowed

### Remaining Block 1 Items
- [ ] **Client reference strip** — see `2026-03-06_client_reference_strip_plan.md`
- [ ] **`src` layout migration** (namespace conflict fix) — REQUIRED BEFORE PUBLISH
- [ ] Publish to PyPI (0.1.0) — Will executes (credentials)
- [ ] Integration guides (Claude Desktop, Cursor, Claude Code, Cline, Continue.dev)
- [ ] Local LLM setup guide (Ollama/vLLM via LiteLLM)
- [ ] MCP directory submissions (Smithery, PulseMCP, mcp.so, Glama)
- [ ] Validation protocol — open-source test database + structured query battery (see below)
- [ ] Null Trap technical essay
- [ ] VS Code extension (Block 1b — "Day 4 / weekend")

---

## Decision: `src` Layout Migration First

**What:** Move `boyce/boyce/` -> `boyce/src/boyce/`. Update `pyproject.toml` build config.

**Why first:** We are about to publish 0.1.0. The directory structure we publish with becomes
the structure users and contributors expect. Changing from `boyce/boyce/` to `boyce/src/boyce/`
after publish means a structural breaking change that touches every contributor's dev setup,
every doc reference, and every CI path. Doing it before publish means it's just the way it was
from day one. The cost is the same either way — a few file moves and a `pyproject.toml` update
— but doing it pre-publish has zero downstream impact, while doing it post-publish creates churn.

**The namespace conflict it fixes:** When running Python from the repo root, the outer `boyce/`
directory shadows the installed `boyce` package because Python finds it as a namespace package
via CWD before the editable install's finder resolves. The `src/` buffer directory cannot be
mistaken for a package (no `__init__.py`), so the conflict disappears entirely. This is the
Python Packaging Authority recommended layout.

**Model assignment:** Sonnet 4.6 — mechanical file move + pyproject.toml update + verify tests pass.

**Sub-items:**
1. Move `boyce/boyce/` -> `boyce/src/boyce/`
2. Update `pyproject.toml`: add `[tool.setuptools.packages.find] where = ["src"]` or hatch equivalent
3. Update any internal path references (test scripts that use `_PROTO_ROOT`, conftest.py)
4. `uv pip install -e boyce/` — verify editable install resolves correctly
5. Run full test suite: `python -m pytest boyce/tests/ -v`
6. Verify imports from neutral CWD: `from boyce import process_request, SemanticSnapshot`
7. Verify imports FROM repo root (the bug this fixes): same import, should now work
8. Update CLAUDE.md path references if any

---

## Decision: Validation Protocol Uses Open-Source Databases Only

### Policy
No client-specific databases, schemas, or data are used in any testing, validation, or
documentation within this repository. All validation uses open-source, publicly available
databases that anyone can reproduce.

Private testing against production databases is Will's responsibility, performed outside this
repo on separate infrastructure. Results are not committed to the repo.

### Open-Source Test Databases

| Database | What it is | Why it's useful | Complexity |
|----------|-----------|-----------------|------------|
| **demo/magic_moment seed.sql** | Purpose-built NULL trap scenario (1,000 rows) | Tests the core safety differentiator; already exists in repo | Low (1 table) |
| **jaffle_shop** (dbt) | Fictional e-commerce: customers, orders, payments | Well-known in dbt community, good multi-join testing; fixtures already in test_warehouses/ | Low-medium (3 tables) |
| **Pagila** | Postgres port of Sakila — DVD rental store | 15 tables, rich FK relationships, good for Dijkstra join testing, temporal queries, aggregations | Medium-high |
| **Chinook** | Digital music store: artists, albums, tracks, invoices, customers | 11 tables, analytical query patterns, good persona-based testing | Medium |

**Recommendation:** Pagila as the primary validation database. It has the right complexity —
enough tables and joins to exercise Dijkstra path resolution, temporal filters, aggregations,
and NULL scenarios, while being small enough to run in Docker instantly. Chinook as a secondary
database for diversity. jaffle_shop and the demo seed for targeted tests.

### Validation Protocol — Reusable Testing Framework

**Where it lives:** `boyce/tests/validation/` — inside the test suite, not published to PyPI.

**Contents:**
- `validation_protocol.md` — Human-readable protocol: what to test, how, acceptance criteria
- `query_battery.json` — Canonical test queries with expected behavior annotations
- `docker-compose.yml` — Spins up Postgres with Pagila + Chinook pre-loaded
- `run_validation.py` — Automated runner for Path 2 surfaces, produces structured report
- `results/` — Timestamped JSON reports from each validation run

**Purpose:** Every delivery surface must pass the validation protocol before publication.
New surfaces (e.g., VS Code extension) get a row in the matrix and must pass before
marketplace publish. This is a regression gate, not a one-off test.

### Integration Surface Matrix

Every validation run tests across all available delivery surfaces:

| Surface | Path | What's tested |
|---------|------|--------------|
| Claude Code (MCP) | Path 1 — host LLM | get_schema -> host reasons -> build_sql -> query |
| Cursor (MCP) | Path 1 — host LLM | Same flow, different host |
| Claude Desktop (MCP) | Path 1 — host LLM | Same flow, GUI host |
| Direct CLI (`boyce ask`) | Path 2 — internal planner | Full ask_boyce pipeline |
| HTTP API (`/chat`) | Path 2 — internal planner | Intent routing + pipeline |
| Cline (VS Code MCP) | Path 1 — host LLM | MCP-native VS Code path |
| VS Code extension | Path 2 — HTTP API | TypeScript GUI -> HTTP -> pipeline (when built) |

**Note on Path 1 testing:** MCP host testing (Claude Code, Cursor, etc.) requires the host
LLM to drive the interaction. This cannot be fully automated — Will runs the queries manually
in each host and records results. The protocol has a human-executed section for Path 1 and
an automated section for Path 2.

### Query Battery Design

**Two categories:**

**Category A — Structured capability tests** (exercises specific pipeline features):
1. **Simple aggregation** — e.g., "Total rental revenue by customer segment last 90 days."
   Tests: entity resolution, metric aggregation, temporal filter.
2. **Multi-join** — Query requiring Dijkstra path resolution across 2+ entities (e.g., films
   through inventory through rentals through customers). Tests: join path selection, edge weight.
3. **NULL trap scenario** — Query that would silently drop rows without NULL handling.
   Tests: the core safety differentiator.
4. **Schema exploration** — "What tables have financial data?" Tests: `/chat` intent routing,
   `get_schema`, non-SQL use cases.
5. **Dialect edge case** — Query requiring Redshift-specific handling. Tests: safety.py linting.

**Category B — Real-world conversational prompts** (tests actual human use cases):

The critical insight from Will: the battery must include messy, ambiguous, non-technical
prompts — not just cleanly structured SQL questions. The point is to test what real people
actually type.

Personas:
- **Junior data analyst** — limited SQL knowledge, conversational, vague:
  "what are the finance tables?" / "show me top customers" / "monthly trend report"
- **Staff data engineer** — domain-specific, complex, assumes context:
  "how did rental patterns change across store locations over the past year?" /
  "reconcile the revenue between payments and rental counts"
- **Non-technical stakeholder** — pure business language:
  "are we losing customers?" / "what's our best category?" / "compare this month to last"

Specific queries will be developed against the Pagila/Chinook schemas. The personas and
intent categories are stable; the specific queries are schema-dependent.

### What We Measure (per query, per surface)

| Metric | What it means |
|--------|--------------|
| **SQL correctness** | Does it produce valid SQL? |
| **Execution success** | Does the SQL run without error? |
| **Result accuracy** | Spot-check: are the numbers right? (for queries where we know the answer) |
| **Response time** | End-to-end latency |
| **Safety layer fires** | Did NULL trap / EXPLAIN / lint catch what it should? |
| **Planner accuracy** | Did the planner pick the right entities, fields, joins? |
| **Graceful failure** | For ambiguous/impossible queries: does it fail informatively? |
| **UX friction** | How many steps / interactions to get the answer? |

---

## Sprint Sequencing (Dependency Chain)

```
Step 0a: Client reference strip       [Sonnet]  <- FIRST
Step 0b: src layout migration          [Sonnet]  <- SECOND, no other deps
    |
Step 1: PyPI publish (0.1.0)          [Will]    <- depends on src layout
    |
    +---> Step 2a: Integration guides  [Sonnet]  <- parallel after PyPI
    |     (Claude Desktop, Cursor,
    |      Claude Code, Cline,
    |      Continue.dev, local LLM)
    |
    +---> Step 2b: MCP directory       [Sonnet drafts, Will submits]
    |     submissions                             <- parallel after PyPI
    |
    +---> Step 2c: Validation protocol [Opus designs, Sonnet implements]
    |     design + implementation                 <- parallel, no PyPI dep
    |
Step 3: Run validation protocol        [Automated + Will for Path 1]
    |   (Docker Pagila/Chinook,                   <- needs protocol + Docker
    |    all surfaces)
    |
Step 4: Null Trap essay               [Will writes, Opus reviews]
    |                                             <- can use validation results
    |
Step 5: VS Code extension             [Opus reviews plan, Sonnet builds]
    (Block 1b — "Day 4 / weekend")               <- needs HTTP API (done)
                                                     + validation before publish
```

### Parallelization Notes
- Steps 2a, 2b, 2c are fully independent — can all run in parallel after PyPI
- Step 2c (validation protocol) has no PyPI dependency — could start before publish
- The essay (Step 4) structure/outline can be drafted in parallel; validation results
  strengthen it but are not required for the core argument
- VS Code extension (Step 5) only requires HTTP API (already built) + validation to test

---

## Model Assignment Summary

| Task | Model | Rationale |
|------|-------|-----------|
| Client reference strip | Sonnet 4.6 | Mechanical find-and-replace + git filter-repo |
| `src` layout migration | Sonnet 4.6 | Mechanical file move, pyproject.toml update |
| PyPI publish | Will + Sonnet support | Build verification, credential-gated |
| Integration guides (5 hosts + local LLM) | Sonnet 4.6 | Template writing, config snippets |
| MCP directory descriptions | Sonnet 4.6 | Drafting copy |
| Validation protocol design | Opus 4.6 | Strategic: query battery, measurement framework |
| `run_validation.py` implementation | Sonnet 4.6 | Straightforward test automation |
| Validation execution (Path 2) | Sonnet 4.6 | Automated testing |
| Validation execution (Path 1) | Will manually | MCP host testing requires human in loop |
| Null Trap essay — outline + argument | Opus 4.6 | Strategic framing, competitive thesis |
| Null Trap essay — code examples | Sonnet 4.6 | Implementation |
| VS Code extension — architecture review | Opus 4.6 | Validate plan against HTTP API surface |
| VS Code extension — TypeScript build | Sonnet 4.6 | Implementation |

---

## Open Items to Resolve

1. **Pagila vs. Chinook as primary:** Pagila has more tables and richer joins (15 tables,
   deep FK graph). Chinook is simpler but has good analytical patterns (11 tables). Recommend
   Pagila as primary, Chinook as secondary diversity check.

2. **Query battery finalization:** Specific queries for Category B depend on the chosen
   database schema. Framework and personas are stable now; specific queries are next.

3. **Essay structure:** The Null Trap argument doesn't depend on a production warehouse.
   The demo kit (`demo/magic_moment/`) already has the scenario. Consider: the essay uses
   the reproducible Docker demo (reader can run it themselves), not production results.

4. **VS Code extension testing:** The validation protocol should include a VS Code extension
   row in the surface matrix. Run the full battery through the extension before marketplace publish.

---

## Will's Explicit Requirements Captured

- `src` layout fix is a **requirement** before anything else, not optional
- **No client references** in any committed file, git history, or published artifact — ever
- Validation uses **open-source databases only** (Pagila, Chinook, jaffle_shop, demo seed)
- Private production testing happens **outside this repo** on Will's separate machine
- Validation protocol is a **reusable, living framework** that gates every delivery surface
- Query battery must include **real-world conversational prompts** from varied personas
  (junior analyst, staff engineer, non-technical stakeholder)
- **Every delivery surface must be validated** before publication
- Plans must capture **model assignments** (Sonnet/Opus) on every task
- Plans must have **detailed sub-items**, not just high-level bullets
- **Decisions discussed in session must be written to files immediately**
