# DataShark_Agents — Comprehensive Architectural Summary

**Purpose:** Single reference document for external planning. Assumes zero prior exposure to this codebase.  
**Scope:** This repository only (`DataShark_Agents/`). References to “Core” denote the parent DataShark repo.

---

## 1. Repository Structure

### Full directory tree (2–3 levels)

```
DataShark_Agents/
├── _management_documents/          # Engineering and architecture docs
│   ├── AGENTIC_STACK_DEEP_DIVE.md  # Deep-dive: agents, orchestration, Core sync
│   └── ARCHITECTURAL_SUMMARY.md    # This document
├── .gitignore                     # Ignores data/, .env
├── .keep                          # Placeholder for empty dirs
├── DataShark_Lab_Lab_Contents.md   # Summary of sibling DataShark_Lab scenarios
├── logs/                          # Ad-hoc log output (not part of app flow)
│   ├── parser_stress_output.txt
│   └── stress_test_output.txt
├── run_watcher.py                 # CLI entry: start ingestion watcher (see §2, §9)
├── scenarios/                     # Test/fixture SQL for Architect
│   └── dummy_fix.sql              # Single file used by verify_architect
├── test_connection.py             # One-off: ping Anthropic + UsageTracker
├── tests/
│   └── verify_architect.py         # Architect E2E: plan + execute on dummy_fix.sql
└── src/
    ├── agent/                     # Migration Architect (Planner + Editor)
    │   ├── __init__.py
    │   ├── editor.py              # FileEditor: safe search/replace, create_file
    │   └── planner.py             # MigrationPlanner: goal → JSON plan → execute
    ├── chat/                      # Chat/REPL (placeholder only)
    │   ├── __init__.py
    │   └── repl.py               # Empty
    ├── graph/                     # Graph integration (placeholder only)
    │   └── __init__.py            # Empty
    ├── ingestion/                 # Ingestion pipeline (watcher + RAG)
    │   ├── __init__.py
    │   └── watcher.py             # Empty (Watcher class not defined)
    └── shared/                    # Cross-cutting: store, embedder, telemetry, diagnostics
        ├── __init__.py
        ├── audit_anthropic.py     # Probe Anthropic model IDs (standalone script)
        ├── diagnostics.py        # Check API keys + OpenAI/Anthropic connectivity
        ├── embedder.py           # LocalEmbedder (all-MiniLM-L6-v2, 384-d)
        ├── store.py              # VectorStore (LanceDB, 384-d)
        └── usage.py              # UsageTracker: CSV log, cost calculation
```

### Top-level directory roles

| Directory | Responsibility |
|-----------|----------------|
| **`_management_documents/`** | Architecture and stack documentation; no runtime code. |
| **`logs/`** | Manual or ad-hoc log outputs; not consumed by any agent or pipeline. |
| **`scenarios/`** | Fixture SQL for the Migration Architect (e.g. `dummy_fix.sql`). |
| **`src/`** | All application and shared library code. |
| **`tests/`** | Verification for the Architect agent only (no pytest discovery elsewhere). |

### Second-level (`src/`) module roles

| Module | Responsibility |
|--------|----------------|
| **`agent/`** | **Migration Architect:** high-level goal → LLM-generated JSON edit plan → safe file edits via `FileEditor`. No SQL generation. |
| **`chat/`** | **Placeholder.** Package exists; `repl.py` is empty. No conversational agent. |
| **`graph/`** | **Placeholder.** Empty package. No integration with Core’s SemanticGraph. |
| **`ingestion/`** | **Intended:** filesystem watcher + parse/embed + vector store. `watcher.py` is empty; `Watcher` is not defined (run_watcher will fail at import or instantiation). |
| **`shared/`** | Vector store (LanceDB), local embedder (sentence-transformers), usage/cost logging, and API key/connectivity diagnostics. |

---

## 2. Agent Definitions

This repo defines **one operational agent** (Migration Architect). Other “agents” are stubs or live in Core.

### 2.1 Migration Architect (Planner + Editor)

