/**
 * Schema Tree Data Provider
 *
 * Displays the semantic schema (entities → fields) in the VS Code sidebar.
 * Data comes from the Boyce HTTP API /schema endpoint — NOT raw database schemas.
 * This shows SemanticSnapshot entities, not pg_catalog tables.
 */

import * as vscode from "vscode";
import { BoyceClient } from "../client";
import type { SchemaEntity, SchemaField } from "../types";

export class SchemaTreeProvider implements vscode.TreeDataProvider<SchemaTreeItem> {
    private _onDidChangeTreeData = new vscode.EventEmitter<
        SchemaTreeItem | undefined | null | void
    >();
    readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

    private entities: SchemaEntity[] = [];

    constructor(private client: BoyceClient) {}

    refresh(): void {
        this.entities = [];
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: SchemaTreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: SchemaTreeItem): Promise<SchemaTreeItem[]> {
        if (!element) {
            return this.getRootEntities();
        }
        if (element instanceof EntityItem) {
            return this.getEntityFields(element.entity);
        }
        return [];
    }

    private async getRootEntities(): Promise<SchemaTreeItem[]> {
        if (this.entities.length > 0) {
            return this.entities.map((e) => new EntityItem(e));
        }

        try {
            const response = await this.client.getSchema();
            if (response.error) {
                vscode.window.showWarningMessage(
                    `Boyce schema: ${response.error}`,
                );
                return [];
            }
            this.entities = response.entities || [];
            return this.entities.map((e) => new EntityItem(e));
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            // Don't spam errors if server isn't running yet
            if (msg.includes("ECONNREFUSED") || msg.includes("fetch failed")) {
                return [new MessageItem("Boyce server not running")];
            }
            vscode.window.showErrorMessage(`Failed to load schema: ${msg}`);
            return [];
        }
    }

    private getEntityFields(entity: SchemaEntity): SchemaTreeItem[] {
        return (entity.fields || []).map((f) => new FieldItem(entity.name, f));
    }
}

// ---------------------------------------------------------------------------
// Tree item classes
// ---------------------------------------------------------------------------

type SchemaTreeItem = EntityItem | FieldItem | MessageItem;

class EntityItem extends vscode.TreeItem {
    contextValue = "entity";

    constructor(public readonly entity: SchemaEntity) {
        super(entity.name, vscode.TreeItemCollapsibleState.Collapsed);
        const fieldCount = entity.fields?.length ?? 0;
        this.description = `${fieldCount} fields`;
        this.tooltip = entity.description
            ? `${entity.name}\n${entity.description}`
            : entity.name;
        this.iconPath = new vscode.ThemeIcon("table");
    }
}

class FieldItem extends vscode.TreeItem {
    contextValue = "field";

    constructor(entityName: string, public readonly field: SchemaField) {
        super(field.name, vscode.TreeItemCollapsibleState.None);
        this.description = field.data_type;
        this.tooltip = this.buildTooltip(entityName);
        this.iconPath = this.iconForType(field.data_type);
    }

    private buildTooltip(entityName: string): string {
        const parts = [`${entityName}.${this.field.name}`, `Type: ${this.field.data_type}`];
        if (this.field.nullable !== undefined) {
            parts.push(`Nullable: ${this.field.nullable ? "Yes" : "No"}`);
        }
        if (this.field.is_primary_key) {
            parts.push("Primary Key");
        }
        if (this.field.is_foreign_key && this.field.references) {
            parts.push(`FK → ${this.field.references}`);
        }
        if (this.field.description) {
            parts.push(`\n${this.field.description}`);
        }
        return parts.join("\n");
    }

    private iconForType(dataType: string): vscode.ThemeIcon {
        const t = dataType.toLowerCase();
        if (/int|numeric|decimal|float|double/.test(t)) {
            return new vscode.ThemeIcon("symbol-number");
        }
        if (/char|text|string|varchar/.test(t)) {
            return new vscode.ThemeIcon("symbol-string");
        }
        if (/bool/.test(t)) {
            return new vscode.ThemeIcon("symbol-boolean");
        }
        if (/date|time|timestamp/.test(t)) {
            return new vscode.ThemeIcon("calendar");
        }
        if (/json/.test(t)) {
            return new vscode.ThemeIcon("symbol-object");
        }
        return new vscode.ThemeIcon("symbol-field");
    }
}

class MessageItem extends vscode.TreeItem {
    contextValue = "message";

    constructor(message: string) {
        super(message, vscode.TreeItemCollapsibleState.None);
        this.iconPath = new vscode.ThemeIcon("info");
    }
}
