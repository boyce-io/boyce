/**
 * Schema Tree Data Provider
 * Provides hierarchical view of database schemas, tables, and columns
 */

import * as vscode from 'vscode';
import { MCPClient, Schema, Table, Column } from '../mcp/client';
import { InstanceAPI } from '../utils/instanceApi';

export class SchemaTreeDataProvider implements vscode.TreeDataProvider<TreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<TreeItem | undefined | null | void> = new vscode.EventEmitter<TreeItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<TreeItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private mcpClient: MCPClient;
    private context: vscode.ExtensionContext;
    private cache: any = null;
    private cacheKey = 'datashark.schemaTree';
    private instanceApi: InstanceAPI | null = null;
    private activeInstanceName: string | null = null;

    constructor(mcpClient: MCPClient, context: vscode.ExtensionContext, instanceApi?: InstanceAPI) {
        this.mcpClient = mcpClient;
        this.context = context;
        this.instanceApi = instanceApi || null;
        this.loadCache();
        this.updateInstanceName();
    }

    private async updateInstanceName(): Promise<void> {
        if (this.instanceApi) {
            try {
                const active = await this.instanceApi.getActiveInstance();
                if (active) {
                    this.activeInstanceName = active.path.split('/').pop() || null;
                }
            } catch (error) {
                console.debug('Failed to get active instance name:', error);
            }
        }
    }

    private loadCache(): void {
        const cached = this.context.globalState.get(this.cacheKey);
        if (cached) {
            this.cache = cached;
        }
    }

    private saveCache(tree: any): void {
        this.cache = tree;
        this.context.globalState.update(this.cacheKey, tree);
    }

    refresh(): void {
        this.updateInstanceName();
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: TreeItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: TreeItem): Promise<TreeItem[]> {
        if (!element) {
            // Root level - load schema tree from Context API
            try {
                const startTime = Date.now();
                
                // Try to get from cache first
                if (this.cache && this.cache.tree) {
                    const tree = this.cache.tree;
                    const latency = Date.now() - startTime;
                    this.logTelemetry('schema_load_time_ms', latency, 'cache');
                    
                    // Return system item (root)
                    return [new SystemItem(tree.system || 'database', tree)];
                }
                
                // Fetch from MCP
                const result = await this.mcpClient.callTool('get_schema_tree', { system: 'database' });
                const latency = Date.now() - startTime;
                this.logTelemetry('schema_load_time_ms', latency, 'mcp');
                
                if (result.tree) {
                    this.saveCache(result);
                    return [new SystemItem(result.tree.system || 'database', result.tree)];
                } else if (result.schemas) {
                    // Fallback: old format
                    return result.schemas.map((s: any) => new SchemaItem(s));
                } else {
                    vscode.window.showWarningMessage('No schema data available');
                    return [];
                }
            } catch (error) {
                vscode.window.showErrorMessage(`Failed to load schema tree: ${error}`);
                return [];
            }
        } else if (element instanceof SystemItem) {
            // System level - show schemas
            const tree = element.tree;
            return tree.schemas.map((schema: any) => new SchemaItem(schema, tree));
        } else if (element instanceof SchemaItem) {
            // Schema level - show tables
            const schema = element.schema;
            if (schema.tables) {
                return schema.tables.map((table: any) => new TableItem(schema.name, table));
            }
            return [];
        } else if (element instanceof TableItem) {
            // Table level - show columns
            const table = element.table;
            if (table.columns && Array.isArray(table.columns)) {
                return table.columns.map((column: any) => new ColumnItem(element.schemaName, element.table.name, column));
            }
            return [];
        }
        
        return [];
    }

    private logTelemetry(metric: string, value: number, source: string): void {
        // Log to extension output or telemetry file
        const telemetry = {
            timestamp: new Date().toISOString(),
            metric,
            value,
            source
        };
        console.log(`[Telemetry] ${JSON.stringify(telemetry)}`);
    }
}

abstract class TreeItem extends vscode.TreeItem {
    abstract contextValue: string;
}

class SystemItem extends TreeItem {
    contextValue = 'system';
    
