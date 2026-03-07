# DataShark_Agents — Comprehensive Architectural Summary for External Planning

**Purpose:** Single reference for executive-level architectural planning. Assumes zero prior exposure.  
**Scope:** This repository only (`DataShark_Agents/`). "Core" = parent DataShark repo.

---

## 1. Repository Structure

### Full directory tree (2–3 levels)

```
DataShark_Agents/
├── _management_documents/           # Engineering and architecture docs (no runtime code)
│   ├── AGENTIC_STACK_DEEP_DIVE.md   # Deep-dive: agents, orchestration, Core sync
│   └── ARCHITECTURAL_SUMMARY.md     # Existing repo summary (this doc extends it)
├── .gitignore                       # Ignores data/, .env
├── .keep                            # Placeholder for empty dirs
├── DataShark_Lab_Lab_Contents.md    # Summary of sibling DataShark_Lab scenarios
├── DATASHARK_AGENTS_CONTEXT_PACKET.md  # Evidence-based context packet (quickstart, gaps)
├── logs/                            # Ad-hoc log output (not part of app flow)
│   ├── parser_stress_output.txt
│   └── stress_test_output.txt
├── run_watcher.py                   # CLI entry: start ingestion watcher (fails: Watcher undefined)
├── scenarios/                       # Test/fixture SQL for Migration Architect
│   ├── dummy_fix.sql                # Fixture for verify_architect
│   └── dummy_fix.sql.bak            # Backup from FileEditor
├── test_connection.py               # One-off: ping Anthropic + UsageTracker
├── tests/
│   └── verify_architect.py          # Architect E2E: plan + execute on dummy_fix.sql
└── src/
    ├── agent/                       # Migration Architect (Planner + Editor)
    │   ├── __init__.py              # Package marker
    │   ├── editor.py                # FileEditor: safe search/replace, create_file
    │   └── planner.py               # MigrationPlanner: goal → JSON plan → execute
    ├── chat/                        # Chat/REPL (placeholder only)
    │   ├── __init__.py
    │   └── repl.py                  # Empty
    ├── graph/                       # Graph integration (placeholder only)
    │   └── __init__.py              # Empty
    ├── ingestion/                   # Intended: watcher + parse/embed + vector store
    │   ├── __init__.py
    │   └── watcher.py               # Empty (Watcher class not defined)
    └── shared/                      # Cross-cutting: store, embedder, telemetry, diagnostics
        ├── __init__.py
        ├── audit_anthropic.py       # Probe Anthropic model IDs (standalone)
        ├── diagnostics.py          # Check API keys + OpenAI/Anthropic connectivity
        ├── embedder.py              # LocalEmbedder (all-MiniLM-L6-v2, 384-d)
        ├── store.py                 # VectorStore (LanceDB, 384-d)
        └── usage.py                # UsageTracker: CSV log, cost calculation
```

### Top-level directory roles

- **`_management_documents/`** — Architecture and stack documentation; no runtime code.
- **`logs/`** — Manual or ad-hoc log outputs; not consumed by any agent or pipeline.
- **`scenarios/`** — Fixture SQL for the Migration Architect (e.g. `dummy_fix.sql`).
- **`src/`** — All application and shared library code.
- **`tests/`** — Verification for the Architect agent only (no pytest discovery).

### Key subdirectories under `src/`

- **`agent/`** — Migration Architect: goal → LLM JSON edit plan → safe file edits via FileEditor. No SQL generation.
- **`chat/`** — Placeholder; `repl.py` is empty. No conversational agent.
- **`graph/`** — Placeholder; empty package. No integration with Core SemanticGraph.
- **`ingestion/`** — Intended: filesystem watcher + parse/embed + vector store. `watcher.py` is empty; Watcher not defined.
- **`shared/`** — Vector store (LanceDB), local embedder (sentence-transformers), usage/cost logging, API key/connectivity diagnostics.

---

## 2. Tech Stack and Dependencies

### Languages and runtime

- **Python 3.x** (3.9+ in practice; parent DataShark requires >=3.10). No Node/TS in this repo.

### Frameworks and agent frameworks

- **No third-party agent framework** (no LangChain, LangGraph, CrewAI, AutoGen). Implementation is **custom**: Python classes (MigrationPlanner, FileEditor), direct SDK calls, in-memory execution.
- **No router/orchestrator** — single agent, direct invocation.

### LLM SDKs and providers

