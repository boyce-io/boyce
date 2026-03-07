# Documentation Pruning Archive — December 2025

Content removed from active documents during consolidation to minimize drift and token waste.

## From PROJECT_SUMMARY.md

Removed duplicated content that should live in authoritative truth surfaces:

- Detailed "Project Overview" section (vision/philosophy restated from 00_MASTER_STRATEGY.md)
- "Recent Achievements" detailed list (execution status belongs in 02_TASKS.md)
- "Phase Definitions" pointer (redundant with Context Anchors)
- "Client Surfaces" section (not executive status)
- Detailed "Document Navigation Guide" (simplified to essential pointers)

Kept:
- Context Anchors (quick map)
- Executive Status (concise, <= 15 lines)
- Current Risks / Decision Points (<= 15 lines)
- Document Navigation (pointers only)

## From 01_ARCHITECTURE.md

Removed aspirational APIs and long module inventories that drift:

- Detailed "Top-Level Stack" section with file locations and entrypoints (drifts with code changes)
- "Supporting Modules" detailed inventory (drifts with code changes)
- "VS Code extension" implementation details (not architectural contract)
- `engine.simulate()` API definition (does not exist in Phase 1, deferred to Phase 2)
- Detailed "Environment & Infrastructure" section (operational, not architectural invariant)
- Verbose "Temporal Logic & Filter Hardening" section (simplified to invariant statement)
- Redundant invariant restatements (consolidated)

Kept:
- Determinism invariant (core contract)
- Air-Gap Seam definition (Phase 2 deferred, but contract)
- Source-Agnostic Ingestion Contract (invariant)
- Temporal Logic & Filter Invariant (core contract)
- Core Invariants list (essential constraints)
