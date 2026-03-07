# DataShark — Architecture Contracts & Invariants

This file defines the strict architectural boundaries.

## 1. The Air-Gap Invariant (The Kernel)

**Rule:** The "Middle Bit" must be byte-stable and deterministic.

* **Input:** `SemanticSnapshot` (JSON) + `StructuredRequest` (Object).
* **Output:** SQL String.
* **Constraint:** The Kernel (SQLBuilder) **must not** perform any semantic inference. It is a dumb compiler. It must never see natural language.
* **Constraint:** The Kernel **must not** access raw data. It sees only the `SemanticSnapshot`.

## 2. The Ingestion Invariant (The Agent's Job)

**Rule:** We do not write Parsers; we write Validators.

* **Old Way:** Write `class LookMLParser` to read `.lkml` files.
* **New Way (Phase 1):** The Agent (Cursor) reads the `.lkml` file and generates a JSON `SemanticSnapshot`.
* **The Contract:** The Python codebase accepts **any** `SemanticSnapshot` that passes the `datashark.core.types` schema validation. It is agnostic to *how* that snapshot was created (Human, Agent, or Script).

## 3. The Progressive Enrichment Model

The System must handle varying levels of context depth.

* **Snapshot Object:** Must support "Partial" states.
    * *Example:* A Table entity may have `grain=UNKNOWN`. The Kernel must handle this (e.g., by preventing aggregations or asking for clarification) rather than crashing.
* **Confidence Score:** Ingestion Agents must attach a `confidence` level to their assertions (e.g., `inferred_from_name` vs `explicit_in_lookml`).

## 4. The Stealth Protocol (Security Invariant)

**Rule:** No Proprietary Data in the Repository.

* **Local Context:** All ingestion artifacts (Semantic Snapshots derived from local development or testing) must be stored in `_local_context/` (strictly git-ignored).
* **No Creds:** The Architecture forbids any module that requests, stores, or transmits database credentials in Phase 1. Database access is performed by the *User* (or the User's Agent) via their own existing tools, pasting the results into the system.

## 5. Stable Entrypoints

* **Kernel Entry:** `process_request(snapshot, structured_filter)` -> `SQL`
* **Ingestion Entry:** `validate_snapshot(json_blob)` -> `Boolean`
* **Agent Entry:** `concepts/INGESTION_CONCEPTS.md` (The "Manual" for the Agent)

## 6. Directory Structure Implication

```text
datashark/
├── core/                  # The Deterministic Kernel
│   ├── types.py           # The Schema (Snapshot, Entity, Filter)
│   ├── sql_builder.py     # The Compiler
│   └── validation.py      # The "Bouncer" (Schema Checks)
├── concepts/              # The Agent's "Brain" (Prompt Contexts)
│   ├── INGESTION.md       # "How to read a DB"
│   └── QUERYING.md        # "How to map text to filters"
└── _local_context/        # (IGNORED) Local snapshots (git-ignored)
```