- **anthropic** — Anthropic API (MigrationPlanner, tests, diagnostics, audit_anthropic). No version pinned in repo.
- **openai** — OpenAI API (MigrationPlanner, diagnostics). No version pinned in repo.
- Direct SDK usage only; no LiteLLM or other router in DataShark_Agents.

### Other third-party libraries (from code imports)

- **python-dotenv** — Load .env for API keys (diagnostics, audit_anthropic, test_connection).
- **lancedb** — Vector store backend (src/shared/store.py).
- **pyarrow** — Schema and tables for LanceDB (src/shared/store.py).
- **sentence-transformers** — LocalEmbedder; model `sentence-transformers/all-MiniLM-L6-v2` (src/shared/embedder.py).

### Dependency manifest

- **No `requirements.txt` or `pyproject.toml` in DataShark_Agents.** Dependencies are implied by imports. Parent DataShark has pyproject.toml and requirements.txt but does **not** list Agents-specific deps: `anthropic`, `lancedb`, `pyarrow`, `sentence_transformers`. A venv that runs Core may lack these for full Agents functionality.

### Versions (where specified)

- In-repo: **none** (no lockfile or version pins).
- Parent pyproject.toml: `openai>=1.0.0`, `python-dotenv>=1.0.0`, `litellm>=1.0.0`, `chromadb>=0.4.0`, `networkx>=3.0`, `watchdog>=3.0.0`, etc. Parent uses **chromadb** and **litellm**; Agents uses **lancedb** and direct **anthropic/openai** — no shared version story for Agents deps.

---

## 3. Agent Architecture Overview

### Number and responsibility of agents

- **One operational agent:** **Migration Architect** (implemented as MigrationPlanner + FileEditor). Responsibility: turn high-level migration/refactor goals into concrete file edits (JSON plan → search/replace patches). **Not** involved in SQL generation or graph.
- **Stubs/placeholders:** Ingestion "agent" (Watcher — not implemented); Chat/REPL (empty). No other agents in this repo.

### Orchestration pattern

- **Single-agent, single-shot.** No multi-agent, hierarchical, or graph-based orchestration.
- **Flow:** Caller → `MigrationPlanner.generate_plan(goal, file_paths)` → one LLM call (Anthropic or OpenAI) → parse JSON → caller (or same process) → `planner.execute_plan(plan)` → for each UPDATE, `FileEditor.apply_patch(...)`.
- **No router or dispatcher** that routes user intent to different agents.

### How agents "communicate"

- No inter-agent messaging. The Architect uses **in-process Python APIs**: planner calls FileEditor after parsing LLM output. No shared state server, message bus, or tool-calling schema passed to the LLM (model returns JSON; code interprets it and calls editor).

### Agent lifecycle

- **Initialization:** Caller instantiates Anthropic or OpenAI client and FileEditor (bound to workspace root), then `MigrationPlanner(client, editor, model_provider="anthropic"|"openai")`.
- **Execution:** Single run: `generate_plan(goal, file_paths)` then optionally `execute_plan(plan)`. No conversation loop.
- **Memory:** None. No conversation history or session state.
- **Termination:** Process ends; no persistent agent state.

---

## 4. Agent Definitions (Per Agent)

### 4.1 Migration Architect (Planner + Editor)

- **Name / purpose:** Migration Architect. Turns high-level migration/refactor goals into concrete, safe file edits.
- **Location:** src/agent/planner.py (MigrationPlanner), src/agent/editor.py (FileEditor).
- **System prompt (summary):** "You are a Senior Data Architect. You design safe, minimal, and precise code edits. Output ONLY valid JSON in the specified format."
- **User prompt (summary):** Instructs the model to take a goal + current file contents and output a **strict JSON list** of actions: `[{ "action": "UPDATE", "file": "path/to/file.sql", "search": "exact string to find", "replace": "new string" }]`. Rules: repo-relative paths only; `search` must be an exact substring; prefer small, local edits; if no changes, return `[]`. Prompts are **inline** in `generate_plan` (no external template files).
- **Tools/functions:** FileEditor (same process): `apply_patch(file_path, search_block, replace_block)` → bool; `create_file(file_path, content)`. No LLM function-calling; planner parses JSON and calls editor from Python.
- **Input contract:** `generate_plan(goal: str, file_paths: List[str])` — goal string and repo-relative file paths. `execute_plan(plan: List[Dict])` — list of action dicts from `generate_plan`.
- **Output contract:** `generate_plan` returns `List[Dict[str, Any]]` (JSON action list). `execute_plan` returns `List[str]` (human-readable log lines per action).
- **Guardrails / error handling:** Planner: JSON parse failure → returns `[]`; strips Markdown code fences; accepts top-level list or `{"plan": list}`. Editor: path must be under `workspace_root`; exact single match for search_block (else returns False); backup (.bak) before write. No retries on API or editor failures; failed patches are logged and execution continues.
- **Known bug (fixed):** `planner.main()` previously used `os.getenv("ANTHROPIC_API_KEY")` without `import os`; `import os` has been added.

