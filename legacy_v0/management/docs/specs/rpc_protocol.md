# DataShark Universal Sidecar Protocol (JSON-RPC 2.0)

**Version:** 1.0.0
**Transport:** Standard I/O (stdio)
**Encoding:** UTF-8

The DataShark Kernel (`datashark-core`) operates as a "Headless Server" that communicates with "Skins" (VS Code, DBeaver) via strict JSON-RPC 2.0 over Stdio.

## 1. initialize

**Purpose:** Handshakes with the Skin, sets the working directory, and registers available context files.

### Request
```json
{
  "jsonrpc": "2.0",
  "method": "initialize",
  "params": {
    "workspace_root": "/Users/dev/repo",
    "context_files": [
        "models/staging/stg_users.sql",
        "models/marts/dim_users.yml",
        "looks/sales_dashboard.lkml"
    ],
    "client_info": {
        "name": "vscode-datashark",
        "version": "1.0.0"
    }
  },
  "id": 1
}
```

### Response
```json
{
  "jsonrpc": "2.0",
  "result": {
    "status": "ready",
    "kernel_version": "0.1.0",
    "capabilities": {
        "dbt": true,
        "lookml": true,
        "airflow": false
    }
  },
  "id": 1
}
```

## 2. ingest_context

**Purpose:** Triggers the Ingestion Agent to parse the registered files and build the in-memory Semantic Graph.

### Request
```json
{
  "jsonrpc": "2.0",
  "method": "ingest_context",
  "params": {
    "force": false
  },
  "id": 2
}
```

### Response
```json
{
  "jsonrpc": "2.0",
  "result": {
    "graph_summary": {
        "nodes": 145,
        "edges": 312,
        "sources": ["dbt", "lookml"],
        "status": "healthy"
    },
    "duration_ms": 1250
  },
  "id": 2
}
```

## 3. generate_sql

**Purpose:** The main generation loop. Translates a natural language prompt (and optional structured constraints) into verified SQL.

### Request
```json
{
  "jsonrpc": "2.0",
  "method": "generate_sql",
  "params": {
    "user_prompt": "Show me total revenue by region for 2024",
    "structured_filter": {
        "limit": 100,
        "dialect": "postgres"
    }
  },
  "id": 3
}
```

### Response
```json
{
  "jsonrpc": "2.0",
  "result": {
    "sql": "SELECT region, SUM(amount) as total_revenue FROM fct_orders WHERE order_date BETWEEN '2024-01-01' AND '2024-12-31' GROUP BY 1",
    "explanation": "Joined `fct_orders` with `dim_regions` on `region_id`. Filtered for 2024.",
    "confidence_score": 0.95,
    "semantic_path": ["fct_orders", "dim_regions"]
  },
  "id": 3
}
```

## 4. verify_sql

**Purpose:** The safety loop. Analyzes arbitrary SQL (written by user or generated) for semantic correctness and safety risks.

### Request
```json
{
  "jsonrpc": "2.0",
  "method": "verify_sql",
  "params": {
    "sql": "SELECT * FROM huge_table"
  },
  "id": 4
}
```

### Response
```json
{
  "jsonrpc": "2.0",
  "result": {
    "is_valid": true,
    "risks": [
        {
            "severity": "high",
            "type": "performance",
            "message": "Unbounded SELECT on 'huge_table' (10B+ rows). Add a LIMIT or partition filter."
        },
        {
            "severity": "low",
            "type": "deprecation",
            "message": "Column 'legacy_id' is marked as deprecated in dbt."
        }
    ]
  },
  "id": 4
}
```

## Error Handling

Standard JSON-RPC 2.0 error codes apply.

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32603,
    "message": "Graph not initialized. Call 'ingest_context' first.",
    "data": { "retry_after": 0 }
  },
  "id": null
}
```