    constructor(public systemName: string, public tree: any) {
        super(systemName, vscode.TreeItemCollapsibleState.Expanded);
        this.tooltip = `System: ${systemName}`;
        this.description = `${tree.schemas?.length || 0} schemas`;
        this.iconPath = new vscode.ThemeIcon('database');
    }
}

class SchemaItem extends TreeItem {
    contextValue = 'schema';
    
    constructor(public schema: any, public tree?: any) {
        const name = typeof schema === 'string' ? schema : schema.name;
        super(name, vscode.TreeItemCollapsibleState.Collapsed);
        
        const tableCount = schema.tables ? schema.tables.length : (typeof schema === 'object' && schema.table_count ? schema.table_count : 0);
        this.tooltip = `Schema: ${name}\nTables: ${tableCount}`;
        this.description = `${tableCount} tables`;
        this.iconPath = new vscode.ThemeIcon('folder-library');
        
        // Store schema object for tree traversal
        if (typeof schema === 'object') {
            this.schema = schema;
        } else {
            this.schema = { name: schema };
        }
    }
}

class TableItem extends TreeItem {
    contextValue = 'table';
    
    constructor(public schemaName: string, public table: Table) {
        super(table.name, vscode.TreeItemCollapsibleState.Collapsed);
        
        this.tooltip = this.buildTooltip();
        this.description = this.buildDescription();
        this.iconPath = new vscode.ThemeIcon('table');
        
        // Enable context menu
        this.contextValue = 'table';
    }
    
    private buildTooltip(): string {
        const parts = [`Table: ${this.schemaName}.${this.table.name}`];
        if (this.table.column_count) {
            parts.push(`Columns: ${this.table.column_count}`);
        }
        if (this.table.row_count) {
            parts.push(`Rows: ${this.table.row_count.toLocaleString()}`);
        }
        if (this.table.size_mb) {
            parts.push(`Size: ${this.table.size_mb.toFixed(2)} MB`);
        }
        return parts.join('\n');
    }
    
    private buildDescription(): string {
        const parts: string[] = [];
        if (this.table.column_count) {
            parts.push(`${this.table.column_count} cols`);
        }
        if (this.table.row_count && this.table.row_count > 0) {
            parts.push(`${this.formatNumber(this.table.row_count)} rows`);
        }
        return parts.join(', ');
    }
    
    private formatNumber(num: number): string {
        if (num >= 1_000_000) {
            return `${(num / 1_000_000).toFixed(1)}M`;
        } else if (num >= 1_000) {
            return `${(num / 1_000).toFixed(1)}K`;
        }
        return num.toString();
    }
}

class ColumnItem extends TreeItem {
    contextValue = 'column';
    
    constructor(
        public schemaName: string,
        public tableName: string,
        public column: Column
    ) {
        super(column.name, vscode.TreeItemCollapsibleState.None);
        
        this.tooltip = this.buildTooltip();
        this.description = column.type;
        this.iconPath = this.getIconForDataType(column.type);
    }
    
    private buildTooltip(): string {
        const parts = [
            `Column: ${this.column.name}`,
            `Type: ${this.column.type}`
        ];
        
        if (this.column.nullable !== undefined) {
            parts.push(`Nullable: ${this.column.nullable ? 'Yes' : 'No'}`);
        }
        
        if (this.column.default) {
            parts.push(`Default: ${this.column.default}`);
        }
        
        return parts.join('\n');
    }
    
    private getIconForDataType(dataType: string): vscode.ThemeIcon {
        const type = dataType.toLowerCase();
        
        if (type.includes('int') || type.includes('numeric') || type.includes('decimal') || type.includes('float') || type.includes('double')) {
            return new vscode.ThemeIcon('symbol-number');
        } else if (type.includes('char') || type.includes('text') || type.includes('string')) {
            return new vscode.ThemeIcon('symbol-string');
        } else if (type.includes('bool')) {
            return new vscode.ThemeIcon('symbol-boolean');
        } else if (type.includes('date') || type.includes('time') || type.includes('timestamp')) {
            return new vscode.ThemeIcon('calendar');
        } else if (type.includes('json')) {
            return new vscode.ThemeIcon('symbol-object');
        } else if (type.includes('array')) {
            return new vscode.ThemeIcon('symbol-array');
        }
        
        return new vscode.ThemeIcon('symbol-field');
    }
}


