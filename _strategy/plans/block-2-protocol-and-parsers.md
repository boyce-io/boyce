# Plan: Block 2 — Protocol & Parsers
**Status:** Pending
**Created:** 2026-02-28
**Timeline:** Days 11-25 after name is locked
**Depends on:** Block 1 (Ship It) — PyPI published, codebase renamed

## Goal
SemanticSnapshot spec published as a standalone specification. Parser coverage expanded to
10+ source formats. Auto-discovery CLI operational. Any developer with any common database
toolchain can generate a SemanticSnapshot in under 5 minutes.

## Prerequisites
- Block 1 complete: package on PyPI, tests passing, live warehouse validated
- Parser plugin interface designed (Step 1 below)

---

## Implementation Steps

### Step 1: Parser Plugin Interface
- Define `SnapshotParser` protocol:
  ```python
  class SnapshotParser(Protocol):
      def detect(self, path: Path) -> float:  # confidence 0.0-1.0
      def parse(self, path: Path) -> SemanticSnapshot:
      def source_type(self) -> str:  # "dbt_manifest", "django", etc.
  ```
- Refactor existing parsers (dbt, lookml) to implement this interface
- Create parser registry: auto-discovery of installed parsers
- Document how community contributors add new parsers
- File: `parsers/base.py` (interface), `parsers/registry.py` (discovery)
- Cursor model: **Opus 4.6** (cross-module refactor touching parsers + detect.py)

### Step 2: Raw DDL Parser
- Parse `CREATE TABLE` statements from `.sql` files
- Extract: table name, column names, types, PKs, FKs, constraints, comments
- Handle: multi-statement files, schema-qualified names, Redshift/Postgres/MySQL dialects
- Produce: SemanticSnapshot with entities, fields, and FK-based joins
- File: `parsers/ddl.py`
- Test: fixtures with various DDL flavors
- Cursor model: **Sonnet 4.6 Thinking** (SQL parsing requires careful control flow)

### Step 3: SQLite Direct Introspection
- Accept a `.sqlite` / `.db` file path
- Introspect via `sqlite3` stdlib: `sqlite_master`, `PRAGMA table_info()`, `PRAGMA foreign_key_list()`
- Produce: SemanticSnapshot with entities, fields, FK joins
- Zero external dependencies (sqlite3 is stdlib)
- File: `parsers/sqlite.py`
- Cursor model: **Sonnet 4.6** (straightforward, well-documented stdlib API)

### Step 4: Django Models Parser
- Parse `models.py` files using AST (no Django import required)
- Extract: model names → entities, field definitions → fields, ForeignKey/ManyToMany → joins
- Handle: abstract models, model inheritance, custom managers (ignore), Meta.db_table
- File: `parsers/django.py`
- Cursor model: **Sonnet 4.6 Thinking** (AST traversal requires reasoning)

### Step 5: SQLAlchemy Models Parser
- Parse SQLAlchemy model files using AST
- Extract: `class User(Base)` → entity, `Column(String)` → field, `ForeignKey` → join
- Handle: declarative base and mapped_column (SQLAlchemy 2.0) styles
- File: `parsers/sqlalchemy.py`
- Cursor model: **Sonnet 4.6 Thinking** (similar to Django parser)

### Step 6: Prisma Schema Parser
- Parse `.prisma` schema files (Prisma Schema Language)
- Extract: models → entities, fields → fields, `@relation` → joins
- Handle: enums, composite types, `@@map` table name overrides
- File: `parsers/prisma.py`
- Cursor model: **Sonnet 4.6** (Prisma schema is simple and well-structured)

### Step 7: SQLMesh Models Parser
- Parse SQLMesh model definitions (Python or SQL)
- Extract: model names, columns, grain, references
- Signals vendor neutrality — shows the protocol works beyond dbt
- File: `parsers/sqlmesh.py`
- Cursor model: **Sonnet 4.6 Thinking** (less common format, needs careful research)

### Step 8: Alembic Migration Parser
- Parse Alembic migration files, reconstruct current schema state
- Walk the migration chain: extract `op.create_table`, `op.add_column`, etc.
- Produce: SemanticSnapshot representing the current schema
- File: `parsers/alembic.py`
- Cursor model: **Opus 4.6** (complex — must replay migration history correctly)

### Step 9: CSV/Parquet Header Parser
- Infer schema from CSV headers + sample rows (type inference)
- Infer schema from Parquet metadata (types are explicit)
- Produce: SemanticSnapshot with one entity per file, fields from columns
- File: `parsers/tabular.py`
- Cursor model: **Sonnet 4.6** (straightforward, pandas/pyarrow)

### Step 10: Auto-Discovery CLI (`scan` command)
- New CLI entry point: `[name] scan <directory>`
- Walks the directory tree, runs each parser's `detect()` method
- Presents discovered sources, asks for confirmation or runs automatically
- Merges all discovered sources into a unified SemanticSnapshot
- Handles conflicts (same table defined in DDL and Django model)
- File: `cli/scan.py` or extend existing CLI
- Cursor model: **Opus 4.6** (cross-module integration, conflict resolution logic)

