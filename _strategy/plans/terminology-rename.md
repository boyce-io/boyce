# Plan: Terminology Rename — LLM-Optimized Component Naming
**Status:** COMPLETE
**Created:** 2026-03-24
**Updated:** 2026-03-24

---

## Decision Record

Replacing anthropomorphic Eyes/Brain/Nervous System metaphor with functional,
LLM-activation-optimized terminology. Each name chosen for dual-audience clarity
(human comprehension + LLM semantic vector activation).

### Approved Renames

| Old Term | New Term | Status |
|---|---|---|
| Eyes (👁️) | **Database Inspector** | DONE |
| Brain (🧠) | **SQL Compiler** | DONE |
| Nervous System (🛡️) | **Query Verification** | DONE |
| Advertising Layer (code + docs) | **Response Guidance** | DONE |
| `_build_advertising_layer()` | **`_build_response_guidance()`** | DONE |
| `test_advertising.py` | **`test_response_guidance.py`** | DONE |
| "Don't let your agents guess. Give them Eyes." | **"The semantic safety layer for agentic database workflows."** | DONE |
| Arrogant Agent (internal) | **Bypass Pattern** | DONE |
| Null Trap | **Keep as-is** | confirmed |
| "naive" (LLM/query) | **"unguarded"** | DONE |
| "arrogant archetype" (ROADMAP.md) | **"bypass pattern"** | DONE |

### Research Basis
- "Tool Preferences in Agentic LLMs are Unreliable" (arxiv 2505.18135) — assertive cues yield 7x tool usage
- "MCP Tool Descriptions Are Smelly" (arxiv 2602.14878) — 97.1% of MCP tools have description quality issues
- Industry comparison: dbt, Cube.dev, Prisma, SQLMesh all use functional naming (no metaphors)

### Why "Advertising" is unacceptable
Will directive (2026-03-24): "Everything needs to be named in a way that doesn't
bounce off of anybody in a negative way." The term "advertising" implies manipulation
of agent behavior. Even though the function genuinely guides agents to safer paths,
the name poisons perception for open-source contributors and users reading the code.

---

## Full Edit List (30 edits + 1 file rename)

### README.md (5 edits)
1. Tagline → "The semantic safety layer for agentic database workflows."
2. 🧠 The Brain → SQL Compiler
3. 👁️ The Eyes → Database Inspector
4. 🛡️ The Nervous System → Query Verification
5. Architecture diagram Nervous System label → Query Verification

### mcp-directory-submissions.md (3 edits)
6-8. Same three Brain/Eyes/Nervous System renames

### demo/magic_moment/DEMO_SCRIPT.md (3 edits)
9. "Eyes" Calibration → Schema Inspection
10. The Nervous System fires → Query Verification fires
11. Boyce's Eyes looked first → The Database Inspector looked first

### demo/magic_moment/verify_demo.py (5 edits)
12-16. All "Boyce's Eyes" references → Database Inspector

### CLAUDE.md (2 edits)
17. Eyes/Brain/Nervous System architecture block → renamed
18. "Response Advertising Layer" → "Response Guidance Layer"

### server.py (3 edits)
19. `_build_advertising_layer()` → `_build_response_guidance()`
20. All comment references to "advertising" → "response guidance"
21. All internal callers updated to new function name

### planner/planner.py (2 edits)
22. "Brain-as-context" comment → "Planner context"
23. "Additional Schema Context from Brain" → "Additional Schema Context"

### tests/test_advertising.py (file rename + internal refs)
24. Rename file → test_response_guidance.py
25. Update internal references

### tests/live_fire/run_mission.py (2 edits)
26. "Brain + Kernel" comment → "Compiler + Kernel"
27. "EXPLAIN pre-flight (Eyes)" → "EXPLAIN pre-flight (Inspector)"

### _strategy/MASTER.md (2 edits)
28. Eyes/Brain/Nervous System references → renamed
29. "Advertising layer" → "Response Guidance"

### _strategy/plans/agent-adoption-docs-sync.md (1 edit)
30. "advertising layer" → "Response Guidance"

### pyproject.toml
31. No change needed

---

## Per-File Review Notes

(Will's decisions recorded as we iterate through each file)
