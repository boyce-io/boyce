# DataShark Agentic Stack — Deep-Dive Summary for Core Architecture

**Audience:** Core Architecture team  
**Scope:** Agent definitions, orchestration, graph integration, prompts, tooling.  
**Focus:** Logic flow from user prompt to SQL generation.

---

## 1. Agent Taxonomy

| Persona / Component | Location | Role |
|--------------------|----------|------|
| **Migration Architect (Planner + Editor)** | `DataShark_Agents/src/agent/` | Turns high-level migration/refactor goals into concrete file edits (JSON plan → search/replace patches). Not involved in SQL generation. |
| **QueryPlanner** | Core `datashark.runtime.planner.planner` | Converts natural language → structured filter (entities, fields, metrics, dimensions, filters, temporal). Single LLM call; output validated against graph. |
| **Ingestion (intended)** | `DataShark_Agents/src/ingestion/` | Watcher is an **empty stub**; `VectorStore` (LanceDB) + `LocalEmbedder` (all-MiniLM-L6-v2) exist for RAG. `run_watcher.py` targets DataShark_Lab; no integration with Core graph. |
| **Chat / REPL** | `DataShark_Agents/src/chat/` | **Placeholder only** (empty `repl.py`). No conversational agent in Agents repo. |
| **SQL “generator”** | Core kernel only | There is no separate “SQL Generator” agent. SQL is produced deterministically by `process_request` → `SQLBuilder` (zero LLM). |

**There are no distinct “SQL Generator,” “Optimizer,” or “Business Analyst” agents in code.** NL→SQL is: **QueryPlanner (NL→structured filter)** then **Kernel (structured filter + snapshot → SQL)**.

---

## 2. Orchestration Logic

### 2.1 How the user query is handled

- **Core server (JSON-RPC, `datashark serve`)**  
  - **No router/dispatcher.** Methods: `ingest_context`, `generate_sql`, `verify_sql`, etc.  
  - **generate_sql:**  
    1. `user_prompt` required.  
    2. Lazy-init `QueryPlanner` (LiteLLM; optional Brain for RAG).  
    3. `structured_filter = self.planner.plan_query(user_prompt, self.graph)`.  
    4. Snapshot taken as first in `self.graph.snapshots`.  
    5. `sql = process_request(snapshot, structured_filter)`.  
    6. Optional Redshift safety transform.  
  - **State:** `self.graph` (SemanticGraph) and `self.planner` in RAM only. No session/conversation ID; no persistence of graph or chat across restarts.

- **MCP (`mcp_app.ask_datashark`)**  
  - Loads snapshot from `_local_context/<snapshot_name>.json`.  
  - **Does not use QueryPlanner.** Uses `_mock_chat_interface(natural_language_query)` → returns **empty** structured filter (empty entities, metrics, dimensions).  
  - Then `process_request(snapshot, structured_filter)` → SQL. So MCP NL→SQL path is currently **stub**: no real NL understanding, only kernel with empty filter.

- **DataShark_Agents**  
  - **No central router.** Migration flow: caller (e.g. test) → `MigrationPlanner.generate_plan(goal, file_paths)` → LLM → JSON plan → `planner.execute_plan(plan)` → `FileEditor.apply_patch` per action.  
  - Ingestion entry: `run_watcher.py` → `Watcher(store, embedder)`; Watcher class is empty, so this path is non-functional until implemented.

### 2.2 State between turns

- **Core:** No conversation or turn state. Each `generate_sql` is stateless given current in-memory graph and snapshot.  
- **MCP:** `_global_graph` is module-level; snapshots persisted to `_local_context/`. No conversation history or session store.  
- **Agents:** No multi-turn state; MigrationPlanner is single-shot (goal → plan → execute).

---

## 3. Graph Integration (Middle Layer)

- **“Middle Layer” graph** = Core’s **SemanticGraph** in `datashark.core.graph`: NetworkX `MultiDiGraph`; nodes = entities, edges = joins with semantic weights; `add_snapshot`, `list_entities`, `find_path`, `field_cache`, etc.

- **How agents/components use it:**  
  - **Core server:** In-process only. `DataSharkServer` holds `self.graph = SemanticGraph()`. `ingest_context` parses files and calls `self.graph.add_snapshot(snapshot)`. `generate_sql` calls `self.planner.plan_query(user_prompt, self.graph)`.  
  - **MCP:** Same process. `_global_graph = SemanticGraph()`. `ingest_source` tool parses and calls `_global_graph.add_snapshot(snapshot)`. `solve_path` uses `_global_graph.find_path` and `generate_join_sql`. `ask_datashark` does **not** pass the graph to any planner (uses mock filter).  
  - **DataShark_Agents:** **No integration.** `DataShark_Agents/src/graph/` is an empty package. No imports from Core. No API calls, no shared DB, no direct use of SemanticGraph. The Agents vector store (LanceDB) is separate from the semantic graph.

