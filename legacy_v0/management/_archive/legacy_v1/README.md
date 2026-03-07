# Legacy V1 Archive

This directory contains code that was moved during the "Codebase Simplification" to align with the new Agentic/Stealth strategy.

## What Was Moved

### 1. Ingestion Logic (`ingestion/`)
- **Location:** `datashark-mcp/src/datashark/ingestion/`
- **Reason:** We no longer write parsers. The Agent (Cursor) handles ingestion by reading raw text and generating SemanticSnapshots.
- **Contents:**
  - `looker/adapter.py` - LookerAdapter (old parser-based ingestion)

### 2. Planner Logic (`planner/`)
- **Location:** `datashark-mcp/src/datashark_mcp/planner/`
- **Reason:** We no longer write NLP logic in Python. The Agent handles natural language → structured filter conversion.
- **Contents:**
  - `planner.py` - Main planner orchestration
  - `mapper/concept_mapper.py` - Concept mapping logic
  - `grain/grain_resolver.py` - Grain resolution logic
  - `join/join_planner.py` - Join path inference
  - `sql/sql_builder.py` - Planner's SQL builder (different from core SQLBuilder)

### 3. Adapters (`adapters/`)
- **Location:** `core/adapters/`
- **Reason:** We no longer write parsers. The Agent handles all ingestion.
- **Contents:**
  - `factory.py` - AdapterFactory
  - `base.py` - Base adapter class
  - `postgres.py`, `redshift.py`, `tableau.py`, `dbt.py`, `airflow_adapter.py` - Source-specific parsers

### 4. Engine (`engine_old/`)
- **Location:** `datashark-mcp/src/datashark_mcp/kernel/engine.py`
- **Reason:** Heavy orchestration logic. The new architecture uses a minimal entrypoint: `process_request(snapshot, structured_filter)` -> `SQL`
- **Contents:**
  - `engine.py` - DataSharkEngine with full orchestration (Planner, AirGapAPI, GraphProjector)

## What Remains (Minimal Kernel)

The simplified codebase now contains only:

- **`datashark/core/`** - The Deterministic Kernel
  - `types.py` - Schema (SemanticSnapshot, Entity, FieldDef, JoinDef)
  - `sql/builder.py` - The Compiler (SQLBuilder)
  - `validation.py` - The "Bouncer" (Schema validation)
  - `api.py` - Minimal entrypoint: `process_request(snapshot, structured_filter)` -> `SQL`
  - `audit.py` - Audit logging

- **`concepts/`** - Agent Instructions
  - `INGESTION.md` - "How to read a DB" (for the Agent)

- **`_local_context/`** - Local snapshots (git-ignored)

## Migration Notes

Files that import from archived modules will need updates:
- `datashark-mcp/src/datashark/core/service.py` - Imports LookerAdapter (archived)
- `datashark-mcp/src/datashark/core/cli.py` - Imports DataSharkEngine (archived)
- `datashark-mcp/src/datashark/core/server.py` - Imports AdapterFactory (archived)

These files may need to be updated to use the new minimal `api.py` entrypoint or archived themselves if they're not part of the minimal kernel.
