# Determinism Audit Report

### 1. Determinism Contract

The codebase implements determinism controls for LLM generation but lacks persistence for the intermediate Intent IR (Intermediate Representation).

*   **LLM Parameters:**
    *   **Agent Brain:** `src/datashark/agent/brain.py`
        ```python
        103:            temperature=0.0
        ```
    *   **Query Planner:** `src/datashark/runtime/planner/planner.py`
        ```python
        176:            temperature=0.1,  # Low temperature for deterministic extraction
        ```
    *   **Seed:** No explicit `seed` parameter is passed to the LLM completion calls in either `brain.py` or `planner.py`.

*   **Intent IR Persistence:**
    *   **Not Found:** The system does not persist or cache the parsed Intent IR (structured filters) between runs.
    *   `src/datashark/agent/brain.py` regenerates the answer via RAG for every call (`ask` method).
    *   `src/datashark/runtime/planner/planner.py` calls LiteLLM to generate the plan from scratch for every query (`plan_query` method).

### 2. End-to-end Determinism Trace

**Path:** User Prompt → Intent Parse → Planner → SQL Emitter

1.  **Ingestion (Non-Deterministic Source)**
    *   **Step:** File Discovery
    *   **File:** `src/datashark/core/server.py`
    *   **Function:** `ingest_context`
    *   **Snippet:**
        ```python
        200:        lookml_files = list(self.workspace_root.glob("*.lkml"))
        ```
    *   **Input:** Filesystem state.
    *   **Output:** List of `Path` objects (Order dependent on OS/Filesystem).

2.  **Graph Construction (Inherits Ingestion Order)**
    *   **Step:** Node Insertion
    *   **File:** `src/datashark/core/graph.py`
    *   **Function:** `add_snapshot`
    *   **Snippet:**
        ```python
        57:        for entity_id, entity in snapshot.entities.items():
        58:            self.graph.add_node(entity_id, entity=entity, snapshot_id=snapshot.snapshot_id)
        ```
    *   **Input:** `SemanticSnapshot` object.
    *   **Output:** Updated `networkx.MultiDiGraph` (Node iteration order depends on insertion order).

3.  **Planner Retrieval (Order Sensitive)**
    *   **Step:** Context Retrieval
    *   **File:** `src/datashark/runtime/planner/planner.py`
    *   **Function:** `plan_query`
    *   **Snippet:**
        ```python
        84:        all_entity_ids = graph.list_entities()
        ...
        96:        entity_scores.sort(reverse=True, key=lambda x: x[0])
        97:        top_entities = [name for _, name in entity_scores[:50]]
        ```
    *   **Input:** `SemanticGraph`.
    *   **Output:** `top_entities` list. If scores are tied, the sort is stable, preserving the non-deterministic ingestion order.

4.  **Intent Parsing (LLM)**
    *   **Step:** Reasoning
    *   **File:** `src/datashark/runtime/planner/planner.py`
    *   **Function:** `plan_query`
    *   **Snippet:**
        ```python
        170:        response = litellm.completion(
        171:            model=f"{self.provider}/{self.model}",
        ...
        176:            temperature=0.1,  # Low temperature for deterministic extraction
        177:        )
        ```
    *   **Input:** `system_prompt` + `user_message` (Context list order depends on Step 3).
    *   **Output:** JSON string (Structured Filter).

5.  **SQL Emitter (Canonicalized Fallback)**
    *   **Step:** SQL Generation
    *   **File:** `src/datashark/core/sql/builder.py`
    *   **Function:** `build_final_sql` / `_build_joins_from_snapshot`
    *   **Snippet:**
        ```python
        170:                if snapshot.entities:
        171:                    first_entity_id = sorted(snapshot.entities.keys())[0]
        172:                    entity_ids = [first_entity_id]
        ```
    *   **Input:** `planner_output` (dict) and `SemanticSnapshot`.
    *   **Output:** SQL string. Note: Explicit sorting is used here for fallback entity selection.

### 3. Ordering / Iteration Dependencies

| Type | Classification | Location |
| :--- | :--- | :--- |
| **Filesystem Traversal** | **Inherited/Implicit** | `src/datashark/core/server.py` `list(self.workspace_root.glob("*.lkml"))` (Line 200) |
| **Filesystem Traversal** | **Inherited/Implicit** | `src/datashark/core/parsers.py` `list(models_path.rglob("*.yml"))` (Line 260) |
| **JSON Serialization** | **Canonicalized** | `src/datashark/core/parsers.py` `json.dumps(..., sort_keys=True)` (Lines 216, 440, 733) |
| **Graph Node Iteration** | **Inherited/Implicit** | `src/datashark/core/graph.py` `list(self.graph.nodes())` (Line 468) |
| **Graph Edge Inference** | **Inherited/Implicit** | `src/datashark/core/graph.py` `for source_entity_id in self.graph.nodes():` (Line 198) |
| **Entity Context Selection**| **Unknown** (Unstable Sort) | `src/datashark/runtime/planner/planner.py` `entity_scores.sort(...)` (Line 96) - Depends on graph order for ties. |
| **SQL Entity Fallback** | **Canonicalized** | `src/datashark/core/sql/builder.py` `sorted(snapshot.entities.keys())` (Line 171) |

### 4. Determinism Tests

*   **`tests/test_determinism_proof.py`**
    *   **`test_ingestion_determinism`**: Asserts that snapshot ID generation is deterministic by testing `json.dumps` with `sort_keys=True`.
        ```python
        36:    assert hash1 == hash2
        ```
    *   **`test_sql_generation_stability`**: Asserts that `SQLBuilder` produces identical SQL strings for identical inputs.
        ```python
        117:    assert sql1 == sql2
        ```
    *   **`test_graph_iteration_order`**: Discusses graph iteration order but contains `pass` and no active assertions.

*   **`tests/learning/test_model_updater.py`**
    *   **`test_model_update_determinism`**: Asserts that model updates are deterministic when a seed is provided.
        ```python
        76:    hash1 = storage.save_model("test_model", model_data, seed=42)
        ```
