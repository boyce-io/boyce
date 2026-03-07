/**
 * Query Console Panel
 * 
 * Interactive SQL/DSL/NL query editor with autocomplete and execution.
 */

import * as vscode from 'vscode';
import { MCPClient } from '../mcp/client';
import { queryStore } from '../state/queryStore';
import { ResultsPanel, QueryResult } from './resultsPanel';
import { TelemetryLogger } from '../utils/telemetry';
import { QueryHistoryManager } from '../utils/queryHistory';
import { InstanceAPI } from '../utils/instanceApi';

export class QueryConsolePanel {
    private static instance: QueryConsolePanel | undefined;
    private panel: vscode.WebviewPanel | undefined;
    private disposables: vscode.Disposable[] = [];
    private autocompleteCache: {
        schemas: string[];
        tables: Map<string, string[]>;
        columns: Map<string, string[]>;
        concepts: Array<{ name: string; description: string }>;
        instanceName: string | null;
    } = {
        schemas: [],
        tables: new Map(),
        columns: new Map(),
        concepts: [],
        instanceName: null
    };

    private queryHistoryManager: QueryHistoryManager;
    private instanceApi: InstanceAPI;

    private constructor(
        private context: vscode.ExtensionContext,
        private mcpClient: MCPClient
    ) {
        this.queryHistoryManager = QueryHistoryManager.getInstance();
        this.instanceApi = new InstanceAPI(mcpClient);
        this.refreshAutocompleteCache();
        this.initializeHistory();
    }

    /**
     * Initialize query history manager
     */
    private async initializeHistory(): Promise<void> {
        await this.queryHistoryManager.initialize(this.instanceApi);
    }

    /**
     * Get or create the singleton instance
     */
    public static getInstance(
        context: vscode.ExtensionContext,
        mcpClient: MCPClient
    ): QueryConsolePanel {
        if (!QueryConsolePanel.instance) {
            QueryConsolePanel.instance = new QueryConsolePanel(context, mcpClient);
        }
        return QueryConsolePanel.instance;
    }