- **Name / role:** Migration Architect. Turns high-level migration/refactor goals into concrete file edits.
- **Location:** `src/agent/planner.py` (MigrationPlanner), `src/agent/editor.py` (FileEditor).
- **System / user prompt (summarized):**
  - **System:** “You are a Senior Data Architect. You design safe, minimal, and precise code edits. Output ONLY valid JSON in the specified format.”
  - **User:** Instructs the model to take a goal + current file contents and output a **strict JSON list** of actions: `[{ "action": "UPDATE", "file": "path/to/file.sql", "search": "exact string to find", "replace": "new string" }]`. Rules: repo-relative paths only; `search` must be an exact substring; prefer small, local edits; if no changes, return `[]`.
- **Tools / functions it uses:**
  - **FileEditor** (same process): `apply_patch(file_path, search_block, replace_block)` → bool; `create_file(file_path, content)`. No LLM tool-calling; the planner calls the editor from Python after parsing JSON.
- **Input contract:** `generate_plan(goal: str, file_paths: List[str])` — goal string and repo-relative file paths. `execute_plan(plan: List[Dict])` — list of action dicts from `generate_plan`.
- **Output contract:** `generate_plan` returns `List[Dict[str, Any]]` (JSON action list). `execute_plan` returns `List[str]` (human-readable log lines per action).
- **Invocation:** Direct Python: caller builds Anthropic or OpenAI client and `FileEditor`, constructs `MigrationPlanner(client, editor, model_provider="anthropic"|"openai")`, then `planner.generate_plan(goal, file_paths)` and optionally `planner.execute_plan(plan)`. Test entry: `tests/verify_architect.py` (both providers). Optional CLI-style run: `python -m src.agent.planner` (uses Anthropic only; **bug:** uses `os.getenv` without `import os`).

### 2.2 Ingestion “Agent” (Watcher)

- **Intended role:** Watch a directory (e.g. DataShark_Lab), parse/embed content, upsert into vector store.
- **Location:** `src/ingestion/watcher.py` (empty), `run_watcher.py` (entry point).
- **Status:** **Not implemented.** `watcher.py` is empty; there is no `Watcher` class. `run_watcher.py` imports `Watcher` from `src.ingestion.watcher` and calls `watcher.start(TARGET_DIR)` — this will fail at import or at instantiation/start. VectorStore and LocalEmbedder are implemented and used by the intended pipeline design only.

### 2.3 Chat / REPL

- **Intended role:** REPL interface with vector context and Claude (per `src/chat/__init__.py`).
- **Location:** `src/chat/repl.py`.
- **Status:** **Placeholder.** `repl.py` is empty. No agent logic, no tools, no invocation path.

### 2.4 Other “agents” (in Core, not this repo)

- **QueryPlanner** (Core): NL → structured filter; lives in `datashark.runtime.planner.planner`; not in DataShark_Agents.
- **SQL generation:** Done in Core kernel (SQLBuilder, etc.); no separate SQL Generator agent in this repo.

---

## 3. Orchestration & Routing

- **No router or dispatcher** in this repo. No single entry that routes a user prompt to different agents.
- **Migration Architect flow:** Caller (e.g. test or script) → `MigrationPlanner.generate_plan(goal, file_paths)` → one LLM call (Anthropic or OpenAI) → parse JSON → caller (or same process) → `planner.execute_plan(plan)` → for each UPDATE, `FileEditor.apply_patch(...)`. **Pattern:** single-shot, sequential (plan then execute).
- **Multi-agent patterns:** None. No chaining, parallel calls, or hierarchical delegation. One agent (Architect) with one LLM call per “run.”
- **Ingestion:** Intended flow would be `run_watcher.py` → Watcher (not implemented) using VectorStore + LocalEmbedder; no coordination with the Architect or with Core.

---

## 4. Tool Definitions

Tools are **Python APIs** used by the Architect or by shared infrastructure. There is **no LLM function-calling schema** (no tools passed to the model as callable functions).

