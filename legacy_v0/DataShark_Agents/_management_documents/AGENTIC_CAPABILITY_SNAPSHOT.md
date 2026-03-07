# Agentic Capability Snapshot — DataShark Agent Framework

**Scope:** DataShark_Agents repository. **Audience:** Executive review. **Focus:** Flow of control and prompt strategy.

---

## 1. Agent Roster

The framework currently defines **one operational agent** and one non-LLM support component:


| Agent / Component                 | Primary responsibility                                                                                                                                                                                            | Location                                                          |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **Migration Architect (Planner)** | Turns high-level migration/refactor goals into a **strict JSON list of file-edit actions** (UPDATE with file/search/replace). Single LLM call (Anthropic Claude or OpenAI GPT-4o); no multi-turn or tool-calling. | [src/agent/planner.py](src/agent/planner.py) — `MigrationPlanner` |
| **FileEditor**                    | Executes edits safely: applies search/replace patches and creates files under a workspace root; enforces path containment and backup-before-write. Not an LLM; invoked by the planner after parsing JSON.         | [src/agent/editor.py](src/agent/editor.py) — `FileEditor`         |


**Not present in this repo:** There are **no** distinct SQL Generator, Validator, or Orchestrator agents. SQL generation (NL → structured filter → SQL) lives in the parent **DataShark Core** (QueryPlanner + kernel), not in DataShark_Agents. Chat/REPL ([src/chat/repl.py](src/chat/repl.py)) and Ingestion Watcher ([src/ingestion/](src/ingestion/)) are **placeholders** (empty or stubs).

---

## 2. Orchestration Logic

**Pattern:** In-process, single-shot, sequential. No LangGraph, no message bus, no shared state machine.

- **Message passing:** There is no inter-agent messaging. The caller (e.g. test or script) calls the planner; the planner calls the LLM once, parses JSON, then calls the editor from Python for each action. No tool schema is passed to the LLM — the model returns JSON; code interprets it and invokes the editor.

**Core orchestration loop (conceptual):**

```
Caller → MigrationPlanner.generate_plan(goal, file_paths)
       → read file contents from disk
       → one LLM request (system + user prompt with goal + file contents)
       → _parse_json_response(raw_text) → list of action dicts
       → return plan to caller

Caller → MigrationPlanner.execute_plan(plan)
       → for each action: editor.apply_patch(file, search, replace) or create_file
       → return list of log strings
```

**Reference implementation:** [tests/verify_architect.py](tests/verify_architect.py) — builds Anthropic or OpenAI client, `MigrationPlanner(client, editor, model_provider)`, then `planner.generate_plan(goal, [rel_path])` and `planner.execute_plan(plan)`.

**Relevant code (orchestration):**

- Plan generation + LLM call: [src/agent/planner.py](src/agent/planner.py) lines 51–140 (`generate_plan`, provider branch for Anthropic vs OpenAI).
- Execution: [src/agent/planner.py](src/agent/planner.py) lines 181–206 (`execute_plan` loops over plan and calls `editor.apply_patch`).

---

## 3. Prompt Engineering

There is **no** "SQL Generation" agent in DataShark_Agents. The only LLM agent is the **Migration Architect** (MigrationPlanner). Below are its **system** and **user** prompts (from [src/agent/planner.py](src/agent/planner.py)).

**System prompt (lines 82–86):**

```text
You are a Senior Data Architect. You design safe, minimal, and precise code edits. Output ONLY valid JSON in the specified format.
```

**User prompt (lines 87–105) — structure:**

- Instructions: given a goal and file contents, propose a concrete edit plan as **strict JSON only**; no explanation or extra keys.
- Schema: list of actions with exact keys: `action`, `file`, `search`, `replace` (example: `[{"action": "UPDATE", "file": "path/to/file.sql", "search": "exact string to find", "replace": "new string"}]`).
- Rules: repo-relative paths; `search` must be an exact substring from the file; prefer smaller edits; if no changes, return `[]`.
- Then: `GOAL:\n{goal}\n\nFILES:\n{files_section}\n\nNow output ONLY the JSON list of actions. No prose.`

**Strategy:** Single-turn, role + task + schema, strict JSON output, then programmatic parse (strip markdown fences, accept top-level list or `{"plan": list}`). No few-shot, no Chain-of-Thought, no ReAct, no tool-use loop.

---

## 4. Tool Definitions

Tools are **Python APIs** used by the planner/editor. **No LLM function-calling** — the model does not receive tool definitions; it returns JSON and the planner calls the editor.


| Tool / function          | Description                                     | Parameters                                   | Return / behavior                                                 | Used by                                              |
| ------------------------ | ----------------------------------------------- | -------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------- |
| `FileEditor.apply_patch` | Safe search/replace in one file under workspace | `file_path`, `search_block`, `replace_block` | `True` if exactly one match replaced (after backup); else `False` | MigrationPlanner in `execute_plan`                   |
| `FileEditor.create_file` | Create or overwrite file under workspace        | `file_path`, `content`                       | None (raises if path escapes workspace)                           | Available; not used by current planner prompt schema |


**Not in this repo:** No `schema_lookup`, `validate_sql`, or SQL execution tools. VectorStore ([src/shared/store.py](src/shared/store.py)) and LocalEmbedder ([src/shared/embedder.py](src/shared/embedder.py)) exist for RAG but are **not** wired into any agent flow.

---

## 5. Dependencies

**LLM / API:**

- **anthropic** — MigrationPlanner (Anthropic path), [src/shared/audit_anthropic.py](src/shared/audit_anthropic.py), [tests/verify_architect.py](tests/verify_architect.py).
- **openai** — MigrationPlanner (OpenAI path), [src/shared/diagnostics.py](src/shared/diagnostics.py), [tests/verify_architect.py](tests/verify_architect.py).

**Other (from imports in repo):**

- **python-dotenv** — diagnostics, audit, test harnesses.
- **lancedb**, **pyarrow** — VectorStore ([src/shared/store.py](src/shared/store.py)); not used by the Architect.
- **sentence_transformers** — LocalEmbedder ([src/shared/embedder.py](src/shared/embedder.py)); not used by the Architect.

**Not used:** No LangChain, LangGraph, PydanticAI, or other third-party agent framework. Implementation is custom: Python classes, direct SDK calls, in-memory execution.

**Note:** DataShark_Agents has no local `pyproject.toml` or `requirements.txt`; dependency list is inferred from source. Parent DataShark repo may declare a superset (e.g. litellm, chromadb, mcp).

---

## Summary

- **Agents:** One operational agent (Migration Architect = MigrationPlanner + FileEditor); no SQL Generator/Validator/Orchestrator in this repo.
- **Orchestration:** Single-shot, sequential (generate_plan → LLM → parse JSON → execute_plan → apply_patch/create_file); no graph or message bus.
- **Prompts:** Single system + user prompt for MigrationPlanner (Senior Data Architect, strict JSON edit plan); no SQL-generation prompts in Agents.
- **Tools:** FileEditor only (`apply_patch`, `create_file`); no LLM tool-calling; no schema_lookup/validate_sql.
- **Dependencies:** anthropic, openai, python-dotenv (and lancedb/pyarrow/sentence_transformers for unused RAG); no LangChain/LangGraph/PydanticAI.
