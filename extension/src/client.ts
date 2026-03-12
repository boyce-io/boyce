/**
 * Boyce HTTP Client
 *
 * Calls the Boyce HTTP API (boyce serve --http).
 * All intelligence lives server-side — this is a thin fetch wrapper.
 */

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";
import type {
    HealthResponse,
    SchemaResponse,
    AskResponse,
    ChatResponse,
    QueryResponse,
    ProfileResponse,
    BuildSqlResponse,
    BoyceConfig,
} from "./types";

export class BoyceClient {
    private token: string | null = null;

    get baseUrl(): string {
        return vscode.workspace
            .getConfiguration("boyce")
            .get<string>("serverUrl", "http://localhost:8741");
    }

    private get defaultDialect(): string {
        return vscode.workspace
            .getConfiguration("boyce")
            .get<string>("defaultDialect", "redshift");
    }

    private get snapshotName(): string {
        return vscode.workspace
            .getConfiguration("boyce")
            .get<string>("snapshotName", "default");
    }

    // -----------------------------------------------------------------------
    // Token resolution
    // -----------------------------------------------------------------------

    /**
     * Load Bearer token from .boyce/config.json in the workspace root.
     * Falls back to BOYCE_HTTP_TOKEN env var.
     */
    loadToken(): string | null {
        // 1. Env var
        const envToken = process.env.BOYCE_HTTP_TOKEN;
        if (envToken) {
            this.token = envToken;
            return this.token;
        }

        // 2. .boyce/config.json in workspace
        const workspaceRoot =
            vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (workspaceRoot) {
            const configPath = path.join(workspaceRoot, ".boyce", "config.json");
            try {
                const raw = fs.readFileSync(configPath, "utf-8");
                const config: BoyceConfig = JSON.parse(raw);
                if (config.http_token) {
                    this.token = config.http_token;
                    return this.token;
                }
            } catch {
                // config doesn't exist yet — that's fine
            }
        }

        return null;
    }

    // -----------------------------------------------------------------------
    // HTTP helpers
    // -----------------------------------------------------------------------

    private headers(): Record<string, string> {
        const h: Record<string, string> = {
            "Content-Type": "application/json",
        };
        if (this.token) {
            h["Authorization"] = `Bearer ${this.token}`;
        }
        return h;
    }

    private async post<T>(endpoint: string, body: Record<string, unknown>): Promise<T> {
        const url = `${this.baseUrl}${endpoint}`;
        const resp = await fetch(url, {
            method: "POST",
            headers: this.headers(),
            body: JSON.stringify(body),
        });
        const data = await resp.json() as T;
        return data;
    }

    // -----------------------------------------------------------------------
    // API methods — one per endpoint
    // -----------------------------------------------------------------------

    async health(): Promise<HealthResponse> {
        const url = `${this.baseUrl}/health`;
        const resp = await fetch(url, { method: "GET" });
        return (await resp.json()) as HealthResponse;
    }

    async getSchema(snapshotName?: string): Promise<SchemaResponse> {
        return this.post<SchemaResponse>("/schema", {
            snapshot_name: snapshotName ?? this.snapshotName,
        });
    }

    async buildSql(
        structuredFilter: Record<string, unknown>,
        snapshotName?: string,
        dialect?: string,
    ): Promise<BuildSqlResponse> {
        return this.post<BuildSqlResponse>("/build-sql", {
            structured_filter: structuredFilter,
            snapshot_name: snapshotName ?? this.snapshotName,
            dialect: dialect ?? this.defaultDialect,
        });
    }

    async ask(query: string, snapshotName?: string, dialect?: string): Promise<AskResponse> {
        return this.post<AskResponse>("/ask", {
            query,
            snapshot_name: snapshotName ?? this.snapshotName,
            dialect: dialect ?? this.defaultDialect,
        });
    }

    async chat(message: string, snapshotName?: string, dialect?: string): Promise<ChatResponse> {
        return this.post<ChatResponse>("/chat", {
            message,
            snapshot_name: snapshotName ?? this.snapshotName,
            dialect: dialect ?? this.defaultDialect,
        });
    }

    async query(sql: string, reason?: string): Promise<QueryResponse> {
        return this.post<QueryResponse>("/query", {
            sql,
            reason: reason ?? "VS Code extension query",
        });
    }

    async profile(table: string, column: string): Promise<ProfileResponse> {
        return this.post<ProfileResponse>("/profile", { table, column });
    }

    async ingest(
        sourcePath?: string,
        snapshotJson?: string,
        snapshotName?: string,
    ): Promise<Record<string, unknown>> {
        return this.post<Record<string, unknown>>("/ingest", {
            source_path: sourcePath,
            snapshot_json: snapshotJson,
            snapshot_name: snapshotName ?? this.snapshotName,
        });
    }
}
