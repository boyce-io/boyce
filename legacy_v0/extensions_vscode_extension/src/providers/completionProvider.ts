/**
 * DataShark SQL Completion Provider
 * 
 * Provides intelligent, schema-aware SQL autocomplete that surpasses Copilot:
 * - Table name suggestions with schema context
 * - Column name suggestions with data types
 * - JOIN suggestions based on foreign keys
 * - SQL keyword completion
 * - Function suggestions
 */

import * as vscode from 'vscode';
import { MCPClient } from '../mcp/client';

interface CompletionContext {
    type: 'table' | 'column' | 'schema' | 'join' | 'function' | 'keyword';
    schema?: string;
    table?: string;
    prefix?: string;
}

export class DataSharkCompletionProvider implements vscode.CompletionItemProvider {
    private mcpClient: MCPClient;
    private cachedSchemas: string[] = [];
    private cachedTables: Map<string, any[]> = new Map();
    private cachedColumns: Map<string, any[]> = new Map();

    constructor(mcpClient: MCPClient) {
        this.mcpClient = mcpClient;
        this.refreshCache();
    }

    /**
     * Refresh metadata cache for faster completions
     */
    private async refreshCache(): Promise<void> {
        try {
            const startTime = Date.now();
            
            // Try to get schema tree from Context API (includes tables and columns)
            try {
                const treeResult = await this.mcpClient.callTool('get_schema_tree', { system: 'database' });
                if (treeResult.tree) {
                    const tree = treeResult.tree;
                    // Extract schemas
                    this.cachedSchemas = tree.schemas.map((s: any) => s.name);
                    
                    // Extract tables and columns
                    for (const schema of tree.schemas) {
                        const tables: any[] = [];
                        for (const table of schema.tables || []) {
                            tables.push({
                                name: table.name,
                                columns: table.columns || []
                            });
                            // Cache columns
                            const cacheKey = `${schema.name}.${table.name}`;
                            this.cachedColumns.set(cacheKey, table.columns || []);
                        }
                        this.cachedTables.set(schema.name, tables);
                    }
                    
                    const latency = Date.now() - startTime;
                    this.logTelemetry('autocomplete_cache_refresh_ms', latency);
                    return;
                }
            } catch (treeError) {
                console.debug('Schema tree not available, falling back to list_schemas:', treeError);
            }
            
            // Fallback: Cache all schemas
            const schemasResult = await this.mcpClient.callTool('list_schemas', {});
            if (schemasResult.schemas) {
                this.cachedSchemas = schemasResult.schemas.map((s: any) => typeof s === 'string' ? s : s.name);
            }

            // Cache tables for common schemas
            const commonSchemas = ['public', 'scratch', 'prod', 'staging'];
            for (const schema of commonSchemas) {
                if (this.cachedSchemas.includes(schema)) {
                    const tablesResult = await this.mcpClient.callTool('search_tables', {
                        schema,
                        pattern: '*'
                    });
                    if (tablesResult.tables) {
                        this.cachedTables.set(schema, tablesResult.tables);
                    }
                }
            }
            
            const latency = Date.now() - startTime;
            this.logTelemetry('autocomplete_cache_refresh_ms', latency);
        } catch (error) {
            console.error('Failed to refresh completion cache:', error);
        }
    }

    private logTelemetry(metric: string, value: number): void {
        const telemetry = {
            timestamp: new Date().toISOString(),
            metric,
            value,
            source: 'completion_provider'
        };
        console.log(`[Telemetry] ${JSON.stringify(telemetry)}`);
    }