    /**
     * Show or create the query console panel
     */
    public show(): void {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.One);
            return;
        }

        // Create webview panel
        this.panel = vscode.window.createWebviewPanel(
            'datasharkQueryConsole',
            'DataShark Query Console',
            vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.file(this.context.extensionPath)
                ]
            }
        );

        // Set initial content
        this.panel.webview.html = this.getWebviewContent();

        // Handle messages from webview
        this.panel.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            null,
            this.disposables
        );

        // Handle panel disposal
        this.panel.onDidDispose(() => {
            this.panel = undefined;
        }, null, this.disposables);

        // Subscribe to query store changes
        const unsubscribe = queryStore.subscribe(state => {
            if (this.panel) {
                this.panel.webview.postMessage({
                    command: 'stateUpdate',
                    state
                });
            }
        });
        this.disposables.push({ dispose: unsubscribe });
    }

    /**
     * Handle messages from webview
     */
    private async handleMessage(message: any): Promise<void> {
        switch (message.command) {
            case 'executeQuery':
                await this.executeQuery(message.query, message.queryType || 'sql');
                break;
            case 'clearQuery':
                queryStore.clear();
                break;
            case 'saveQuery':
                await this.saveQuery(message.query);
                break;
            case 'requestAutocomplete':
                await this.handleAutocompleteRequest(message.prefix, message.position);
                break;
            case 'openHistory':
                await this.showHistory();
                break;
            case 'loadQueryFromHistory':
                await this.loadQueryFromHistory(message.queryId);
                break;
            case 'inspectTraceFromHistory':
                await this.inspectTraceFromHistory(message.queryId);
                break;
        }
    }

    /**
     * Handle autocomplete request from webview
     */
    private async handleAutocompleteRequest(prefix: string, position: number): Promise<void> {
        try {
            const suggestions = await this.getAutocompleteSuggestions(prefix);
            
            if (this.panel) {
                this.panel.webview.postMessage({
                    command: 'autocompleteSuggestions',
                    suggestions,
                    prefix,
                    position
                });
            }
        } catch (error) {
            console.error('Error fetching autocomplete:', error);
        }
    }

    /**
     * Get autocomplete suggestions for prefix
     */
    private async getAutocompleteSuggestions(prefix: string): Promise<Array<{
        text: string;
        type: 'table' | 'column' | 'concept' | 'schema';
        description?: string;
        icon?: string;
    }>> {
        const suggestions: Array<{
            text: string;
            type: 'table' | 'column' | 'concept' | 'schema';
            description?: string;
            icon?: string;
        }> = [];

        const prefixLower = prefix.toLowerCase();

        // Refresh cache if needed
        await this.refreshAutocompleteCache();

        // Schema suggestions
        for (const schema of this.autocompleteCache.schemas) {
            if (prefixLower === '' || schema.toLowerCase().includes(prefixLower)) {
                suggestions.push({
                    text: schema,
                    type: 'schema',
                    description: 'Schema',
                    icon: '📁'
                });
            }
        }

        // Table suggestions (from all schemas)
        for (const [schema, tables] of this.autocompleteCache.tables.entries()) {
            for (const table of tables) {
                if (prefixLower === '' || table.toLowerCase().includes(prefixLower)) {
                    suggestions.push({
                        text: `${schema}.${table}`,
                        type: 'table',
                        description: `Table in ${schema}`,
                        icon: '📊'
                    });
                }
            }
        }

        // Column suggestions (from all tables)
        for (const [tableKey, columns] of this.autocompleteCache.columns.entries()) {
            for (const column of columns) {
                if (prefixLower === '' || column.toLowerCase().includes(prefixLower)) {
                    suggestions.push({
                        text: column,
                        type: 'column',
                        description: `Column in ${tableKey}`,
                        icon: '📋'
                    });
                }
            }
        }

        // Business concept suggestions
        for (const concept of this.autocompleteCache.concepts) {
            if (prefixLower === '' || concept.name.toLowerCase().includes(prefixLower)) {
                suggestions.push({
                    text: concept.name,
                    type: 'concept',
                    description: concept.description || 'Business concept',
                    icon: '💡'
                });
            }
        }

        // Sort: concepts first, then schemas, tables, columns
        suggestions.sort((a, b) => {
            const order = { concept: 0, schema: 1, table: 2, column: 3 };
            return (order[a.type] || 99) - (order[b.type] || 99);
        });

        return suggestions.slice(0, 20); // Limit to 20 suggestions
    }

    /**
     * Refresh autocomplete cache from MCP
     */
    private async refreshAutocompleteCache(): Promise<void> {
        try {
            // Get active instance name
            const { InstanceAPI } = await import('../utils/instanceApi');
            const instanceApi = new InstanceAPI(this.mcpClient);
            const activeInstance = await instanceApi.getActiveInstance();
            const instanceName = activeInstance?.name || null;

            // Only refresh if instance changed
            if (instanceName === this.autocompleteCache.instanceName && this.autocompleteCache.schemas.length > 0) {
                return;
            }

            this.autocompleteCache.instanceName = instanceName;
            this.autocompleteCache.schemas = [];
            this.autocompleteCache.tables.clear();
            this.autocompleteCache.columns.clear();
            this.autocompleteCache.concepts = [];

            // Fetch schema tree
            try {
                const treeResult = await this.mcpClient.call('get_schema_tree', { system: 'database' });
                if (treeResult.tree?.schemas) {
                    for (const schema of treeResult.tree.schemas) {
                        this.autocompleteCache.schemas.push(schema.name);
                        
                        const tables: string[] = [];
                        for (const table of schema.tables || []) {
                            tables.push(table.name);
                            const tableKey = `${schema.name}.${table.name}`;
                            const columns = (table.columns || []).map((c: any) => c.name || c);
                            this.autocompleteCache.columns.set(tableKey, columns);
                        }
                        this.autocompleteCache.tables.set(schema.name, tables);
                    }
                }
            } catch (error) {
                console.debug('Schema tree not available:', error);
            }

            // Fetch business concepts (if MCP tool exists)
            try {
                const conceptsResult = await this.mcpClient.call('search_concepts', { term: '' });
                if (conceptsResult.concepts) {
                    this.autocompleteCache.concepts = conceptsResult.concepts.map((c: any) => ({
                        name: c.name,
                        description: c.description || ''
                    }));
                }
            } catch (error) {
                // Concept search not available, skip
                console.debug('Concept search not available:', error);
            }
        } catch (error) {
            console.error('Error refreshing autocomplete cache:', error);
        }
    }

    /**
     * Execute query via MCP
     */
    private async executeQuery(query: string, queryType: string): Promise<void> {
        const startTime = Date.now();
        
        try {
            queryStore.setQueryText(query);
            queryStore.setQueryStatus('running');

            // Log query start
            TelemetryLogger.getInstance().logQueryStart(queryType, query.length);

            // Call MCP tool
            const result = await this.mcpClient.call('run_query', {
                query,
                query_type: queryType,
                limit: 100
            });

            const duration = Date.now() - startTime;

            // Log telemetry
            TelemetryLogger.getInstance().logQueryExecution(
                duration,
                result.count || 0,
                query.length
            );

            if (result.error || !result.success) {
                queryStore.setError(result.error || 'Query failed', duration);
                
                // Log query error
                TelemetryLogger.getInstance().logQueryError(duration, result.error || 'Query failed');
                
                // Show error in ResultsPanel
                const resultsPanel = ResultsPanel.getInstance(this.context);
                const errorResult: QueryResult = {
                    query,
                    columns: [],
                    rows: [],
                    rowCount: 0,
                    duration,
                    timestamp: new Date(),
                    error: result.error || 'Query failed'
                };
                resultsPanel.showResults(errorResult);
                
                return;
            }

            // Log query success
            const traceLength = result.trace_summary?.total_steps || 0;
            TelemetryLogger.getInstance().logQuerySuccess(duration, result.count || 0, traceLength);

            // Update store with results
            queryStore.setResults(
                result.results || [],
                result.schema || [],
                result.latency_ms || duration,
                result.reasoning_trace_id
            );

            // Show results in ResultsPanel
            const resultsPanel = ResultsPanel.getInstance(this.context);
            const queryResult: QueryResult = {
                query,
                columns: result.schema || [],
                rows: result.results || [],
                rowCount: result.count || 0,
                duration: result.latency_ms || duration,
                timestamp: new Date(),
                reasoningTraceId: result.reasoning_trace_id,
                explanation: result.explanation
            };
            resultsPanel.showResults(queryResult);

            // Save to query history
            this.queryHistoryManager.addQuery({
                query,
                queryType: queryType as 'sql' | 'dsl' | 'nl',
                resultCount: result.count || 0,
                duration: result.latency_ms || duration,
                success: true,
                reasoningTraceId: result.reasoning_trace_id,
                explanation: result.explanation
            });

            vscode.window.showInformationMessage(
                `✅ Query executed: ${result.count || 0} rows in ${duration}ms`
            );

        } catch (error: any) {
            const duration = Date.now() - startTime;
            const errorMsg = error.message || String(error);
            
            // Save failed query to history
            this.queryHistoryManager.addQuery({
                query,
                queryType: queryType as 'sql' | 'dsl' | 'nl',
                resultCount: 0,
                duration,
                success: false,
                error: errorMsg
            });
            
            queryStore.setError(errorMsg, duration);
            
            vscode.window.showErrorMessage(`Query failed: ${errorMsg}`);
        }
    }

    /**
     * Show query history
     */
    private async showHistory(): Promise<void> {
        const history = this.queryHistoryManager.getRecent(50);
        
        if (history.length === 0) {
            vscode.window.showInformationMessage('No query history available');
            return;
        }

        // Create quick pick items
        const items = history.map(entry => ({
            label: entry.query.substring(0, 60) + (entry.query.length > 60 ? '...' : ''),
            description: `${entry.queryType.toUpperCase()} • ${entry.resultCount} rows • ${entry.duration}ms • ${new Date(entry.timestamp).toLocaleString()}`,
            detail: entry.success ? '✅ Success' : `❌ Error: ${entry.error}`,
            queryId: entry.id,
            entry
        }));

        const selected = await vscode.window.showQuickPick(items, {
            placeHolder: 'Select a query to reopen',
            matchOnDescription: true,
            matchOnDetail: true
        });

        if (selected) {
            // Log telemetry
            TelemetryLogger.getInstance().logQueryHistoryOpened(selected.queryId);

            // Load query into editor
            await this.loadQueryFromHistory(selected.queryId);
        }
    }

    /**
     * Load query from history into editor
     */
    private async loadQueryFromHistory(queryId: string): Promise<void> {
        const entry = this.queryHistoryManager.getQuery(queryId);
        if (!entry) {
            vscode.window.showErrorMessage('Query not found in history');
            return;
        }

        // Send query to webview
        if (this.panel) {
            this.panel.webview.postMessage({
                command: 'loadQuery',
                query: entry.query,
                queryType: entry.queryType
            });
        }

        // Update query store
        queryStore.setQueryText(entry.query);
    }

    /**
     * Inspect trace from history
     */
    private async inspectTraceFromHistory(queryId: string): Promise<void> {
        const entry = this.queryHistoryManager.getQuery(queryId);
        if (!entry) {
            vscode.window.showErrorMessage('Query not found in history');
            return;
        }

        if (!entry.reasoningTraceId) {
            vscode.window.showWarningMessage('No reasoning trace available for this query');
            return;
        }

        // Log telemetry
        TelemetryLogger.getInstance().logTraceReinspected(queryId, entry.reasoningTraceId);

        // Load trace in ResultsPanel
        const resultsPanel = ResultsPanel.getInstance(this.context);
        
        // Create a mock result to display trace
        const mockResult: QueryResult = {
            query: entry.query,
            columns: [],
            rows: [],
            rowCount: entry.resultCount,
            duration: entry.duration,
            timestamp: new Date(entry.timestamp),
            reasoningTraceId: entry.reasoningTraceId,
            explanation: entry.explanation
        };

        resultsPanel.showResults(mockResult);
        
        // Automatically open trace viewer
        if (this.panel && entry.reasoningTraceId) {
            // Wait a bit for panel to render, then trigger trace view
            setTimeout(() => {
                this.panel?.webview.postMessage({
                    command: 'showTrace',
                    traceId: entry.reasoningTraceId
                });
            }, 500);
        }
    }

    /**
     * Save query to file
     */
    private async saveQuery(query: string): Promise<void> {
        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file('query.sql'),
            filters: {
                'SQL Files': ['sql'],
                'All Files': ['*']
            }
        });

        if (uri) {
            await vscode.workspace.fs.writeFile(
                uri,
                Buffer.from(query, 'utf8')
            );
            vscode.window.showInformationMessage(`Query saved to ${uri.fsPath}`);
        }
    }

    /**
     * Get webview HTML content
     */
    private getWebviewContent(): string {
        const nonce = this.getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
    <title>Query Console</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background-color: var(--vscode-editor-background);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        .toolbar {
            display: flex;
            gap: 8px;
            padding: 8px 12px;
            background-color: var(--vscode-editor-background);
            border-bottom: 1px solid var(--vscode-panel-border);
            flex-shrink: 0;
        }

        .toolbar select {
            padding: 4px 8px;
            background-color: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 2px;
        }

        .btn {
            padding: 4px 12px;
            background-color: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 2px;
            cursor: pointer;
            white-space: nowrap;
        }

        .btn:hover {
            background-color: var(--vscode-button-hoverBackground);
        }

        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .editor-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            position: relative;
        }

        #query-editor {
            flex: 1;
            width: 100%;
            padding: 12px;
            background-color: var(--vscode-editor-background);
            color: var(--vscode-editor-foreground);
            font-family: var(--vscode-editor-font-family);
            font-size: var(--vscode-editor-font-size);
            border: none;
            outline: none;
            resize: none;
            white-space: pre;
            overflow-wrap: normal;
            overflow-x: auto;
        }

        .status-bar {
            padding: 6px 12px;
            background-color: var(--vscode-statusBar-background);
            color: var(--vscode-statusBar-foreground);
            border-top: 1px solid var(--vscode-panel-border);
            font-size: 12px;
            flex-shrink: 0;
        }

        .status-info {
            display: flex;
            gap: 12px;
        }

        .status-running {
            color: var(--vscode-textLink-foreground);
        }

        .status-success {
            color: var(--vscode-testing-iconPassed);
        }

        .status-error {
            color: var(--vscode-errorForeground);
        }

        /* Autocomplete Dropdown */
        .autocomplete-dropdown {
            position: absolute;
            top: 40px;
            left: 0;
            right: 0;
            background-color: var(--vscode-dropdown-background);
            border: 1px solid var(--vscode-dropdown-border);
            border-radius: 2px;
            max-height: 200px;
            overflow-y: auto;
            z-index: 1000;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            margin: 0 12px;
        }

        .autocomplete-item {
            padding: 6px 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid var(--vscode-dropdown-border);
        }

        .autocomplete-item:hover,
        .autocomplete-item.selected {
            background-color: var(--vscode-list-hoverBackground);
        }

        .autocomplete-item-icon {
            font-size: 14px;
            width: 20px;
            text-align: center;
        }

        .autocomplete-item-text {
            flex: 1;
            font-weight: 500;
        }

        .autocomplete-item-desc {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            margin-left: auto;
        }
    </style>