| Tool / function | Description | Parameters | Internal behavior | Used by |
|-----------------|-------------|------------|-------------------|---------|
| **FileEditor.apply_patch** | Safe search/replace in one file under workspace. | `file_path` (str), `search_block` (str), `replace_block` (str) | Resolves path under `workspace_root`, rejects escape; ensures exactly one match; creates `.bak` backup; replaces and writes. Returns True iff exactly one replacement. | MigrationPlanner (during execute_plan) |
| **FileEditor.create_file** | Create or overwrite a file under workspace. | `file_path` (str), `content` (str) | Safe path resolution; mkdir parents; write content. | Not used in current code (available for future plan actions) |
| **VectorStore.upsert** | Upsert one document by id. | `id`, `text`, `metadata_dict`, `vector` (list[float], len 384) | Serializes metadata to JSON; sets last_updated UTC; merge_insert into LanceDB. | Intended for Watcher pipeline (Watcher not implemented) |
| **VectorStore.search** | k-NN search by vector. | `query_vector` (384-d), `limit` (int, default 5) | Returns list of dicts with `id`, `text`, `metadata`. | Intended for RAG (no caller in repo today) |
| **LocalEmbedder.embed_text** | Encode text to 384-d vector. | `text` (str) | Cleans whitespace; sentence-transformers all-MiniLM-L6-v2; returns list[float]. | Intended for Watcher (no caller in repo today) |
| **UsageTracker.log_request** | Log one model request and cost. | `model`, `input_tokens`, `output_tokens` | Uses PRICING table; appends CSV row to `data/usage_log.csv`; accumulates session cost. Returns cost in dollars. | test_connection.py (optional; not used by planner) |

No SQL executor, no search API, no graph client in this repo.

---

## 5. LLM Integration

- **Providers and models:**
  - **Anthropic:** `claude-3-haiku-20240307` (planner default in code). Diagnostics use `claude-3-5-sonnet-20240620`. test_connection and usage use `claude-sonnet-4-5-20250929`. Audit script probes several model IDs.
  - **OpenAI:** `gpt-4o` (planner when `model_provider="openai"`; diagnostics).
- **How calls are made:** Direct SDK: `anthropic.Anthropic`, `openai.OpenAI`. No LiteLLM or other router in this repo. Planner uses `client.messages.create` (Anthropic) or `client.chat.completions.create` (OpenAI) with a single user message (system prompt concatenated for Anthropic).
- **Retry / fallback:** None in code. No retries, no fallback to another model or provider.
- **Token budgeting:** `max_tokens=2048` in planner; no input token caps or truncation.
- **Prompt management:** Prompts are inline in `MigrationPlanner.generate_plan` (system_prompt + user_prompt). No external prompt files or versioning in this repo.

---

## 6. Agentic Framework

- **No third-party agent framework** (no LangChain, LangGraph, CrewAI, AutoGen, etc.). Implementation is **custom**: Python classes (MigrationPlanner, FileEditor), direct SDK calls, and in-memory execution.
- **Embedding:** Custom only for RAG stack: LocalEmbedder (sentence-transformers) + VectorStore (LanceDB). Not wired into any agent flow yet.

---

## 7. Memory & State Management

- **Conversation history:** Not kept. Migration Architect is single-shot (one goal → one plan → one execute). No multi-turn state.
- **Agent state:** In-memory only. MigrationPlanner holds client, editor, provider, and repo root; no persistence.
- **Intermediate results:** Plan (list of dicts) is returned in process and optionally passed to `execute_plan`; not stored to disk or DB.
- **Vector store:** LanceDB under `data/lancedb` (created by VectorStore). Used for RAG-ready storage only; no current pipeline fills or queries it from an agent.
- **Usage:** `UsageTracker` appends to `data/usage_log.csv` (session cost in memory; “total project” read from file when printing summary). No other caches or persistent memory.

---

## 8. Integration Points with Main DataShark Repo

- **No code imports** from DataShark Core into DataShark_Agents. No shared Python packages, no API client to Core server, no use of Core’s SemanticGraph, QueryPlanner, or SQL kernel.
- **Filesystem-only “integration”:**
  - **DataShark_Lab path:** `run_watcher.py` resolves a target directory from candidates: `../DataShark_Lab` or `../DataShark/DataShark_Lab`. Used only as the intended watch root for the (unimplemented) Watcher. No shared modules or data contracts.
- **Documentation:** `_management_documents/AGENTIC_STACK_DEEP_DIVE.md` and `DataShark_Lab_Lab_Contents.md` describe Core’s flow and Lab layout for human readers; they are not runtime interfaces.
- **Runtime:** The two repos do **not** run together in one process. Core uses its own `QueryPlanner` and agent_engine (e.g. Brain); this repo’s MigrationPlanner is standalone. Unifying (e.g. Agents calling Core API or a shared lib) is a documented gap.

---

## 9. Configuration & Environment