### 4.2 Ingestion "Agent" (Watcher)

- **Intended purpose:** Watch a directory (e.g. DataShark_Lab), parse/embed content, upsert into vector store.
- **Location:** src/ingestion/watcher.py (empty), run_watcher.py (entry point).
- **Status:** **Not implemented.** `watcher.py` is empty; no `Watcher` class. `run_watcher.py` imports `Watcher` and calls `watcher.start(TARGET_DIR)` — fails at import or instantiation. VectorStore and LocalEmbedder exist for the intended pipeline but are not wired to any agent.

### 4.3 Chat / REPL

- **Intended purpose:** REPL interface with vector context and Claude (per src/chat/__init__.py).
- **Location:** src/chat/repl.py.
- **Status:** **Placeholder.** `repl.py` is empty. No agent logic, tools, or invocation path.

---

## 5. Tool Definitions

Tools are **Python APIs** used by the Architect or shared infrastructure. **No LLM function-calling schema** (no tools passed to the model as callable functions).

| Tool / function              | Description                                      | Parameters                                                     | Return                                  | External/graph/DB?                  | Used by                                               |
| ---------------------------- | ------------------------------------------------ | -------------------------------------------------------------- | --------------------------------------- | ----------------------------------- | ----------------------------------------------------- |
| **FileEditor.apply_patch**   | Safe search/replace in one file under workspace. | `file_path` (str), `search_block` (str), `replace_block` (str) | bool (True iff exactly one replacement) | Purely local filesystem             | MigrationPlanner during execute_plan                  |
| **FileEditor.create_file**   | Create or overwrite file under workspace.        | `file_path` (str), `content` (str)                             | None                                    | Purely local filesystem             | Not used in current code (available for plan actions) |
| **VectorStore.upsert**       | Upsert one document by id.                       | `id`, `text`, `metadata_dict`, `vector` (list[float], len 384)  | None                                    | Local LanceDB                       | Intended for Watcher (Watcher not implemented)        |
| **VectorStore.search**       | k-NN search by vector.                           | `query_vector` (384-d), `limit` (int, default 5)               | list[dict] with id, text, metadata      | Local LanceDB                       | No caller in repo today                               |
| **LocalEmbedder.embed_text**  | Encode text to 384-d vector.                     | `text` (str)                                                    | list[float]                             | Local model (sentence-transformers) | Intended for Watcher; no caller today                 |
| **UsageTracker.log_request**  | Log one model request and cost.                  | `model`, `input_tokens`, `output_tokens`                        | float (cost in dollars)                 | Writes CSV to `data/usage_log.csv`  | test_connection.py; not used by planner               |

- **No** SQL executor, search API, or graph client in this repo.

---

## 6. LLM Integration

### Providers and models

- **Anthropic:** Planner default `claude-3-haiku-20240307` (src/agent/planner.py constant `MODEL`). Diagnostics use `claude-3-5-sonnet-20240620`. test_connection and usage use `claude-sonnet-4-5-20250929`. Audit script probes several model IDs.
- **OpenAI:** Planner uses `gpt-4o` when `model_provider="openai"`; diagnostics use `gpt-4o`.

### How prompts are constructed

- **Inline** in `MigrationPlanner.generate_plan`: system_prompt + user_prompt strings. No external template files, no versioning, no few-shot examples in code. User prompt includes goal + concatenated file contents (`--- FILE: path ---` blocks).

### Token management and context

- **max_tokens=2048** in planner for both providers. No input token caps, truncation, or context-window strategy in code.
- **Cost controls:** UsageTracker can log cost per request to CSV; not wired into the planner. PRICING in src/shared/usage.py has entry for `claude-sonnet-4-5-20250929` only.

### Fine-tuning, caching, embeddings

- **No** fine-tuning or response caching in repo. Embeddings: LocalEmbedder (sentence-transformers all-MiniLM-L6-v2) for RAG pipeline only; not used by any agent flow yet.

---

## 7. Integration with Main DataShark Repo

