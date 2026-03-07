# Plan: Block 1 — Ship It
**Status:** Active
**Created:** 2026-02-28
**Timeline:** Active — days 1-10
**Depends on:** Block 0 (naming)

## Goal
Published on PyPI, deployed on a real warehouse, discoverable by agents and developers.
The world can `pip install boyce` and have a working semantic protocol + safety layer
for their database in under 5 minutes.

## Prerequisites
- Name finalized and trademark filing initiated
- Current codebase passing all tests (verified: 15 verify_eyes + 42 pytest)

---

## Implementation Steps

### Step 1: Rename Codebase ✓ DONE
- Rename `boyce/` directory → `boyce/`
- Rename `boyce/` Python package → `boyce/`
- Update all imports across the codebase
- Update `pyproject.toml`: package name, script entry point, metadata
- Update `server.py`: tool names and descriptions
- Update `README.md`, `CLAUDE.md`, `MASTER.md`
- Update `quickstart.sh`
- Verify: `python -m boyce.server` starts, all tests pass
- Cursor model: **Sonnet 4.6** (mechanical find-replace across files, clear spec)

### Step 2: Clean Public API Surface ✓ DONE (this session)
- Ensure key classes/functions are importable directly:
  ```python
  from boyce import process_request, SemanticSnapshot, lint_redshift_compat
  from boyce.parsers import parse_from_path, detect_source_type
  from boyce.graph import SemanticGraph
  ```
- Add `__all__` exports to `__init__.py`
- Write a "Library Usage" section in README (not just MCP server usage)
- Cursor model: **Sonnet 4.6** (straightforward module exports)

### Step 3: Publish to PyPI — IN PROGRESS
- Verify `pyproject.toml` metadata: name, version (0.1.0), description, license (MIT),
  classifiers, Python requires (>=3.10), dependencies, optional deps ([postgres])
- `python -m build` → wheel + sdist
- `twine check dist/*`
- `twine upload dist/*` (or `uv publish`)
- Verify: `pip install boyce` in a clean venv, `boyce` CLI starts
- Executor: Will directly (PyPI credentials required)

### Step 4: Validate on a Live Warehouse
- Connect to a live Redshift/Postgres instance
- Run `ingest_source` with the live schema (live introspection via PostgresAdapter)
- Run `ask_boyce` with real business questions
- Document: what worked, what didn't, where the planner struggled
- Capture: response times, planner accuracy, safety layer catches
- This is the proof point. Nothing else creates as much strategic clarity.
- Executor: Will directly (database credentials required)

### Step 5: Write the Null Trap Essay
- Technical essay: "Here is a real failure mode in AI + database workflows.
  Here is how structured semantics prevent it."
- Structure: problem (30% of users invisible), demo (show the trap), solution (how the
  protocol detects it), call to action (try it yourself)
- **Must include a one-command reproducible demo** — `docker run` or equivalent where
  the reader can see the trap happen and the protocol catch it in under 2 minutes.
  Foundation already exists in `demo/magic_moment/` (seed.sql, snapshot.json, verify_demo.py).
- This is not a blog post — it is the competitive thesis in executable form. Conference-talk quality.
- Publish on personal blog, cross-post to: Hacker News, dbt community, r/dataengineering,
  r/MachineLearning, dev.to
- Include working code examples with `pip install boyce`
- Executor: Will writes content; technical accuracy review by Claude Code

### Step 6: MCP Directory Submissions
- Submit to Smithery (smithery.ai)
- Submit to PulseMCP (pulsemcp.com)
- Submit to mcp.so
- Submit to Glama (glama.ai)
- **Positioning:** Lead with "complementary safety layer for agentic database workflows"
  — not "alternative to dbt." Descriptions should emphasize: null profiling, EXPLAIN pre-flight,
  drift detection, deterministic SQL. Frame as the tool agents add *alongside* existing semantic layers.
- Ensure MCP tool descriptions are optimized for agent discoverability
- Executor: Will directly (account creation required)

### Step 7: Integration Guides
- Claude Desktop: 3-step copy-paste config (`claude_desktop_config.json`)
- Cursor: `.cursor/mcp.json` config
- Claude Code: `.claude/settings.json` or project-level MCP config
- **Cline (VS Code extension):** MCP-compatible — Path 1, no LLM key needed. Config snippet
  only (~5 lines). Already works; just needs a documented guide.
- **Continue.dev (VS Code extension):** MCP-compatible — same as Cline. Already works; just
  needs a documented guide.
- Local LLM: Ollama setup with `BOYCE_PROVIDER=ollama` via LiteLLM
- **dbt + Boyce dual MCP setup:** Show both MCP servers running simultaneously — dbt provides
  semantic context, Boyce provides quality signals and safety. This is the fastest adoption path
  for ICP #3 (dbt users who want a safety layer on top of what they already have).
- Each guide: under 30 seconds to follow, works first try
- Cursor model: **Sonnet 4.6** (docs, straightforward)

---

## Acceptance Criteria
- [ ] `pip install boyce` works from PyPI in a clean environment
- [ ] `boyce` CLI starts the MCP server
- [x] `from boyce import process_request` works as a library (Step 2 done)
- [ ] Real queries executed on a live warehouse with meaningful results
- [ ] Null Trap essay published and submitted to at least 3 channels
- [ ] Listed on at least 2 MCP server directories
- [ ] Claude Desktop and Cursor integration guides tested end-to-end
- [x] All existing tests still pass (260 tests green)

## Risks / Open Questions
- Live warehouse deployment depends on database access and schema complexity — may surface planner weaknesses
- PyPI name availability depends on Block 0 (naming)
- Null Trap essay reception is unpredictable — have follow-up content ideas ready