- **Config files:** No `config.json`, `config.yaml`, or app-level config file in this repo. Paths (e.g. LanceDB, usage log) are hardcoded or derived from `__file__` (repo root).
- **Environment variables:**
  - **ANTHROPIC_API_KEY** — used by planner (Anthropic), test_connection, verify_architect, diagnostics, audit_anthropic.
  - **OPENAI_API_KEY** — used by planner (OpenAI), verify_architect, diagnostics.
  - Loaded via `python-dotenv` in several scripts (`load_dotenv()`); no central bootstrap.
- **Secrets:** Keys only in environment (or `.env`); `.env` is gitignored. No vault or secrets manager.
- **Feature flags:** None.

---

## 10. Testing & CI/CD

- **Test framework:** No pytest (or other) configuration in this repo. Single script: `tests/verify_architect.py`, run as `python tests/verify_architect.py`. It resets `scenarios/dummy_fix.sql`, runs MigrationPlanner for both Anthropic and OpenAI (goal: rename alias `u` to `users`), executes the plan, and asserts file content. No pytest discovery, no coverage.
- **CI/CD:** No `.github` (or other CI) in DataShark_Agents. Parent DataShark has `.github/workflows` (e.g. ci.yml, build_plugin.yml); those are not specific to DataShark_Agents.

---

## 11. Dependencies

This repo has **no dedicated `requirements.txt` or `pyproject.toml`**. It lives under DataShark and relies on the parent for some ecosystem; several dependencies are specific to Agents and are **not** all listed in the parent’s `requirements.txt` or `pyproject.toml`.

| Library | Typical use / version (if evident) | Role |
|---------|-----------------------------------|------|
| **anthropic** | — | Anthropic API (MigrationPlanner, tests, diagnostics, audit) |
| **openai** | — | OpenAI API (MigrationPlanner, diagnostics) |
| **python-dotenv** | ≥1.0.0 (parent) | Load .env for API keys |
| **lancedb** | — | Vector store backend |
| **pyarrow** | — | Schema and tables for LanceDB |
| **sentence-transformers** | — | LocalEmbedder (all-MiniLM-L6-v2) |

Parent DataShark also uses: `typer`, `rich`, `litellm`, `networkx`, `chromadb`, `watchdog`, etc.; those are not necessarily used by Agents code. A virtualenv or install that runs Core may still be missing `lancedb`, `pyarrow`, `sentence-transformers` for full Agents functionality (e.g. VectorStore and LocalEmbedder).

---

## 12. Known Gaps & TODOs

- **Ingestion / Watcher:** `src/ingestion/watcher.py` is empty. `Watcher` is not defined; `run_watcher.py` will fail. No filesystem watcher, no parse/embed/upsert pipeline, no integration with Core graph.
- **Chat / REPL:** `src/chat/repl.py` is empty; no conversational agent.
- **Graph:** `src/graph/` is an empty package; no integration with Core’s SemanticGraph.
- **Planner `main()`:** Uses `os.getenv("ANTHROPIC_API_KEY")` without `import os` — runtime error if `__main__` is run.
- **No explicit TODO/FIXME/HACK** comments found in the repo; gaps are structural (empty modules, missing class).

---

## 13. Tech Debt & Observations

- **Dependencies:** Agents-specific deps (lancedb, pyarrow, sentence_transformers, anthropic, openai) are not declared in a single place in this repo; documenting or adding a local `requirements.txt` / `pyproject.toml` would clarify install and CI.
- **Bug:** `planner.py` `main()` uses `os.getenv` but does not import `os`.
- **Orchestration:** Single agent, no framework, no router. If more agents or flows are added, a small orchestration layer and clearer entry points would help.
- **Testing:** One manual verification script; no pytest, no coverage, no CI in this repo. Adding pytest and a minimal CI would reduce regression risk.
- **Config:** Paths and model IDs are hardcoded; centralizing in a small config (or env) would ease deployment and tuning.
- **State:** No conversation or session state; acceptable for current single-shot Architect; any future chat or multi-step flow would need a state/memory design.
- **Core/Agents boundary:** Clear in code (no imports), but the intended product relationship (e.g. “Agents as plugin to Core” vs “standalone tools”) could be documented and reflected in integration points (e.g. optional Core API client or shared lib).

---

*End of architectural summary. For Core-side flow (QueryPlanner, graph, MCP, server), see `AGENTIC_STACK_DEEP_DIVE.md` and the main DataShark repository.*