### API contracts, shared schemas, direct imports

- **No code imports** from DataShark Core into DataShark_Agents. No shared Python packages, no API client to Core server, no use of Core's SemanticGraph, QueryPlanner, or SQL kernel.

### How agents would access graph/middle layer

- **They do not.** `src/graph/` is empty. Graph is in-process Core only; no HTTP API or shared storage. Agents repo does not query or update the middle-layer graph.

### How agents would access ingested metadata and business context

- **Not implemented.** Intended ingestion (Watcher + VectorStore) is not built. Core has its own ingestion and graph; no shared context API or data contract with Agents.

### Deployment coupling

- **Filesystem-only "integration":** `run_watcher.py` resolves a target directory from candidates: `../DataShark_Lab` or `../DataShark/DataShark_Lab` for the (unimplemented) Watcher. No shared modules or runtime coupling. The two repos do **not** run together in one process; Core uses its own QueryPlanner and agent_engine; this repo's MigrationPlanner is standalone. Unifying (e.g. Agents calling Core API or shared lib) is a documented gap.

---

## 8. Memory and State Management

### Short-term (within a conversation/session)

- **None.** Migration Architect is single-shot (one goal → one plan → one execute). No multi-turn state or conversation history.

### Long-term (across sessions, preferences, learned patterns)

- **None.** No user preferences or learned patterns. UsageTracker appends to `data/usage_log.csv` (cost log); "total project" is read from file when printing summary. No other persistent agent memory.

### Vector store and RAG

- **VectorStore** (LanceDB at `data/lancedb`, 384-d) and **LocalEmbedder** exist for RAG-ready storage. No pipeline in this repo fills or queries them from an agent. No RAG pattern currently wired into any agent.

---

## 9. Evaluation and Observability

### Eval frameworks, benchmarks, test harnesses

- **No** formal eval framework, benchmarks, or golden test suite. Single E2E script: tests/verify_architect.py — resets `scenarios/dummy_fix.sql`, runs MigrationPlanner for both Anthropic and OpenAI (goal: rename alias `u` to `users`), executes plan, asserts file content contains `SELECT * FROM users`. No pytest discovery; no regression or determinism strategy.

### Logging, tracing, observability

- **No** LangSmith, Braintrust, Phoenix, or custom tracing. Logging: `execute_plan` returns a list of human-readable log strings; no structured logs or metrics for tool calls. Usage/cost: UsageTracker (CSV) where explicitly used (e.g. test_connection.py), not in the planner.

### Validation of agent outputs (e.g. generated SQL)

- **No SQL generation in this repo.** Architect produces file-edit plans (JSON), not SQL. Validation: planner parses JSON and normalizes; editor validates path and exact match. No SQL validation in DataShark_Agents.

---

## 10. Current State and Known Gaps

### Fully implemented

- **Migration Architect:** MigrationPlanner + FileEditor — plan generation (Anthropic + OpenAI), JSON parsing, execute_plan, apply_patch, create_file, workspace scoping, backup. Single E2E test (verify_architect) for both providers.
- **Shared infra:** VectorStore (LanceDB), LocalEmbedder (all-MiniLM-L6-v2), UsageTracker (CSV), diagnostics (API keys + connectivity), audit_anthropic (model probe).

### Partially implemented

- **Ingestion:** VectorStore and LocalEmbedder ready; run_watcher entry exists but Watcher class is missing — run_watcher fails.
- **Usage tracking:** Implemented but not integrated into planner; only test_connection and manual use.

### Stubbed / planned

- **Chat/REPL:** Package and docstring exist; repl.py empty.
- **Graph integration:** Empty package; no Core graph access.
- **RAG in agent flow:** Vector store and embedder not used by any agent.

### Known bugs

- **planner.main():** Fixed — `import os` added so `os.getenv("ANTHROPIC_API_KEY")` works when run as `python -m src.agent.planner`.

### Architectural debt and TODOs (from docs and structure)

- No explicit TODO/FIXME/HACK in code. Gaps: no dependency manifest (requirements.txt/pyproject.toml) in this repo; no retries or fallback for LLM/editor; no conversation or session state; no eval harness beyond single verify_architect; no integration path with Core (graph, MCP, or API). Config: paths and model IDs largely hardcoded; centralizing in config or env would ease deployment.

---

*End of architectural summary. For Core-side flow (QueryPlanner, graph, MCP, server), see `_management_documents/AGENTIC_STACK_DEEP_DIVE.md` and the main DataShark repository.*
