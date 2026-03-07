# DataShark — Ingestion Concepts & Protocol

This document defines the **Ontology** that the Ingestion Agent must map raw data into. The Output of this process is a valid `SemanticSnapshot` JSON.

## 1. The Core Philosophy: "Progressive Enrichment"

We do not demand perfect metadata. We accept what is available and tag it with a `confidence` score.

* **Tier 1 (Physical):** You see only DDL. You infer Grains/Measures from naming conventions. (Confidence: Low)
* **Tier 2 (Semantic):** You see LookML/dbt. You extract explicit definitions. (Confidence: High)
* **Tier 3 (Operational):** You see Query Logs. You prioritize based on usage. (Confidence: High)

## 2. The Ontology (Definitions)

### 2.1 The Entity (Table)
A logical collection of rows.
* **Invariant:** Every Entity MUST have a `grain`.
* **The Grain:** The set of columns that uniquely identifies a row.
    * *If unknown:* Mark as `<unknown_grain>`. The Kernel will restrict aggregation on this table.
    * *Agent Heuristic:* Look for `PRIMARY KEY` constraints, unique indexes, or fields ending in `_id`.

### 2.2 The Measure (Metric)
A numeric field that can be aggregated (summed, averaged) over dimensions.
* **Invariant:** A Measure implies an aggregation function (default: `SUM`).
* **Negative Definition:** IDs, Foreign Keys, and Timestamps are NEVER Measures, even if they are numeric types.
* **Agent Heuristic:** Look for fields named `amount`, `revenue`, `count`, `duration`. Ignore `_id`, `_key`.

### 2.3 The Dimension (Attribute)
A field used for grouping or filtering.
* **Types:** `Categorical` (String), `Temporal` (Date/Time), `Boolean`.
* **Agent Heuristic:** Low-cardinality strings (status, type), dates, and flags.

### 2.4 The Join (Relationship)
A directed path from one Entity (Source) to another (Target).
* **Invariant:** We only support `LEFT` and `INNER` joins in the golden path.
* **Cardinality:** The Agent must infer `one-to-one`, `one-to-many`, or `many-to-one` based on the Grain of the target table.

## 3. The Ingestion Protocol (Agent Instructions)

When asked to "Ingest [Source]":
1.  **Scan** the input text (DDL, LookML, or dbt YAML).
2.  **Map** the physical columns to the Concepts above.
3.  **Construct** a JSON object adhering to `datashark.core.types.SemanticSnapshot`.
4.  **Validate** strictly:
    * Do not hallucinate joins that don't exist in foreign keys (unless explicitly told).
    * If a field's purpose is ambiguous, default to `Dimension` (safe) rather than `Measure` (risky).
