# Session Briefing — March 4, 2026

> **SUPERSEDED** — This document is a historical snapshot from 2026-03-04, before the
> rename to Boyce and all Block 1 Phase A engineering. For current state, read
> `_strategy/MASTER.md`. Do not use this document to bootstrap a session.

---

---

## Product in One Sentence

An open-source (MIT) semantic protocol and safety layer for agentic database workflows — headless MCP server, deterministic SQL kernel, 10 parsers, scan CLI. Named "DataShark" internally, renaming to **Boyce** (pending Will's confirmation).

---

## What's Built (the engineering is done)

The core product works end-to-end. 30 source files, ~7,500 LOC, 212 tests passing.

| Capability | Status |
|------------|--------|
| Deterministic SQL kernel (same inputs → same SQL) | Done |
| 4 SQL dialects (Redshift, Postgres, DuckDB, BigQuery) | Done |
| Semantic graph + Dijkstra join resolution | Done |
| NL → StructuredFilter (LiteLLM, BYOK) | Done |
| NULL Trap detection (query-time profiling) | Done |
| Redshift safety linting + NULLIF rewrites | Done |
| EXPLAIN pre-flight validation | Done |
| 10 parsers (dbt manifest, dbt project, LookML, SQLite, DDL, CSV, Parquet, Django, SQLAlchemy, Prisma) | Done |
| Parser plugin interface + registry | Done |
| Scan CLI (`datashark-scan <path>`) | Done (this session) |
| Snapshot persistence (`_local_context/`) | Done |
| Business definitions (ingest + inject into planner) | Done |
| Audit logging (append-only JSONL) | Done |
| Demo kit (Null Trap scenario + Docker) | Done |

**What's NOT built yet (engineering remaining):**
- SQLMesh parser (Block 2, Tier 3 — signals vendor neutrality)
- Alembic migration parser (Block 2, Tier 3 — complex migration replay)
- Standalone dbt→snapshot converter CLI (Block 2, Step 11)
- SemanticSnapshot JSON Schema as standalone spec document (Block 2, Step 13)
- StructuredFilter spec publication (Block 2, Step 13)
- Data quality profiles baked into protocol schema (Block 3)
- Drift detection (Block 3)
- Policy stubs in FieldDef (Block 3)
- Planner accuracy eval suite (Block 3)
- Entity priority score (Block 4)
- Airflow DAG parser (Block 4)

---

## The Execution Blocks

### Block 0 — Name ← YOU ARE HERE
**Status:** Candidate selected ("Boyce"), awaiting Will's confirmation.
**Blocker:** Everything public-facing is gated on this.

### Block 1 — Ship It (Days 1-10 after name)
Get the product into the world. Seven steps:
1. Rename codebase (atomic commit — package, imports, CLI, docs)
2. Clean public API surface (`from boyce import process_request`)
3. Publish to PyPI
4. Deploy on a live warehouse (real-world proof point)
5. Write + publish the Null Trap essay
6. Submit to MCP directories (Smithery, PulseMCP, mcp.so, Glama)
7. Integration guides (Claude Desktop, Cursor, local LLM)

### Block 2 — Protocol & Parsers (Days 11-25)
Mostly done. Remaining: SQLMesh + Alembic parsers, specs publication, dbt converter CLI.

### Block 3 — Data Quality & Protocol v0.2 (Days 26-35)
The competitive wedge. Quality profiles in the protocol schema. Drift detection. Policy stubs.

### Block 4 — Ecosystem & Adoption (Days 36-45)
Content series, outreach, external adoption signals.

---

## The Name Change — All Fronts

The rename touches six distinct workstreams. Some are Will-only, some are Claude Code, some are both.

### Front 1: Confirm & Secure (Will only)
- [ ] Final decision on "Boyce"
- [ ] Buy boyce.io domain ($499 Namecheap)
- [ ] Register `boyce` on PyPI (placeholder 0.0.1 to lock namespace)
- [ ] Create GitHub org or repo (`boyce` or `boyce-io`)
- [ ] Initiate USPTO intent-to-use filing (Class 9 + Class 42) — can defer, but should be on the radar

### Front 2: Codebase Rename (Claude Code, single atomic commit)
- [ ] Rename `datashark-protocol/` → `boyce/` (or chosen directory name)
- [ ] Rename `datashark_protocol/` Python package → `boyce/`
- [ ] Update all imports across 30 source files
- [ ] Update `pyproject.toml` (package name, entry points, metadata)
- [ ] Update `server.py` tool names/descriptions
- [ ] Update CLI entry points: `boyce` (server), `boyce-scan` (scan)
- [ ] Update `README.md`, `CLAUDE.md`, `MASTER.md`, all `_strategy/` docs
- [ ] Update `quickstart.sh`
- [ ] Verify: all 212 tests pass under new name

### Front 3: PyPI Publication (Will + Claude Code)
- [ ] Finalize `pyproject.toml` metadata (version, description, license, classifiers)
- [ ] Build: `python -m build` → wheel + sdist
- [ ] Upload: `twine upload` or `uv publish`
- [ ] Verify: `pip install boyce` in clean venv, CLI starts

### Front 4: GitHub & Repository (Will + Claude Code)
- [ ] Rename GitHub repo (or create new one)
- [ ] Update remote URLs
- [ ] Set up GitHub Actions CI (currently stale — needs path updates)
- [ ] README that sells the product to agents and developers
- [ ] License file (MIT)

### Front 5: Website (Will, post-launch)
- [ ] Minimal landing page on boyce.io
- [ ] Content: what it is, install command, 30-second demo GIF, links to docs
- [ ] Can be as simple as a single-page static site or GitHub Pages
- [ ] Not a blocker for PyPI launch — can come after

### Front 6: Public Content & Directories (Will, post-launch)
- [ ] Null Trap essay (technical content, the launch story)
- [ ] MCP directory submissions (Smithery, PulseMCP, mcp.so, Glama)
- [ ] Claude Desktop + Cursor integration guides
- [ ] dbt community engagement

---

## What to Do Next (in order)

1. **Will:** Confirm "Boyce" (or provide alternative)
2. **Will:** Buy boyce.io, register PyPI placeholder, create GitHub org
3. **Claude Code:** Execute codebase rename (Front 2) — single session, atomic commit
4. **Together:** PyPI publication (Front 3)
5. **Will:** Live warehouse deployment + Null Trap essay
6. **Will:** Directory submissions + integration guides
7. **Claude Code:** Remaining Block 2 engineering (SQLMesh, Alembic, specs) — can run in parallel with steps 5-6

---

## Key Numbers

| Metric | Value |
|--------|-------|
| Source files | 30 |
| Lines of code | ~7,500 |
| Tests | 212 passing, 4 skipped (pyarrow) |
| Parsers | 10 operational |
| MCP tools | 6 |
| Test warehouses | 12 fixture projects |
| Time to run full test suite | ~9 seconds |
