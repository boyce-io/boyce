/**
 * Boyce VS Code Extension — Type Definitions
 *
 * Mirrors the JSON contracts from boyce.http_api endpoints.
 * Keep in sync with boyce/src/boyce/http_api.py and boyce/src/boyce/types.py.
 */

// ---------------------------------------------------------------------------
// HTTP API response types
// ---------------------------------------------------------------------------

export interface HealthResponse {
    status: "ok";
    version: string;
}

export interface SchemaEntity {
    name: string;
    fields: SchemaField[];
    joins?: JoinDef[];
    description?: string;
}

export interface SchemaField {
    name: string;
    data_type: string;
    nullable?: boolean;
    is_primary_key?: boolean;
    is_foreign_key?: boolean;
    description?: string;
    references?: string;
}

export interface JoinDef {
    from_entity: string;
    to_entity: string;
    from_field: string;
    to_field: string;
    join_type: string;
    weight: number;
}

export interface SchemaResponse {
    entities: SchemaEntity[];
    snapshot_id: string;
    error?: string;
}

export interface AskResponse {
    sql: string;
    validation: {
        status: "verified" | "invalid" | "unchecked";
        error?: string;
    };
    compat_risks: string[];
    snapshot_id: string;
    entities_resolved: string[];
    null_trap_warnings: NullTrapWarning[];
    error?: string;
}

export interface NullTrapWarning {
    code: string;
    message: string;
    column: string;
    null_pct: number;
}

export interface ChatResponse {
    reply: string;
    tool_used: string;
    data: Record<string, unknown>;
    error?: { code: number; message: string };
}

export interface QueryResponse {
    columns: string[];
    rows: Record<string, unknown>[];
    row_count: number;
    error?: string;
    blocked?: boolean;
}

export interface ProfileResponse {
    table: string;
    column: string;
    total_rows: number;
    null_count: number;
    null_pct: number;
    distinct_count: number;
    min_value?: string;
    max_value?: string;
    error?: string;
}

export interface BuildSqlResponse {
    sql: string;
    validation: {
        status: "verified" | "invalid" | "unchecked";
        error?: string;
    };
    compat_risks: string[];
    snapshot_id: string;
    entities_resolved: string[];
    null_trap_warnings: NullTrapWarning[];
    error?: string;
}

// ---------------------------------------------------------------------------
// Extension-internal types
// ---------------------------------------------------------------------------

export interface BoyceConfig {
    http_token?: string;
    [key: string]: unknown;
}

export interface ChatMessage {
    role: "user" | "assistant";
    content: string;
    timestamp: Date;
    toolUsed?: string;
    sql?: string;
}