</head>
<body>
    <div class="toolbar">
        <select id="query-type">
            <option value="sql">SQL</option>
            <option value="dsl">DSL</option>
            <option value="nl">Natural Language</option>
        </select>
        <button class="btn" id="run-btn" onclick="executeQuery()">▶ Run</button>
        <button class="btn" onclick="clearQuery()">Clear</button>
        <button class="btn" onclick="saveQuery()">Save</button>
        <button class="btn" onclick="showHistory()">📜 History</button>
    </div>

    <div class="editor-container">
        <textarea 
            id="query-editor" 
            placeholder="Enter your query here...&#10;Press Ctrl+Enter (Cmd+Enter on Mac) to execute&#10;Type to see autocomplete suggestions"
            spellcheck="false"
        ></textarea>
    </div>

    <div class="status-bar">
        <div class="status-info" id="status-info">
            <span>Ready</span>
        </div>
    </div>

    <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();
        let queryState = {
            queryText: '',
            queryStatus: 'idle',
            latency: 0,
            error: null
        };

        // Listen for state updates
        window.addEventListener('message', event => {
            const message = event.data;
            if (message.command === 'stateUpdate') {
                queryState = message.state;
                updateUI();
            }
        });

        // Update UI based on state
        function updateUI() {
            const editor = document.getElementById('query-editor');
            const runBtn = document.getElementById('run-btn');
            const statusInfo = document.getElementById('status-info');

            if (editor && queryState.queryText) {
                editor.value = queryState.queryText;
            }

            if (runBtn) {
                runBtn.disabled = queryState.queryStatus === 'running';
                runBtn.textContent = queryState.queryStatus === 'running' ? '⏳ Running...' : '▶ Run';
            }

            if (statusInfo) {
                let statusText = 'Ready';
                let statusClass = '';

                if (queryState.queryStatus === 'running') {
                    statusText = '⏳ Running query...';
                    statusClass = 'status-running';
                } else if (queryState.queryStatus === 'success') {
                    statusText = \`✅ Query completed in \${queryState.latency}ms\`;
                    statusClass = 'status-success';
                } else if (queryState.queryStatus === 'error') {
                    statusText = \`❌ Error: \${queryState.error}\`;
                    statusClass = 'status-error';
                }

                statusInfo.innerHTML = \`<span class="\${statusClass}">\${statusText}</span>\`;
            }
        }

        // Execute query
        function executeQuery() {
            const editor = document.getElementById('query-editor');
            const queryType = document.getElementById('query-type').value;
            
            if (!editor || !editor.value.trim()) {
                return;
            }

            vscode.postMessage({
                command: 'executeQuery',
                query: editor.value,
                queryType: queryType
            });
        }

        // Clear query
        function clearQuery() {
            const editor = document.getElementById('query-editor');
            if (editor) {
                editor.value = '';
            }
            vscode.postMessage({ command: 'clearQuery' });
        }

        // Save query
        function saveQuery() {
            const editor = document.getElementById('query-editor');
            if (!editor || !editor.value.trim()) {
                return;
            }
            vscode.postMessage({
                command: 'saveQuery',
                query: editor.value
            });
        }

        // Show history
        function showHistory() {
            vscode.postMessage({ command: 'openHistory' });
        }

        // Listen for load query command
        window.addEventListener('message', event => {
            const message = event.data;
            if (message.command === 'loadQuery') {
                const editor = document.getElementById('query-editor');
                const queryType = document.getElementById('query-type');
                if (editor) {
                    editor.value = message.query;
                }
                if (queryType && message.queryType) {
                    queryType.value = message.queryType;
                }
            }
            if (message.command === 'showTrace') {
                // Trigger trace view in results panel
                // This will be handled by the ResultsPanel
            }
        });

        // Autocomplete state
        let autocompleteSuggestions = [];
        let selectedIndex = -1;
        let currentPrefix = '';
        let autocompletePosition = 0;

        // Autocomplete dropdown
        const autocompleteDropdown = document.getElementById('autocomplete-dropdown');
        const editor = document.getElementById('query-editor');

        // Show autocomplete
        function showAutocomplete(suggestions, prefix, position) {
            autocompleteSuggestions = suggestions;
            selectedIndex = -1;
            currentPrefix = prefix;
            autocompletePosition = position;

            if (!autocompleteDropdown || suggestions.length === 0) {
                hideAutocomplete();
                return;
            }

            autocompleteDropdown.innerHTML = '';
            suggestions.forEach((sug, idx) => {
                const item = document.createElement('div');
                item.className = 'autocomplete-item';
                item.innerHTML = \`
                    <span class="autocomplete-item-icon">\${sug.icon || '•'}</span>
                    <span class="autocomplete-item-text">\${escapeHtml(sug.text)}</span>
                    <span class="autocomplete-item-desc">\${escapeHtml(sug.description || '')}</span>
                \`;
                item.onclick = () => insertSuggestion(sug.text);
                autocompleteDropdown.appendChild(item);
            });

            // Position dropdown (relative to editor container)
            autocompleteDropdown.style.display = 'block';
        }

        // Hide autocomplete
        function hideAutocomplete() {
            if (autocompleteDropdown) {
                autocompleteDropdown.style.display = 'none';
            }
            selectedIndex = -1;
        }

        // Insert suggestion
        function insertSuggestion(text) {
            if (!editor) return;
            
            const value = editor.value;
            const before = value.substring(0, autocompletePosition - currentPrefix.length);
            const after = value.substring(autocompletePosition);
            editor.value = before + text + after;
            editor.focus();
            editor.setSelectionRange(before.length + text.length, before.length + text.length);
            
            hideAutocomplete();
        }

        // Handle autocomplete typing
        if (editor) {
            let autocompleteTimeout;
            editor.addEventListener('input', (e) => {
                clearTimeout(autocompleteTimeout);
                
                const value = editor.value;
                const cursorPos = editor.selectionStart;
                
                // Extract word at cursor
                const before = value.substring(0, cursorPos);
                const match = before.match(/(\\w+)$/);
                const prefix = match ? match[1] : '';
                
                if (prefix.length >= 2) {
                    autocompleteTimeout = setTimeout(() => {
                        vscode.postMessage({
                            command: 'requestAutocomplete',
                            prefix: prefix,
                            position: cursorPos
                        });
                    }, 300); // Debounce 300ms
                } else {
                    hideAutocomplete();
                }
            });

            editor.addEventListener('blur', () => {
                setTimeout(hideAutocomplete, 200); // Delay to allow clicks
            });

            // Keyboard navigation
            editor.addEventListener('keydown', (e) => {
                if (autocompleteSuggestions.length === 0) return;

                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, autocompleteSuggestions.length - 1);
                    updateAutocompleteSelection();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, -1);
                    updateAutocompleteSelection();
                } else if (e.key === 'Enter' && selectedIndex >= 0) {
                    e.preventDefault();
                    insertSuggestion(autocompleteSuggestions[selectedIndex].text);
                } else if (e.key === 'Escape') {
                    hideAutocomplete();
                }
            });
        }

        // Update autocomplete selection
        function updateAutocompleteSelection() {
            const items = autocompleteDropdown?.querySelectorAll('.autocomplete-item');
            if (!items) return;
            
            items.forEach((item, idx) => {
                item.classList.toggle('selected', idx === selectedIndex);
            });
        }

        // Listen for autocomplete suggestions
        window.addEventListener('message', event => {
            const message = event.data;
            if (message.command === 'autocompleteSuggestions') {
                showAutocomplete(message.suggestions, message.prefix, message.position);
            }
        });

        // Escape HTML
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
            const modifier = isMac ? e.metaKey : e.ctrlKey;

            if (modifier && e.key === 'Enter' && autocompleteSuggestions.length === 0) {
                e.preventDefault();
                executeQuery();
            }
        });

        // Initialize
        updateUI();
    </script>
</body>
</html>`;
    }

    /**
     * Generate nonce for CSP
     */
    private getNonce(): string {
        let text = '';
        const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
        for (let i = 0; i < 32; i++) {
            text += possible.charAt(Math.floor(Math.random() * possible.length));
        }
        return text;
    }

    /**
     * Dispose resources
     */
    public dispose(): void {
        this.disposables.forEach(d => d.dispose());
        if (this.panel) {
            this.panel.dispose();
        }
        this.panel = undefined;
        QueryConsolePanel.instance = undefined;
    }
}