### Step 11: Standalone dbt→Snapshot Converter CLI
- `[name] convert manifest.json > snapshot.json`
- Simple wrapper around existing parser, but standalone (no MCP server needed)
- Useful for CI/CD pipelines, pre-computation, sharing snapshots
- Cursor model: **Sonnet 4.6** (thin wrapper)

### Step 12: Test Suite Audit & Fixture Gap Analysis
- Run every parser against every relevant fixture in `test_warehouses/`
- Document: which parsers produce valid snapshots, which fail, failure modes
- Identify gaps: parsers with no test fixture (Django, SQLAlchemy, Prisma, SQLMesh, Alembic)
- For each gap: find the best available open-source repo to use as a fixture, or create a synthetic one
- **Comprehensive fixture refresh:** The original fixture selection was done 6 months ago with limited tooling. Now that the product architecture is mature and all parsers are implemented, do a full search for the best available open-source database projects for EACH parser type:
  - dbt: Is jaffle_shop still the best small fixture? Are there better enterprise-scale dbt projects than mattermost/dagster?
  - DDL: Northwind and WWI are classics but T-SQL dialect — find a Postgres/Redshift-native DDL fixture
  - LookML: Is thelook still the richest available LookML project?
  - Django: Find the best open-source Django project with rich models (e.g., Saleor, Wagtail, Taiga)
  - SQLAlchemy: Find the best open-source SQLAlchemy project (e.g., Airflow metadata, Superset)
  - Prisma: Find the best open-source Prisma schema (e.g., Cal.com, Documenso)
  - SQLMesh: Find representative SQLMesh project definitions
  - Alembic: Find a project with a long, well-structured migration history
  - CSV/Parquet: Find small, well-typed datasets for type inference testing
- Evaluation criteria: schema complexity (table count, FK density), real-world representativeness, community maintenance status, size (<1MB for committed, any size for cloned), dialect coverage
- Evaluate: are these the best test warehouses available? Search for better options if gaps exist.
- Update `test_warehouses/README.md` with results
- Establish update protocol: how to refresh external repos, how to validate after updates
- File: `test_warehouses/`, `tests/`
- Cursor model: **Sonnet 4.6** (systematic testing, no complex logic)

### Step 13: Publish SemanticSnapshot Spec
- Extract the SemanticSnapshot JSON Schema into a standalone spec document
- Separate repository or directory: `spec/` with versioned schema files
- Write the specification narrative: what each field means, validation rules, examples
- Publish: GitHub, potentially a simple spec website
- Include StructuredFilter spec as "the IR for NL-to-SQL"
- Executor: Claude Code drafts spec; Will reviews and publishes

---

## Acceptance Criteria
- [ ] Parser plugin interface defined and documented
- [ ] All existing parsers refactored to implement the interface
- [ ] At least 8 new parsers implemented and tested (DDL, SQLite, Django, SQLAlchemy, Prisma, SQLMesh, Alembic, CSV/Parquet)
- [ ] `[name] scan ./` auto-discovers and parses sources from a mixed-format project
- [ ] `[name] convert` produces standalone snapshot files
- [ ] SemanticSnapshot spec published as standalone document with JSON Schema
- [ ] StructuredFilter spec published alongside
- [ ] Cold-start to useful snapshot in under 2 minutes on a clean machine (`pip install [name] && [name] scan ./`)
- [ ] Every parser validated against at least one real-world fixture from `test_warehouses/`
- [ ] Fixture gap analysis complete — synthetic fixtures created for parsers with no external repo
- [ ] Comprehensive fixture refresh complete — each parser type evaluated against best available open-source projects
- [ ] All tests pass (existing + new parser tests)

## Risks / Open Questions
- AST-based parsing (Django, SQLAlchemy) is fragile against unconventional code patterns — keep parsers conservative, return partial results rather than failing
- SQLMesh format may evolve — design parser to degrade gracefully
- Spec publication format: simple markdown + JSON Schema, or something more formal? Decision deferred to execution time.
- Parser conflict resolution in `scan`: when multiple parsers find the same table, which wins? Proposed: highest-confidence parser wins, with user override.

## Parser Priority Tiers

All parsers ship. No deprioritization. But build order matters for unlocking the scan CLI:

| Tier | Parsers | Why first |
|------|---------|-----------|
| **Tier 1** (build first) | DDL, SQLite, CSV/Parquet | Universal formats. Zero-dependency. Three fundamentally different input types producing the same SemanticSnapshot — this IS the protocol story. Scan CLI gates on these. |
| **Tier 2** (build next) | Django, SQLAlchemy, Prisma | ORM ecosystems. Large user bases. AST-based — similar patterns, build together. |
| **Tier 3** (build last) | SQLMesh, Alembic | Niche but strategic. SQLMesh signals vendor neutrality. Alembic is complex (migration replay). |

## Parallelization Notes
- Steps 2-9 (individual parsers) are fully independent — can run as parallel Cursor handoffs
- Step 1 (plugin interface) must complete first — all parsers implement it
- Step 10 (scan CLI) depends on Tier 1 completion (DDL + SQLite + CSV/Parquet)
- Step 12 (spec publication) can proceed in parallel with parser work