- **Summary:** Graph is **in-process Core only**. No HTTP API or shared storage for the graph; Agents repo does not currently query or update the Middle Layer graph.

---

## 4. Prompt Engineering

| Component | Strategy | Notes |
|-----------|----------|------|
| **QueryPlanner (Core)** | Single system + user message. **Role:** “You are a Data Engineer.” Schema context = entities/fields from graph (top ~50 entities by keyword match, up to 20 fields per entity). **Output:** strict JSON (entities, fields, metrics, dimensions, filters, temporal). Optional Brain RAG appended as “Additional Schema Context.” **No** few-shot examples in code; **no** explicit Chain-of-Thought or ReAct. Single completion → regex extract JSON → validate against graph. |
| **MigrationPlanner (Agents)** | Single system + user message. **Role:** “Senior Data Architect”; “Output ONLY valid JSON.” **Output:** list of `{action, file, search, replace}`. **No** few-shot, CoT, or ReAct. |
| **Distribution prompts** | `distribution/ai_sql_helper_prompts/01_build_map.md`, `02_activate_architect.md` | Human-facing: Repo Indexer and Principal Data Architect. Not invoked by code; used as Cursor/LLM session instructions. |

**Pattern in code:** Single-turn, role + schema + task, strict JSON out, then programmatic validation. No tool-use loops or ReAct in the planner.

---

## 5. Tooling

### 5.1 DataShark_Agents

- **FileEditor** (`src/agent/editor.py`): `apply_patch(file_path, search_block, replace_block)` (safe, workspace-scoped, backup); `create_file(file_path, content)`.  
- **VectorStore** (`src/shared/store.py`): LanceDB, 384-d (all-MiniLM-L6-v2); `upsert`, `search(query_vector, limit)`.  
- **LocalEmbedder** (`src/shared/embedder.py`): `embed_text(text)` → 384-d vector.  
- **Watcher:** Stub (empty module); no filesystem watcher, no SQL parse/embed pipeline.  
- **No** SQL executor, no search tool, no graph API client in Agents repo.

### 5.2 Core / MCP

- **MCP tools:**  
  - `ingest_source(source_path | source_text, source_type, snapshot_name)` → parsers → validate → `_global_graph.add_snapshot` + save to `_local_context/`.  
  - `solve_path(source, target, snapshot_name)` → `_global_graph.find_path`, `generate_join_sql`.  
  - `ask_datashark(natural_language_query, snapshot_name)` → `_mock_chat_interface` + `process_request` (+ optional Redshift lint).  
- **Server:** Same logical operations via JSON-RPC (ingest_context, generate_sql, verify_sql). Optional: DataSharkBrain (`retrieve_context`), Redshift lint/transform.  
- **QueryPlanner** has no exposed “tools” (no function-calling); it’s a single LiteLLM completion with graph-derived context.

---

## 6. End-to-End Logic Flow: User Prompt → SQL

```
[User natural language query]
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Core server (generate_sql)                                        │
│   1. planner.plan_query(user_prompt, self.graph)                 │
│      - Graph: list_entities → entity_context (top 50 by keywords) │
│      - Optional: brain.retrieve_context(query) → RAG blob in prompt│
│      - LiteLLM completion → raw JSON                               │
│      - Validate entities/fields/metrics/dimensions/filters        │
│        against graph → structured_filter                           │
│   2. snapshot = first graph.snapshots value                      │
│   3. process_request(snapshot, structured_filter)                 │
│      - validate_snapshot; SQLBuilder.build_final_sql(...)         │
│      - JOINs from snapshot; planner join_path only as hint        │
│   4. Optional Redshift transform                                  │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
[SQL string]
```

**MCP path today:** Same kernel (`process_request`), but `structured_filter` is **mock empty** → SQL reflects only snapshot schema with no user intent (no real NL→SQL on MCP).

---

## 7. Gaps / Clarifications for Core Sync

1. **Agents ↔ Core:** No code path from DataShark_Agents to Core’s graph or SQL pipeline. Unify (e.g. Agents call Core API or shared lib) or document as intentional separation.  
2. **MCP NL→SQL:** Wire `ask_datashark` to QueryPlanner (and graph) so MCP uses the same NL→structured_filter flow as the server.  
3. **State:** Conversation/session state is not persisted; graph is in-memory except snapshot files in `_local_context/`.  
4. **Ingestion in Agents:** Watcher is empty; run_watcher will fail. Decide whether RAG pipeline in Agents should feed Core (e.g. via Brain or a shared context API) or stay separate.

---

*Generated from scan of DataShark_Agents and DataShark Core (src/datashark, mcp_app, server, planner, graph, api).*
