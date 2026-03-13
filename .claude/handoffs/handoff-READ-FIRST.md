# CEO Directive Handoff — Read This First

**Date:** 2026-03-13
**From:** CEO planning session (Will + Opus)
**To:** Claude Code (CTO/Architect)
**Priority:** CRITICAL — blocks Phase B completion and PyPI publish

---

## What Happened

Will and Opus conducted a full architectural review of Boyce's MCP tool surface, credential model, platform targeting, and VS Code extension strategy. All decisions are final. This handoff contains three implementation documents.

## Documents (read in order)

### 1. `handoff-architecture-revision.md`
**The master plan.** 10 changes covering:
- MCP tools consolidated from 8 → 7 (build_sql/solve_path internalized, validate_sql added)
- `ask_boyce` becomes tri-modal (StructuredFilter / NL+credentials / NL fallback with schema guidance)
- All tool descriptions rewritten for host-LLM consumption
- StructuredFilter docs get concrete examples
- Three-tier schema freshness (event-driven / mtime check / DB drift)
- Kill keyword intent classifier in cli.py
- VS Code extension deprioritized (VS Code native MCP is the path)
- Platform targeting expanded to 6 platforms
- Implementation order specified

### 2. `handoff-boyce-init-platforms.md`
**Platform detection specs.** Adding VS Code, JetBrains/DataGrip, and Windsurf to `boyce-init`. Config paths, key structures, detection signals, and test requirements for each.

### 3. `handoff-validate-sql-and-freshness.md`
**Detailed implementation specs** for:
- `validate_sql` new MCP tool (signature, pipeline, NULL risk scanner, tests)
- Schema freshness Tier 2 (mtime-based session-start check with auto re-ingest)
- Schema freshness Tier 3 (live DB drift detection via information_schema)
- Source path tracking in parsers

## Core Architectural Principle

**Boyce is invisible infrastructure.** In MCP host contexts (Claude Code, VS Code, Cursor, DataGrip, Windsurf), the host LLM does ALL reasoning. Boyce does ZERO reasoning. Boyce is a deterministic compiler and safety layer. The user never configures Boyce's LLM, never provides API keys for Boyce, never learns Boyce's vocabulary.

The QueryPlanner + LiteLLM exist only for standalone surfaces (CLI `boyce ask`, HTTP API, future VS Code extension) where no host LLM is present.

## Implementation Order

1. `ask_boyce` tri-modal (Change 2) — highest leverage, unblocks zero-config MCP
2. Tool descriptions (Change 3) — programs host LLM behavior
3. `validate_sql` (Change 9) — new tool, uses existing functions
4. `build_sql`/`solve_path` internalization (Change 1) — remove @mcp.tool() decorators
5. StructuredFilter examples (Change 4) — add to _STRUCTURED_FILTER_DOCS
6. Kill intent classifier (Change 6) — simplify cli.py and http_api.py
7. `boyce-init` platform updates (Change 8) — add VS Code, JetBrains, Windsurf
8. Schema freshness Tier 2 (Change 5) — mtime check
9. Schema freshness Tier 3 (Change 5) — DB drift warning
10. MASTER.md updates (Change 10) — reflect all changes

## Verification Requirements

- `python boyce/tests/verify_eyes.py` passes before and after EVERY change
- All existing 260 tests continue to pass
- New tests required for: validate_sql, ask_boyce Mode A, ask_boyce Mode C, freshness checks, new boyce-init platforms
- Update `test_kernel_tools.py` for build_sql/solve_path internalization (functions stay, @mcp.tool decorators removed)

## What NOT to Touch

- Kernel (`kernel.py`) — unchanged
- Builder (`builder.py`) — unchanged
- Types (`types.py`) — unchanged
- Graph (`graph.py`) — unchanged
- Safety (`safety.py`) — unchanged
- Parsers — unchanged (except adding source_path to metadata)
- StructuredFilter contract shape — unchanged
- Deterministic pipeline stages — unchanged
