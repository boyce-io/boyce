/**
 * SQL Editor Provider
 * Enhanced SQL editing features with query execution
 */

import * as vscode from 'vscode';
import { MCPClient } from '../mcp/client';
import { ResultsPanel, QueryResult } from '../panels/resultsPanel';
import { ErrorHandler } from '../utils/errorHandler';
import { TelemetryLogger } from '../utils/telemetry';

export class SQLEditorProvider {
    private outputChannel: vscode.OutputChannel;
    private resultsPanel: ResultsPanel | undefined;
    
    constructor(
        private mcpClient: MCPClient,
        private context: vscode.ExtensionContext
    ) {
        this.outputChannel = vscode.window.createOutputChannel('DataShark Query Results');
    }

    /**
     * Execute current query in active SQL editor
     */
    async executeCurrentQuery() {
        const editor = vscode.window.activeTextEditor;
        
        if (!editor) {
            vscode.window.showErrorMessage('No active editor');
            return;
        }

        // Get selected text or entire document
        let sql: string;
        const selection = editor.selection;
        
        if (!selection.isEmpty) {
            sql = editor.document.getText(selection);
        } else {
            sql = editor.document.getText();
        }

        if (!sql.trim()) {
            vscode.window.showWarningMessage('No SQL query to execute');
            return;
        }

        await this.executeQuery(sql);
    }

    /**
     * Execute SQL query and show results
     */
    async executeQuery(sql: string) {
        const start = Date.now();
        
        try {
            // Show progress
            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'Executing query...',
                cancellable: false
            }, async (progress) => {
                const result = await this.mcpClient.executeQuery(sql, 100);
                const duration = Date.now() - start;

                // Log telemetry
                TelemetryLogger.getInstance().logQueryExecution(
                    duration,
                    result.row_count || 0,
                    sql.length
                );

                if (result.error || result.blocked) {
                    // Use error handler for friendly message
                    const friendlyError = ErrorHandler.handleError(result.error, 'executing query');
                    const formattedError = ErrorHandler.formatForDisplay(friendlyError);
                    
                    vscode.window.showErrorMessage(`Query failed: ${friendlyError.title}`);
                    this.showErrorInOutput(sql, formattedError, duration);
                    return;
                }

                // Show success
                vscode.window.showInformationMessage(
                    `✅ Query executed: ${result.row_count} rows in ${duration}ms`
                );

                // Display results
                await this.showResults(result, sql, duration);
            });
        } catch (error) {
            const duration = Date.now() - start;
            
            // Use error handler for friendly message
            const friendlyError = ErrorHandler.handleError(error, 'executing query');
            const formattedError = ErrorHandler.formatForDisplay(friendlyError);
            
            vscode.window.showErrorMessage(`Query failed: ${friendlyError.title}`);
            this.showErrorInOutput(sql, formattedError, duration);
        }
    }

    /**
     * Show query results in rich panel
     */
    private async showResults(result: any, sql: string, duration: number) {
        // Initialize results panel if needed
        if (!this.resultsPanel) {
            this.resultsPanel = ResultsPanel.getInstance(this.context);
        }

        // Convert to QueryResult format
        // Handle both execute_query_safe and run_query formats
        const queryResult: QueryResult = {
            query: sql,
            columns: result.columns || result.schema || [],
            rows: result.rows || result.results || [],
            rowCount: result.row_count || result.count || 0,
            duration,
            timestamp: new Date(),
            // Include reasoning trace if available
            reasoningTraceId: result.reasoning_trace_id,
            explanation: result.explanation
        };

        // Show in panel
        this.resultsPanel.showResults(queryResult);
    }

    /**
     * Show error in results panel
     */
    private showErrorInOutput(sql: string, error: string, duration: number) {
        // Initialize results panel if needed
        if (!this.resultsPanel) {
            this.resultsPanel = ResultsPanel.getInstance(this.context);
        }

        // Show error in panel
        const errorResult: QueryResult = {
            query: sql,
            columns: [],
            rows: [],
            rowCount: 0,
            duration,
            timestamp: new Date(),
            error
        };

        this.resultsPanel.showResults(errorResult);
    }

    /**
     * Export results to CSV
     */
    async exportToCSV(result: any) {
        if (!result.rows || result.rows.length === 0) {
            vscode.window.showWarningMessage('No data to export');
            return;
        }

        const columns = result.columns || Object.keys(result.rows[0]);
        
        // Build CSV
        let csv = columns.join(',') + '\n';
        result.rows.forEach((row: any) => {
            const values = columns.map((col: string) => {
                const val = row[col];
                if (val === null || val === undefined) return '';
                // Escape commas and quotes
                const str = String(val);
                if (str.includes(',') || str.includes('"')) {
                    return `"${str.replace(/"/g, '""')}"`;
                }
                return str;
            });
            csv += values.join(',') + '\n';
        });

        // Save file
        const uri = await vscode.window.showSaveDialog({
            filters: { 'CSV Files': ['csv'] },
            defaultUri: vscode.Uri.file('query_results.csv')
        });

        if (uri) {
            await vscode.workspace.fs.writeFile(uri, Buffer.from(csv, 'utf8'));
            vscode.window.showInformationMessage(`Exported to ${uri.fsPath}`);
        }
    }

    /**
     * Format SQL query
     */
    async formatQuery() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        const sql = editor.document.getText();
        
        // Simple formatting (basic)
        const formatted = this.simpleFormat(sql);
        
        const edit = new vscode.WorkspaceEdit();
        const fullRange = new vscode.Range(
            editor.document.positionAt(0),
            editor.document.positionAt(sql.length)
        );
        edit.replace(editor.document.uri, fullRange, formatted);
        
        await vscode.workspace.applyEdit(edit);
        vscode.window.showInformationMessage('SQL formatted');
    }

    /**
     * Simple SQL formatter
     */
    private simpleFormat(sql: string): string {
        // Basic formatting: uppercase keywords, indent
        const keywords = ['SELECT', 'FROM', 'WHERE', 'JOIN', 'LEFT JOIN', 'RIGHT JOIN', 
                         'INNER JOIN', 'ON', 'GROUP BY', 'ORDER BY', 'HAVING', 'LIMIT'];
        
        let formatted = sql;
        keywords.forEach(keyword => {
            const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
            formatted = formatted.replace(regex, keyword);
        });
        
        return formatted;
    }

    dispose() {
        this.outputChannel.dispose();
        if (this.resultsPanel) {
            this.resultsPanel.dispose();
        }
    }
}