    /**
     * Main completion entry point
     */
    async provideCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        token: vscode.CancellationToken,
        context: vscode.CompletionContext
    ): Promise<vscode.CompletionItem[] | vscode.CompletionList | undefined> {
        const startTime = Date.now();
        const lineText = document.lineAt(position).text;
        const textBeforeCursor = lineText.substring(0, position.character);
        const textAfterCursor = lineText.substring(position.character);

        // Detect what kind of completion is needed
        const completionContext = this.detectContext(textBeforeCursor, textAfterCursor, document, position);

        // Get appropriate suggestions
        let items: vscode.CompletionItem[] = [];
        switch (completionContext.type) {
            case 'schema':
                items = await this.suggestSchemas(completionContext.prefix);
                break;
            case 'table':
                items = await this.suggestTables(completionContext.schema, completionContext.prefix);
                break;
            case 'column':
                items = await this.suggestColumns(completionContext.schema, completionContext.table, completionContext.prefix);
                break;
            case 'join':
                items = await this.suggestJoins(completionContext.schema, completionContext.table);
                break;
            case 'function':
                items = this.suggestFunctions(completionContext.prefix);
                break;
            case 'keyword':
                items = this.suggestKeywords(completionContext.prefix);
                break;
            default:
                // Also try business concepts
                items = await Promise.all([
                    this.suggestKeywords(completionContext.prefix),
                    this.suggestBusinessConcepts(completionContext.prefix)
                ]).then(([keywords, concepts]) => [...keywords, ...concepts]);
                break;
        }
        
        // Log telemetry
        const latency = Date.now() - startTime;
        this.logTelemetry('autocomplete_latency_ms', latency);
        
        return items;
    }

    /**
     * Suggest business concepts from ConceptCatalog
     */
    private async suggestBusinessConcepts(prefix?: string): Promise<vscode.CompletionItem[]> {
        const items: vscode.CompletionItem[] = [];
        
        try {
            // Try to get concepts from MCP (if tool exists)
            const result = await this.mcpClient.callTool('search_concepts', {
                term: prefix || ''
            }).catch(() => null);
            
            if (result && result.concepts) {
                for (const concept of result.concepts) {
                    const item = new vscode.CompletionItem(concept.name, vscode.CompletionItemKind.Value);
                    item.detail = `Business Concept: ${concept.name}`;
                    item.documentation = new vscode.MarkdownString(
                        `**${concept.name}**\n\n${concept.description || ''}\n\n` +
                        `Aliases: ${(concept.aliases || []).join(', ')}`
                    );
                    item.sortText = `0_concept_${concept.name}`;
                    items.push(item);
                }
            }
        } catch (error) {
            // Concept search not available, skip
            console.debug('Concept search not available:', error);
        }
        
        return items;
    }

    /**
     * Detect what kind of completion is needed based on context
     */
    private detectContext(
        textBefore: string,
        textAfter: string,
        document: vscode.TextDocument,
        position: vscode.Position
    ): CompletionContext {
        const textBeforeTrimmed = textBefore.trim().toUpperCase();
        const lastWord = this.getLastWord(textBefore);
        const secondLastWord = this.getSecondLastWord(textBefore);

        // Schema.table pattern (after dot)
        if (textBefore.match(/(\w+)\.$/)) {
            const schemaMatch = textBefore.match(/(\w+)\.$/);
            if (schemaMatch) {
                return {
                    type: 'table',
                    schema: schemaMatch[1],
                    prefix: ''
                };
            }
        }

        // Schema.table.column pattern
        if (textBefore.match(/(\w+)\.(\w+)\.$/)) {
            const match = textBefore.match(/(\w+)\.(\w+)\.$/);
            if (match) {
                return {
                    type: 'column',
                    schema: match[1],
                    table: match[2],
                    prefix: ''
                };
            }
        }

        // After FROM keyword
        if (textBeforeTrimmed.match(/\bFROM\s+\w*$/)) {
            return {
                type: 'table',
                schema: 'public', // default schema
                prefix: lastWord
            };
        }

        // After JOIN keyword
        if (textBeforeTrimmed.match(/\bJOIN\s+\w*$/)) {
            // Find the table we're joining to
            const fromTable = this.findTableAfterFrom(document, position);
            return {
                type: 'join',
                table: fromTable || undefined,
                prefix: lastWord
            };
        }

        // After SELECT keyword or comma (column suggestions)
        if (textBeforeTrimmed.match(/\bSELECT\s+\w*$/) || textBeforeTrimmed.match(/,\s*\w*$/)) {
            const fromTable = this.findTableAfterFrom(document, position);
            if (fromTable) {
                const parts = fromTable.split('.');
                return {
                    type: 'column',
                    schema: parts.length > 1 ? parts[0] : 'public',
                    table: parts.length > 1 ? parts[1] : parts[0],
                    prefix: lastWord
                };
            }
        }

        // After WHERE, AND, OR (column suggestions)
        if (textBeforeTrimmed.match(/\b(WHERE|AND|OR)\s+\w*$/)) {
            const fromTable = this.findTableAfterFrom(document, position);
            if (fromTable) {
                const parts = fromTable.split('.');
                return {
                    type: 'column',
                    schema: parts.length > 1 ? parts[0] : undefined,
                    table: parts.length > 1 ? parts[1] : parts[0],
                    prefix: lastWord
                };
            }
        }

        // Function call pattern
        if (textBeforeTrimmed.match(/\b(COUNT|SUM|AVG|MIN|MAX|STRING_AGG|CONCAT)\s*\(?\w*$/)) {
            return {
                type: 'function',
                prefix: lastWord
            };
        }

        // Default: SQL keywords
        return {
            type: 'keyword',
            prefix: lastWord
        };
    }

    /**
     * Suggest schema names
     */
    private async suggestSchemas(prefix?: string): Promise<vscode.CompletionItem[]> {
        const items: vscode.CompletionItem[] = [];

        for (const schema of this.cachedSchemas) {
            if (!prefix || schema.toLowerCase().startsWith(prefix.toLowerCase())) {
                const item = new vscode.CompletionItem(schema, vscode.CompletionItemKind.Module);
                item.detail = 'Schema';
                item.sortText = `0_${schema}`;
                items.push(item);
            }
        }

        return items;
    }

    /**
     * Suggest table names
     */
    private async suggestTables(schema?: string, prefix?: string): Promise<vscode.CompletionItem[]> {
        const items: vscode.CompletionItem[] = [];

        try {
            // Use cached tables if available
            let tables = schema ? this.cachedTables.get(schema) : undefined;

            // If not cached, fetch from MCP
            if (!tables && schema) {
                const result = await this.mcpClient.callTool('search_tables', {
                    schema,
                    pattern: prefix ? `${prefix}*` : '*'
                });
                const fetchedTables = result.tables || [];
                this.cachedTables.set(schema, fetchedTables);
                tables = fetchedTables;
            }

            if (tables && Array.isArray(tables) && tables.length > 0) {
                for (const table of tables) {
                    const tableName = typeof table === 'string' ? table : table.name;
                    if (!prefix || tableName.toLowerCase().includes(prefix.toLowerCase())) {
                        const item = new vscode.CompletionItem(tableName, vscode.CompletionItemKind.Class);
                        item.detail = `Table in ${schema}`;
                        
                        // Add table metadata if available
                        if (typeof table === 'object' && table.row_count) {
                            item.documentation = new vscode.MarkdownString(
                                `**${schema}.${tableName}**\n\n` +
                                `Rows: ${table.row_count.toLocaleString()}\n\n` +
                                `Columns: ${table.column_count || 'N/A'}`
                            );
                        }
                        
                        item.sortText = `1_${tableName}`;
                        items.push(item);
                    }
                }
            }
        } catch (error) {
            console.error('Error suggesting tables:', error);
        }

        return items;
    }

    /**
     * Suggest column names
     */
    private async suggestColumns(
        schema?: string,
        table?: string,
        prefix?: string
    ): Promise<vscode.CompletionItem[]> {
        const items: vscode.CompletionItem[] = [];

        if (!schema || !table) {
            return items;
        }

        try {
            // Check cache
            const cacheKey = `${schema}.${table}`;
            let columns = this.cachedColumns.get(cacheKey);

            // Fetch from MCP if not cached
            if (!columns) {
                const result = await this.mcpClient.callTool('get_table_info', {
                    schema,
                    table
                });
                const fetchedColumns = result.columns || [];
                this.cachedColumns.set(cacheKey, fetchedColumns);
                columns = fetchedColumns;
            }

            if (columns && Array.isArray(columns) && columns.length > 0) {
                for (const column of columns) {
                const columnName = typeof column === 'string' ? column : column.name;
                if (!prefix || columnName.toLowerCase().startsWith(prefix.toLowerCase())) {
                    const item = new vscode.CompletionItem(columnName, vscode.CompletionItemKind.Field);
                    
                    // Add type information
                    if (typeof column === 'object' && column.type) {
                        item.detail = column.type;
                        item.documentation = new vscode.MarkdownString(
                            `**${columnName}** (${column.type})\n\n` +
                            `Table: \`${schema}.${table}\`\n\n` +
                            `Nullable: ${column.nullable ? 'Yes' : 'No'}`
                        );
                    } else {
                        item.detail = `Column in ${schema}.${table}`;
                    }
                    
                    item.sortText = `2_${columnName}`;
                    items.push(item);
                }
            }
            }
        } catch (error) {
            console.error('Error suggesting columns:', error);
        }

        return items;
    }

    /**
     * Suggest JOIN targets based on foreign keys
     */
    private async suggestJoins(schema?: string, table?: string): Promise<vscode.CompletionItem[]> {
        const items: vscode.CompletionItem[] = [];

        if (!schema || !table) {
            return items;
        }

        try {
            // Get foreign key relationships
            const result = await this.mcpClient.callTool('find_relationships', {
                table: `${schema}.${table}`
            });

            const relationships = result.relationships || [];

            for (const rel of relationships) {
                const targetTable = `${rel.referenced_schema}.${rel.referenced_table}`;
                const item = new vscode.CompletionItem(targetTable, vscode.CompletionItemKind.Reference);
                item.detail = `JOIN suggestion`;
                item.documentation = new vscode.MarkdownString(
                    `**Suggested JOIN**\n\n` +
                    `\`\`\`sql\n` +
                    `JOIN ${targetTable}\n` +
                    `  ON ${schema}.${table}.${rel.column} = ${targetTable}.${rel.referenced_column}\n` +
                    `\`\`\`\n\n` +
                    `Based on foreign key relationship`
                );
                
                // Create insert text with full JOIN clause
                item.insertText = new vscode.SnippetString(
                    `${targetTable}\n  ON ${schema}.${table}.${rel.column} = ${targetTable}.${rel.referenced_column}`
                );
                
                item.sortText = `0_${targetTable}`;
                items.push(item);
            }
        } catch (error) {
            console.error('Error suggesting joins:', error);
        }

        return items;
    }

    /**
     * Suggest SQL functions
     */
    private suggestFunctions(prefix?: string): vscode.CompletionItem[] {
        const functions = [
            { name: 'COUNT', detail: 'COUNT(*) or COUNT(column)', doc: 'Count rows or non-null values' },
            { name: 'SUM', detail: 'SUM(column)', doc: 'Sum numeric values' },
            { name: 'AVG', detail: 'AVG(column)', doc: 'Average of numeric values' },
            { name: 'MIN', detail: 'MIN(column)', doc: 'Minimum value' },
            { name: 'MAX', detail: 'MAX(column)', doc: 'Maximum value' },
            { name: 'STRING_AGG', detail: 'STRING_AGG(column, delimiter)', doc: 'Concatenate strings with delimiter' },
            { name: 'CONCAT', detail: 'CONCAT(str1, str2, ...)', doc: 'Concatenate strings' },
            { name: 'COALESCE', detail: 'COALESCE(val1, val2, ...)', doc: 'Return first non-null value' },
            { name: 'CAST', detail: 'CAST(value AS type)', doc: 'Convert value to specified type' },
            { name: 'CASE', detail: 'CASE WHEN ... THEN ... END', doc: 'Conditional expression' },
            { name: 'UPPER', detail: 'UPPER(string)', doc: 'Convert to uppercase' },
            { name: 'LOWER', detail: 'LOWER(string)', doc: 'Convert to lowercase' },
            { name: 'TRIM', detail: 'TRIM(string)', doc: 'Remove leading/trailing whitespace' },
            { name: 'LENGTH', detail: 'LENGTH(string)', doc: 'Length of string' },
            { name: 'SUBSTRING', detail: 'SUBSTRING(string, start, length)', doc: 'Extract substring' },
            { name: 'NOW', detail: 'NOW()', doc: 'Current timestamp' },
            { name: 'DATE_TRUNC', detail: 'DATE_TRUNC(unit, timestamp)', doc: 'Truncate timestamp to unit' },
            { name: 'EXTRACT', detail: 'EXTRACT(field FROM timestamp)', doc: 'Extract date/time field' },
        ];

        const items: vscode.CompletionItem[] = [];

        for (const func of functions) {
            if (!prefix || func.name.toLowerCase().startsWith(prefix.toLowerCase())) {
                const item = new vscode.CompletionItem(func.name, vscode.CompletionItemKind.Function);
                item.detail = func.detail;
                item.documentation = new vscode.MarkdownString(func.doc);
                item.insertText = new vscode.SnippetString(`${func.name}($1)$0`);
                item.sortText = `3_${func.name}`;
                items.push(item);
            }
        }

        return items;
    }

    /**
     * Suggest SQL keywords
     */
    private suggestKeywords(prefix?: string): vscode.CompletionItem[] {
        const keywords = [
            'SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN', 'OUTER JOIN',
            'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT', 'OFFSET',
            'INSERT INTO', 'UPDATE', 'DELETE', 'CREATE TABLE', 'ALTER TABLE', 'DROP TABLE',
            'AS', 'DISTINCT', 'UNION', 'UNION ALL', 'INTERSECT', 'EXCEPT',
            'AND', 'OR', 'NOT', 'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'ILIKE',
            'IS NULL', 'IS NOT NULL',
            'ASC', 'DESC',
            'BEGIN', 'COMMIT', 'ROLLBACK',
            'WITH', 'RECURSIVE'
        ];

        const items: vscode.CompletionItem[] = [];

        for (const keyword of keywords) {
            if (!prefix || keyword.toLowerCase().startsWith(prefix.toLowerCase())) {
                const item = new vscode.CompletionItem(keyword, vscode.CompletionItemKind.Keyword);
                item.detail = 'SQL Keyword';
                item.sortText = `4_${keyword}`;
                items.push(item);
            }
        }

        return items;
    }

    /**
     * Utility: Get last word from text
     */
    private getLastWord(text: string): string {
        const words = text.trim().split(/\s+/);
        return words[words.length - 1] || '';
    }

    /**
     * Utility: Get second last word from text
     */
    private getSecondLastWord(text: string): string {
        const words = text.trim().split(/\s+/);
        return words.length > 1 ? words[words.length - 2] : '';
    }

    /**
     * Find the table referenced in FROM clause
     */
    private findTableAfterFrom(document: vscode.TextDocument, position: vscode.Position): string | null {
        // Look backwards from current position to find FROM clause
        const text = document.getText(new vscode.Range(
            new vscode.Position(Math.max(0, position.line - 10), 0),
            position
        ));

        const fromMatch = text.match(/FROM\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)/i);
        if (fromMatch) {
            return fromMatch[1];
        }

        return null;
    }

    /**
     * Public method to refresh cache on demand
     */
    public async refresh(): Promise<void> {
        await this.refreshCache();
    }
}

