# DataShark Architecture

High-level data flow, class hierarchy, and agent interaction model for the DataShark Agentic SQL Protocol.

## High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Entrypoints                                          │
│  CLI (datashark ask/serve/config/init) │ DBeaver (JSON-RPC) │ MCP (mcp_app)  │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Ingestion Layer                                                             │
│  • parsers: parse_dbt_manifest, parse_dbt_project_source, parse_lookml_file  │
│  • sniper: ContextSniper (file discovery, sqlglot for SQL deps)              │
│  • watcher: ProjectWatcher (watchdog-based real-time file monitoring)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Semantic Graph (The Meat)                                                   │
│  • SemanticGraph (networkx.MultiDiGraph): entities = nodes, joins = edges    │
│  • Weights: explicit joins (0.1), source YAML (0.5), FK (1.0), M:M (100)     │
│  • add_snapshot(), infer_edges(), shortest_path(), list_entities()           │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
              ┌───────────────────────────┼───────────────────────────┐
              ▼                           ▼                           ▼
┌──────────────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  QueryPlanner        │   │  process_request()   │   │  Optional: Brain     │
│  (LiteLLM)           │   │  (Zero-Agency Kernel)│   │  (Vanna/Chroma RAG)   │
│  NL → StructuredFilter│   │  StructuredFilter  │   │  DDL training, RAG   │
│  plan_query()        │   │  + Snapshot → SQL    │   │  fallback for SQL    │
└──────────────────────┘   └──────────────────────┘   └──────────────────────┘
              │                           │
              └───────────────────────────┼───────────────────────────┘
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SQL Builder (Strategy + Snapshot as Truth)                                  │
│  • SQLBuilder(dialect): build_final_sql(planner_output, snapshot)            │
│  • JoinPathResolver(snapshot, dialect): resolve_joins_from_entity_list()     │
│  • Dialects: PostgresDialect (default), DuckDBDialect, BigQueryDialect       │
│  • Redshift: Postgres dialect + optional lint_redshift_compat() when safe    │
└─────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
                              Executable SQL (string)
```

## Class and Module Hierarchy

### Core Types (`datashark.core.types`)

- **FieldType**, **JoinType**: Enums for field/join classification.
- **Entity**, **FieldDef**, **JoinDef**: Pydantic models for schema elements.
- **SemanticSnapshot**: Root model (snapshot_id, entities, fields, joins, metadata).
- **TemporalUnit**, **TemporalOperator**, **TemporalFilter**: Time-based filters.
- **FilterOperator**, **FilterDef**: Generic filter predicates.

### Graph and Validation

- **SemanticGraph** (`datashark.core.graph`): Holds NetworkX graph, snapshots, field cache; add_snapshot, infer_edges, shortest_path.
- **validate_snapshot** (`datashark.core.validation`): Validates snapshot dict before SQL generation.

### SQL Layer (`datashark.core.sql`)

- **SQLDialect** (ABC): quote_identifier, render_temporal_filter, render_interval, render_date_trunc.
- **PostgresDialect**, **DuckDBDialect**, **BigQueryDialect**: Concrete implementations.
- **SQLBuilder**: build_final_sql(planner_output, snapshot); uses JoinPathResolver and dialect for SELECT/FROM/JOIN/WHERE/GROUP BY.
- **JoinPathResolver**: Resolves join order and conditions from snapshot.joins (single source of truth).

### Parsers (`datashark.core.parsers`)

- **parse_dbt_manifest(manifest_path)** → SemanticSnapshot
- **parse_dbt_project_source(project_root)** → SemanticSnapshot
- **parse_lookml_file(file_path)** → SemanticSnapshot
- **detect_source_type(file_path|source_text)** → "dbt" | "lookml" | "dbt_manifest" | etc.

### Runtime

- **QueryPlanner** (`datashark.runtime.planner.planner`): LiteLLM-based; plan_query(query, graph) → structured filter (concept_map, join_path, grain_context, policy_context).

### Kernel Entrypoint

- **process_request(snapshot, structured_filter)** (`datashark.core.api`): Validates snapshot, sets dialect, delegates to SQLBuilder.build_final_sql. No LLM in this path.

### Servers and Agents

- **DataSharkServer** (`datashark.core.server`): JSON-RPC 2.0 over stdio for DBeaver. Methods: ping, initialize, ingest_context, generate_sql, verify_sql. Uses sniper, watcher, planner, optional Brain and Redshift lint.
- **mcp_app** (`datashark.mcp_app`): FastMCP server. Tools: ingest_source, solve_path, ask_datashark. Canonical MCP entrypoint: `python -m datashark.mcp_app`.
- **mcp_server** (deprecated): Hand-rolled MCP-shaped JSON-RPC; prefer mcp_app.

## Agent Interaction Model

1. **Thin clients** (DBeaver plugin, Cursor MCP config) send requests to either:
   - **datashark serve** → DataSharkServer (custom JSON-RPC), or
   - **python -m datashark.mcp_app** → FastMCP (tools/call).
2. **Ingestion**: Client or server triggers parsing (manifest, dbt project, LookML). Results are merged into SemanticGraph and optionally persisted as snapshots.
3. **NL → SQL**: User query → QueryPlanner.plan_query(query, graph) → structured filter. Server may use optional Brain (Vanna RAG) for DDL context. process_request(snapshot, structured_filter) → final SQL.
4. **Redshift**: When safety_kernel.redshift_guardrails is available, generate_sql/verify_sql can call lint_redshift_compat(sql) and, in a separate path, transform_sql_for_redshift_safety(sql). Default SQL is Postgres-dialect; Redshift 1.0 targets Postgres 8.0.2 compatibility.

## Dependency Direction (No Cycles)

- **core.types** ← core.validation, core.graph, core.parsers, core.sql.*, core.api
- **core.api** ← core.sql.builder, core.validation
- **core.graph** ← core.types, networkx
- **core.sql.builder** ← core.sql.dialects, core.sql.join_resolver, core.types
- **runtime.planner** ← core.graph, core.types
- **server / mcp_app** ← core.api, core.graph, core.parsers, core.types, runtime.planner, ingestion.*

All agent-facing entrypoints depend inward on core and runtime; core does not import server or mcp_app.
