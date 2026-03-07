/**
 * DataShark Results Panel
 * 
 * Rich webview-based results viewer with:
 * - Sortable columns
 * - Client-side filtering
 * - Multiple query tabs
 * - Export to CSV, JSON, Excel
 * - Copy cells/rows
 * - Pagination
 */

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';

export interface QueryResult {
    query: string;
    columns: string[];
    rows: any[][];
    rowCount: number;
    duration: number;
    timestamp: Date;
    error?: string;
    reasoningTraceId?: string;
    explanation?: string;
}

export interface ResultTab {
    id: string;
    title: string;
    result: QueryResult;
    active: boolean;
}

export class ResultsPanel {
    private static instance: ResultsPanel | undefined;
    private panel: vscode.WebviewPanel | undefined;
    private tabs: ResultTab[] = [];
    private activeTabId: string | undefined;
    private nextTabId = 1;

    private constructor(private context: vscode.ExtensionContext) {}

    /**
     * Get or create the singleton instance
     */
    public static getInstance(context: vscode.ExtensionContext): ResultsPanel {
        if (!ResultsPanel.instance) {
            ResultsPanel.instance = new ResultsPanel(context);
        }
        return ResultsPanel.instance;
    }

    /**
     * Show results in a new or existing tab
     */
    public showResults(result: QueryResult): void {
        // Create new tab
        const tab: ResultTab = {
            id: `tab-${this.nextTabId++}`,
            title: this.generateTabTitle(result),
            result,
            active: true
        };

        // Mark other tabs as inactive
        this.tabs.forEach(t => t.active = false);

        // Add new tab
        this.tabs.push(tab);
        this.activeTabId = tab.id;

        // Limit to 10 tabs
        if (this.tabs.length > 10) {
            this.tabs.shift(); // Remove oldest
        }

        // Create or show panel
        if (!this.panel) {
            this.createPanel();
        } else {
            this.panel.reveal(vscode.ViewColumn.Two);
        }

        // Update content
        this.updateContent();
    }

    /**
     * Create the webview panel
     */
    private createPanel(): void {
        this.panel = vscode.window.createWebviewPanel(
            'datasharkResults',
            'Query Results',
            {
                viewColumn: vscode.ViewColumn.Two,
                preserveFocus: true
            },
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [
                    vscode.Uri.file(path.join(this.context.extensionPath, 'media'))
                ]
            }
        );

        // Handle panel disposal
        this.panel.onDidDispose(() => {
            this.panel = undefined;
        });

        // Handle messages from webview
        this.panel.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            undefined,
            this.context.subscriptions
        );

        // Set icon
        const iconPath = path.join(this.context.extensionPath, 'resources', 'database-icon.svg');
        if (fs.existsSync(iconPath)) {
            this.panel.iconPath = vscode.Uri.file(iconPath);
        }
    }

    /**
     * Update webview content
     */
    private updateContent(): void {
        if (!this.panel) {
            return;
        }

        this.panel.webview.html = this.getWebviewContent();
    }

    /**
     * Generate HTML content for webview
     */
    private getWebviewContent(): string {
        const activeTab = this.tabs.find(t => t.id === this.activeTabId);
        if (!activeTab) {
            return this.getEmptyState();
        }

        const nonce = this.getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
    <title>Query Results</title>
    <style>${this.getStyles()}</style>
</head>
<body>
    <div class="results-container">
        <!-- Tabs -->
        <div class="tabs-container">
            ${this.renderTabs()}
        </div>

        <!-- Toolbar -->
        <div class="toolbar">
            <input 
                type="text" 
                id="filter-input" 
                placeholder="Filter rows..." 
                class="filter-input"
            />
            <button class="btn" onclick="exportCSV()">📥 CSV</button>
            <button class="btn" onclick="exportJSON()">📥 JSON</button>
            <button class="btn" onclick="exportExcel()">📥 Excel</button>
            <button class="btn" onclick="copyAll()">📋 Copy All</button>
            <button class="btn" onclick="showFederated()">🌐 Federated View</button>
        </div>

        <!-- Data Grid -->
        <div class="data-grid-container">
            ${this.renderDataGrid(activeTab.result)}
        </div>

        <!-- Federated Intelligence Panel (hidden by default) -->
        <div class="trace-viewer" id="federated-view" style="display: none;">
            <div class="trace-header">
                <h3>Federated Intelligence</h3>
                <button class="btn" onclick="closeFederatedView()">Close</button>
            </div>
            <div class="trace-content" id="federated-content">
                <div class="trace-loading">Loading federated metrics...</div>
            </div>
        </div>

        <!-- Trace Viewer (expandable) -->
        ${activeTab.result.reasoningTraceId ? `
        <div class="trace-viewer" id="trace-viewer" style="display: none;">
            <div class="trace-header">
                <h3>Reasoning Trace</h3>
                <button class="btn" onclick="closeTraceViewer()">Close</button>
            </div>
            <div class="trace-content" id="trace-content">
                <div class="trace-loading">Loading trace...</div>
            </div>
        </div>
        ` : ''}

        <!-- Status Bar -->
        <div class="status-bar">
            <span class="status-info">
                ${activeTab.result.rowCount} rows • 
                ${activeTab.result.duration}ms • 
                ${activeTab.result.timestamp.toLocaleTimeString()}
                ${activeTab.result.reasoningTraceId ? ` • <button class="trace-btn" onclick="showTrace('${activeTab.result.reasoningTraceId}')">Why this result?</button>` : ''}
            </span>
        </div>
    </div>

    <script nonce="${nonce}">
        ${this.getScript()}
    </script>
</body>
</html>`;
    }

    /**
     * Render tabs HTML
     */
    private renderTabs(): string {
        return this.tabs.map(tab => `
            <div class="tab ${tab.active ? 'active' : ''}" data-tab-id="${tab.id}" onclick="switchTab('${tab.id}')">
                <span class="tab-title">${this.escapeHtml(tab.title)}</span>
                <button class="tab-close" onclick="closeTab(event, '${tab.id}')">×</button>
            </div>
        `).join('');
    }

    /**
     * Render data grid HTML
     */
    private renderDataGrid(result: QueryResult): string {
        if (result.error) {
            return `<div class="error-state">
                <h3>❌ Query Failed</h3>
                <pre>${this.escapeHtml(result.error)}</pre>
            </div>`;
        }

        if (result.rows.length === 0) {
            return `<div class="empty-state">
                <h3>No Results</h3>
                <p>The query returned no rows.</p>
            </div>`;
        }

        // Build table
        let html = '<table class="data-table">';
        
        // Header
        html += '<thead><tr>';
        result.columns.forEach((col, index) => {
            html += `<th data-column="${index}" onclick="sortColumn(${index})">
                <span class="column-name">${this.escapeHtml(col)}</span>
                <span class="sort-indicator" id="sort-${index}"></span>
            </th>`;
        });
        html += '</tr></thead>';

        // Body
        html += '<tbody id="data-tbody">';
        result.rows.forEach((row, rowIndex) => {
            html += `<tr data-row="${rowIndex}">`;
            row.forEach(cell => {
                const cellValue = cell === null ? '<null>' : String(cell);
                html += `<td title="${this.escapeHtml(cellValue)}">${this.escapeHtml(cellValue)}</td>`;
            });
            html += '</tr>';
        });
        html += '</tbody>';

        html += '</table>';

        return html;
    }

    /**
     * Get empty state HTML
     */
    private getEmptyState(): string {
        return `<!DOCTYPE html>
<html>
<head>
    <style>${this.getStyles()}</style>
</head>
<body>
    <div class="empty-state">
        <h2>No Query Results</h2>
        <p>Execute a query to see results here.</p>
    </div>
</body>
</html>`;
    }

    /**
     * Get CSS styles
     */
    private getStyles(): string {
        return `
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
                overflow: hidden;
            }

            .results-container {
                display: flex;
                flex-direction: column;
                height: 100vh;
            }

            /* Tabs */
            .tabs-container {
                display: flex;
                background-color: var(--vscode-tab-inactiveBackground);
                border-bottom: 1px solid var(--vscode-panel-border);
                overflow-x: auto;
                flex-shrink: 0;
            }

            .tab {
                display: flex;
                align-items: center;
                padding: 8px 12px;
                background-color: var(--vscode-tab-inactiveBackground);
                color: var(--vscode-tab-inactiveForeground);
                border-right: 1px solid var(--vscode-panel-border);
                cursor: pointer;
                user-select: none;
                white-space: nowrap;
            }

            .tab:hover {
                background-color: var(--vscode-tab-hoverBackground);
            }

            .tab.active {
                background-color: var(--vscode-tab-activeBackground);
                color: var(--vscode-tab-activeForeground);
                border-bottom: 2px solid var(--vscode-focusBorder);
            }

            .tab-title {
                margin-right: 8px;
            }

            .tab-close {
                background: none;
                border: none;
                color: inherit;
                cursor: pointer;
                font-size: 18px;
                line-height: 1;
                padding: 0 4px;
                opacity: 0.6;
            }

            .tab-close:hover {
                opacity: 1;
                background-color: var(--vscode-toolbar-hoverBackground);
                border-radius: 3px;
            }

            /* Toolbar */
            .toolbar {
                display: flex;
                gap: 8px;
                padding: 8px 12px;
                background-color: var(--vscode-editor-background);
                border-bottom: 1px solid var(--vscode-panel-border);
                flex-shrink: 0;
            }

            .filter-input {
                flex: 1;
                padding: 4px 8px;
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
                border: 1px solid var(--vscode-input-border);
                border-radius: 2px;
                outline: none;
            }

            .filter-input:focus {
                border-color: var(--vscode-focusBorder);
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

            /* Data Grid */
            .data-grid-container {
                flex: 1;
                overflow: auto;
                padding: 12px;
            }

            .data-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
            }

            .data-table thead {
                position: sticky;
                top: 0;
                background-color: var(--vscode-editor-background);
                z-index: 10;
            }

            .data-table th {
                padding: 8px 12px;
                text-align: left;
                font-weight: 600;
                border-bottom: 2px solid var(--vscode-panel-border);
                cursor: pointer;
                user-select: none;
                white-space: nowrap;
            }

            .data-table th:hover {
                background-color: var(--vscode-list-hoverBackground);
            }

            .column-name {
                margin-right: 4px;
            }

            .sort-indicator {
                opacity: 0.5;
                font-size: 10px;
            }

            .data-table td {
                padding: 6px 12px;
                border-bottom: 1px solid var(--vscode-panel-border);
                max-width: 400px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .data-table tr:hover {
                background-color: var(--vscode-list-hoverBackground);
            }

            /* Status Bar */
            .status-bar {
                padding: 6px 12px;
                background-color: var(--vscode-statusBar-background);
                color: var(--vscode-statusBar-foreground);
                border-top: 1px solid var(--vscode-panel-border);
                font-size: 12px;
                flex-shrink: 0;
            }

            /* Empty/Error States */
            .empty-state, .error-state {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100%;
                text-align: center;
                padding: 40px;
            }

            .empty-state h2, .empty-state h3,
            .error-state h3 {
                margin-bottom: 12px;
                color: var(--vscode-descriptionForeground);
            }

            .error-state pre {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 12px;
                border-radius: 4px;
                text-align: left;
                max-width: 600px;
                overflow-x: auto;
            }

            /* Trace Viewer */
            .trace-viewer {
                background-color: var(--vscode-editor-background);
                border-top: 1px solid var(--vscode-panel-border);
                max-height: 400px;
                overflow-y: auto;
                flex-shrink: 0;
            }

            .trace-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px;
                border-bottom: 1px solid var(--vscode-panel-border);
            }

            .trace-header h3 {
                margin: 0;
                font-size: 14px;
            }

            .trace-content {
                padding: 12px;
            }

            .trace-loading {
                text-align: center;
                padding: 20px;
                color: var(--vscode-descriptionForeground);
            }

            .trace-error {
                color: var(--vscode-errorForeground);
                padding: 12px;
            }

            .trace-summary {
                margin-bottom: 20px;
            }

            .trace-summary h4 {
                margin-bottom: 8px;
                font-size: 13px;
            }

            .trace-summary p {
                margin: 4px 0;
                font-size: 12px;
            }

            .trace-steps {
                margin-top: 16px;
            }

            .trace-steps h4 {
                margin-bottom: 12px;
                font-size: 13px;
            }

            .trace-step {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 12px;
                margin-bottom: 8px;
                border-radius: 4px;
                border-left: 3px solid var(--vscode-focusBorder);
            }

            .step-header {
                display: flex;
                gap: 12px;
                align-items: center;
                margin-bottom: 8px;
            }

            .step-number {
                background-color: var(--vscode-badge-background);
                color: var(--vscode-badge-foreground);
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
            }

            .step-operation {
                font-weight: 600;
                font-size: 12px;
            }

            .step-confidence {
                margin-left: auto;
                font-size: 11px;
                color: var(--vscode-descriptionForeground);
            }

            .confidence-high {
                border-left-color: var(--vscode-testing-iconPassed);
            }

            .confidence-medium {
                border-left-color: var(--vscode-testing-iconQueued);
            }

            .confidence-low {
                border-left-color: var(--vscode-errorForeground);
            }

            .step-confidence.confidence-high {
                color: var(--vscode-testing-iconPassed);
            }

            .step-confidence.confidence-medium {
                color: var(--vscode-testing-iconQueued);
            }

            .step-confidence.confidence-low {
                color: var(--vscode-errorForeground);
            }

            .step-header {
                cursor: pointer;
            }

            .step-toggle {
                margin-left: auto;
                font-size: 10px;
                opacity: 0.6;
            }

            .step-details {
                margin-top: 8px;
                padding-top: 8px;
                border-top: 1px solid var(--vscode-panel-border);
            }

            .step-input, .step-result {
                margin-top: 4px;
                font-size: 11px;
            }

            .step-input code, .step-result code {
                background-color: var(--vscode-textCodeBlock-background);
                padding: 2px 4px;
                border-radius: 2px;
                font-family: var(--vscode-editor-font-family);
                font-size: 10px;
                display: block;
                margin-top: 4px;
                white-space: pre-wrap;
                max-height: 200px;
                overflow-y: auto;
            }

            .trace-actions {
                margin-bottom: 12px;
                display: flex;
                gap: 8px;
            }

            .step-context, .step-rules, .step-duration {
                font-size: 11px;
                color: var(--vscode-descriptionForeground);
                margin-top: 4px;
            }

            .trace-btn {
                background: none;
                border: none;
                color: var(--vscode-textLink-foreground);
                cursor: pointer;
                text-decoration: underline;
                font-size: inherit;
                padding: 0;
            }

            .trace-btn:hover {
                color: var(--vscode-textLink-activeForeground);
            }

            /* Scrollbars */
            ::-webkit-scrollbar {
                width: 10px;
                height: 10px;
            }

            ::-webkit-scrollbar-track {
                background: var(--vscode-editor-background);
            }

            ::-webkit-scrollbar-thumb {
                background: var(--vscode-scrollbarSlider-background);
                border-radius: 5px;
            }

            ::-webkit-scrollbar-thumb:hover {
                background: var(--vscode-scrollbarSlider-hoverBackground);
            }
        `;
    }

    /**
     * Get JavaScript code
     */
    private getScript(): string {
        // Serialize tabs and active tab data to JavaScript
        const tabsJson = JSON.stringify(this.tabs.map(t => ({
            id: t.id,
            title: t.title,
            active: t.active,
            rowCount: t.result.rowCount,
            columns: t.result.columns,
            rows: t.result.rows
        })));

        const activeTabId = JSON.stringify(this.activeTabId);

        return `
            const vscode = acquireVsCodeApi();
            let tabs = ${tabsJson};
            let activeTabId = ${activeTabId};
            let sortColumn = -1;
            let sortAscending = true;
            let allRows = [];

            // Store original rows
            (function() {
                const activeTab = tabs.find(t => t.id === activeTabId);
                if (activeTab) {
                    allRows = activeTab.rows.slice(); // Copy array
                }
            })();

            // Switch tab
            function switchTab(tabId) {
                vscode.postMessage({
                    command: 'switchTab',
                    tabId: tabId
                });
            }

            // Close tab
            function closeTab(event, tabId) {
                event.stopPropagation();
                vscode.postMessage({
                    command: 'closeTab',
                    tabId: tabId
                });
            }

            // Sort column
            function sortColumn(columnIndex) {
                const tbody = document.getElementById('data-tbody');
                if (!tbody) return;

                const rows = Array.from(tbody.querySelectorAll('tr'));
                
                // Toggle sort direction if same column
                if (sortColumn === columnIndex) {
                    sortAscending = !sortAscending;
                } else {
                    sortColumn = columnIndex;
                    sortAscending = true;
                }

                // Sort rows
                rows.sort((a, b) => {
                    const aCell = a.children[columnIndex].textContent;
                    const bCell = b.children[columnIndex].textContent;

                    // Handle nulls
                    if (aCell === '<null>' && bCell !== '<null>') return 1;
                    if (aCell !== '<null>' && bCell === '<null>') return -1;
                    if (aCell === '<null>' && bCell === '<null>') return 0;

                    // Try numeric comparison
                    const aNum = parseFloat(aCell);
                    const bNum = parseFloat(bCell);
                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return sortAscending ? aNum - bNum : bNum - aNum;
                    }

                    // String comparison
                    const result = aCell.localeCompare(bCell);
                    return sortAscending ? result : -result;
                });

                // Clear tbody and re-append sorted rows
                tbody.innerHTML = '';
                rows.forEach(row => tbody.appendChild(row));

                // Update sort indicators
                document.querySelectorAll('.sort-indicator').forEach(el => {
                    el.textContent = '';
                });
                document.getElementById('sort-' + columnIndex).textContent = 
                    sortAscending ? '▲' : '▼';
            }

            // Filter rows
            document.getElementById('filter-input')?.addEventListener('input', (e) => {
                const filterText = e.target.value.toLowerCase();
                const tbody = document.getElementById('data-tbody');
                if (!tbody) return;

                const rows = tbody.querySelectorAll('tr');
                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(filterText) ? '' : 'none';
                });
            });

            // Export CSV
            function exportCSV() {
                vscode.postMessage({ command: 'exportCSV' });
            }

            // Export JSON
            function exportJSON() {
                vscode.postMessage({ command: 'exportJSON' });
            }

            // Export Excel
            function exportExcel() {
                vscode.postMessage({ command: 'exportExcel' });
            }

            // Copy all
            function copyAll() {
                vscode.postMessage({ command: 'copyAll' });
            }

            // Show Federated View
            function showFederated() {
                const panel = document.getElementById('federated-view');
                const content = document.getElementById('federated-content');
                if (!panel || !content) return;
                panel.style.display = 'block';
                content.innerHTML = '<div class="trace-loading">Loading federated metrics...</div>';
                vscode.postMessage({ command: 'openFederatedDoc' });
            }

            // Close Federated View
            function closeFederatedView() {
                const panel = document.getElementById('federated-view');
                if (panel) panel.style.display = 'none';
            }

            // Show trace viewer
            function showTrace(traceId) {
                const traceViewer = document.getElementById('trace-viewer');
                const traceContent = document.getElementById('trace-content');
                
                if (!traceViewer || !traceContent) return;
                
                traceViewer.style.display = 'block';
                traceContent.innerHTML = '<div class="trace-loading">Loading trace...</div>';
                
                vscode.postMessage({
                    command: 'getTrace',
                    traceId: traceId
                });
            }

            // Close trace viewer
            function closeTraceViewer() {
                const traceViewer = document.getElementById('trace-viewer');
                if (traceViewer) {
                    traceViewer.style.display = 'none';
                }
            }

            // Listen for trace data
            window.addEventListener('message', event => {
                const message = event.data;
                if (message.command === 'traceData') {
                    const traceContent = document.getElementById('trace-content');
                    if (traceContent) {
                        traceContent.innerHTML = renderTrace(message.trace);
                    }
                }
            });

            // Render trace data with collapsible tree and color-coding
            function renderTrace(trace) {
                if (!trace || trace.error) {
                    return \`<div class="trace-error">\${trace?.error || 'Trace not found'}</div>\`;
                }

                let html = \`
                    <div class="trace-summary">
                        <div class="trace-actions">
                            <button class="btn" onclick="copyTraceJSON()">📋 Copy Trace JSON</button>
                        </div>
                        <h4>Summary</h4>
                        <p><strong>Query:</strong> \${escapeHtml(trace.query || '')}</p>
                        <p><strong>Type:</strong> \${trace.query_type || 'unknown'}</p>
                        <p><strong>Explanation:</strong> \${escapeHtml(trace.explanation || '')}</p>
                    </div>
                \`;

                if (trace.steps && trace.steps.length > 0) {
                    html += '<div class="trace-steps"><h4>Steps</h4>';
                    trace.steps.forEach((step, idx) => {
                        const confidence = step.confidence || 1.0;
                        let confidenceClass = 'confidence-high';
                        if (confidence < 0.6) {
                            confidenceClass = 'confidence-low';
                        } else if (confidence < 0.9) {
                            confidenceClass = 'confidence-medium';
                        }

                        html += \`
                            <div class="trace-step \${confidenceClass}" data-step-id="\${step.step_id || idx}">
                                <div class="step-header" onclick="toggleStep(\${idx})">
                                    <span class="step-number">\${step.step_number || idx + 1}</span>
                                    <span class="step-operation">\${escapeHtml(step.operation || 'unknown')}</span>
                                    <span class="step-confidence \${confidenceClass}">Confidence: \${(confidence * 100).toFixed(1)}%</span>
                                    <span class="step-toggle">▼</span>
                                </div>
                                <div class="step-details" style="display: none;">
                                    \${step.node_context ? \`<div class="step-context">Node: \${escapeHtml(step.node_context)}</div>\` : ''}
                                    \${step.edge_context ? \`<div class="step-context">Edge: \${escapeHtml(step.edge_context)}</div>\` : ''}
                                    \${step.rule_matches && step.rule_matches.length > 0 ? 
                                        \`<div class="step-rules">Rules: \${step.rule_matches.map(r => escapeHtml(r)).join(', ')}</div>\` : ''}
                                    \${step.input_params ? \`<div class="step-input">Input: <code>\${escapeHtml(JSON.stringify(step.input_params, null, 2))}</code></div>\` : ''}
                                    \${step.result ? \`<div class="step-result">Result: <code>\${escapeHtml(JSON.stringify(step.result, null, 2))}</code></div>\` : ''}
                                    <div class="step-duration">Duration: \${step.duration_ms?.toFixed(2)}ms</div>
                                </div>
                            </div>
                        \`;
                    });
                    html += '</div>';
                }

                // Store trace for copy
                window.currentTrace = trace;

                return html;
            }

            // Toggle step details
            function toggleStep(stepIndex) {
                const step = document.querySelector(\`.trace-step[data-step-id="\${stepIndex}"]\`);
                if (!step) return;
                
                const details = step.querySelector('.step-details');
                const toggle = step.querySelector('.step-toggle');
                
                if (details && toggle) {
                    const isVisible = details.style.display !== 'none';
                    details.style.display = isVisible ? 'none' : 'block';
                    toggle.textContent = isVisible ? '▼' : '▲';
                }
            }

            // Copy trace JSON
            function copyTraceJSON() {
                if (window.currentTrace) {
                    const json = JSON.stringify(window.currentTrace, null, 2);
                    vscode.postMessage({
                        command: 'copyTraceJSON',
                        json: json
                    });
                }
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
        `;
    }

    /**
     * Handle messages from webview
     */
    private async handleMessage(message: any): Promise<void> {
        switch (message.command) {
            case 'switchTab':
                this.switchToTab(message.tabId);
                break;
            case 'closeTab':
                this.closeTab(message.tabId);
                break;
            case 'exportCSV':
                await this.exportToCSV();
                break;
            case 'exportJSON':
                await this.exportToJSON();
                break;
            case 'exportExcel':
                await this.exportToExcel();
                break;
            case 'copyAll':
                await this.copyAllToClipboard();
                break;
            case 'getTrace':
                await this.loadTrace(message.traceId);
                break;
            case 'copyTraceJSON':
                await this.copyTraceJSON(message.json);
                break;
            case 'openFederatedDoc':
                await this.openFederatedStatus();
                break;
        }
    }

    /**
     * Copy trace JSON to clipboard
     */
    private async copyTraceJSON(json: string): Promise<void> {
        try {
            await vscode.env.clipboard.writeText(json);
            vscode.window.showInformationMessage('✅ Trace JSON copied to clipboard');
            
            // Log telemetry
            const { TelemetryLogger } = await import('../utils/telemetry');
            TelemetryLogger.getInstance().logTraceCopied();
        } catch (error: any) {
            vscode.window.showErrorMessage(`Failed to copy trace: ${error.message}`);
        }
    }

    /**
     * Open federated intelligence status document if available
     */
    private async openFederatedStatus(): Promise<void> {
        try {
            const wsFolders = vscode.workspace.workspaceFolders;
            if (!wsFolders || wsFolders.length === 0) {
                vscode.window.showWarningMessage('No workspace found to locate federated status.');
                return;
            }
            const docUri = vscode.Uri.file(path.join(wsFolders[0].uri.fsPath, 'docs', 'status', 'FEDERATED_INTELLIGENCE_STATUS.md'));
            try {
                const doc = await vscode.workspace.openTextDocument(docUri);
                await vscode.window.showTextDocument(doc, vscode.ViewColumn.Two, true);
            } catch (err) {
                vscode.window.showWarningMessage('Federated status not found. Generate it via telemetry_dashboard --federated.');
            }
        } catch (error) {
            // no-op
        }
    }

    /**
     * Load trace data via MCP
     */
    private async loadTrace(traceId: string): Promise<void> {
        try {
            // Log trace viewed event
            const { TelemetryLogger } = await import('../utils/telemetry');
            TelemetryLogger.getInstance().logTraceViewed(traceId);
            
            // Import MCP client (circular dependency handled via dynamic import)
            const { MCPClient } = await import('../mcp/client');
            const mcpClient = MCPClient.getInstance(this.context);
            
            const trace = await mcpClient.call('get_trace', {
                trace_id: traceId
            });

            // Send trace data to webview
            if (this.panel) {
                this.panel.webview.postMessage({
                    command: 'traceData',
                    trace
                });
            }
        } catch (error: any) {
            if (this.panel) {
                this.panel.webview.postMessage({
                    command: 'traceData',
                    trace: { error: error.message || String(error) }
                });
            }
        }
    }

    /**
     * Switch to a different tab
     */
    private switchToTab(tabId: string): void {
        this.tabs.forEach(t => t.active = (t.id === tabId));
        this.activeTabId = tabId;
        this.updateContent();
    }

    /**
     * Close a tab
     */
    private closeTab(tabId: string): void {
        const index = this.tabs.findIndex(t => t.id === tabId);
        if (index === -1) return;

        this.tabs.splice(index, 1);

        // If closed tab was active, activate another
        if (tabId === this.activeTabId) {
            if (this.tabs.length > 0) {
                this.activeTabId = this.tabs[this.tabs.length - 1].id;
                this.tabs[this.tabs.length - 1].active = true;
            } else {
                this.activeTabId = undefined;
            }
        }

        this.updateContent();
    }

    /**
     * Export active tab to CSV
     */
    private async exportToCSV(): Promise<void> {
        const activeTab = this.tabs.find(t => t.id === this.activeTabId);
        if (!activeTab) return;

        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(`query-results-${Date.now()}.csv`),
            filters: { 'CSV Files': ['csv'] }
        });

        if (!uri) return;

        try {
            const csv = this.resultToCSV(activeTab.result);
            await fs.promises.writeFile(uri.fsPath, csv, 'utf8');
            vscode.window.showInformationMessage(`✅ Exported to ${path.basename(uri.fsPath)}`);
        } catch (error) {
            vscode.window.showErrorMessage(`❌ Export failed: ${error}`);
        }
    }

    /**
     * Export active tab to JSON
     */
    private async exportToJSON(): Promise<void> {
        const activeTab = this.tabs.find(t => t.id === this.activeTabId);
        if (!activeTab) return;

        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(`query-results-${Date.now()}.json`),
            filters: { 'JSON Files': ['json'] }
        });

        if (!uri) return;

        try {
            const json = this.resultToJSON(activeTab.result);
            await fs.promises.writeFile(uri.fsPath, json, 'utf8');
            vscode.window.showInformationMessage(`✅ Exported to ${path.basename(uri.fsPath)}`);
        } catch (error) {
            vscode.window.showErrorMessage(`❌ Export failed: ${error}`);
        }
    }

    /**
     * Export active tab to Excel (CSV format for now)
     */
    private async exportToExcel(): Promise<void> {
        // For now, export as CSV which can be opened in Excel
        // Future: Use a library like exceljs for true .xlsx format
        const activeTab = this.tabs.find(t => t.id === this.activeTabId);
        if (!activeTab) return;

        const uri = await vscode.window.showSaveDialog({
            defaultUri: vscode.Uri.file(`query-results-${Date.now()}.csv`),
            filters: { 'Excel Compatible': ['csv'] }
        });

        if (!uri) return;

        try {
            const csv = this.resultToCSV(activeTab.result);
            await fs.promises.writeFile(uri.fsPath, csv, 'utf8');
            vscode.window.showInformationMessage(`✅ Exported to ${path.basename(uri.fsPath)}`);
        } catch (error) {
            vscode.window.showErrorMessage(`❌ Export failed: ${error}`);
        }
    }

    /**
     * Copy all data to clipboard
     */
    private async copyAllToClipboard(): Promise<void> {
        const activeTab = this.tabs.find(t => t.id === this.activeTabId);
        if (!activeTab) return;

        try {
            const csv = this.resultToCSV(activeTab.result);
            await vscode.env.clipboard.writeText(csv);
            vscode.window.showInformationMessage(`✅ Copied ${activeTab.result.rowCount} rows to clipboard`);
        } catch (error) {
            vscode.window.showErrorMessage(`❌ Copy failed: ${error}`);
        }
    }

    /**
     * Convert result to CSV format
     */
    private resultToCSV(result: QueryResult): string {
        const lines: string[] = [];

        // Header
        lines.push(result.columns.map(c => this.escapeCSV(c)).join(','));

        // Rows
        for (const row of result.rows) {
            lines.push(row.map(cell => 
                this.escapeCSV(cell === null ? '' : String(cell))
            ).join(','));
        }

        return lines.join('\n');
    }

    /**
     * Convert result to JSON format
     */
    private resultToJSON(result: QueryResult): string {
        const objects = result.rows.map(row => {
            const obj: any = {};
            result.columns.forEach((col, i) => {
                obj[col] = row[i];
            });
            return obj;
        });

        return JSON.stringify(objects, null, 2);
    }

    /**
     * Escape CSV cell value
     */
    private escapeCSV(value: string): string {
        // If contains comma, quote, or newline, wrap in quotes and escape quotes
        if (value.includes(',') || value.includes('"') || value.includes('\n')) {
            return `"${value.replace(/"/g, '""')}"`;
        }
        return value;
    }

    /**
     * Escape HTML special characters
     */
    private escapeHtml(text: string): string {
        const map: { [key: string]: string } = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, m => map[m]);
    }

    /**
     * Generate a nonce for CSP
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
     * Generate tab title from query
     */
    private generateTabTitle(result: QueryResult): string {
        // Extract first significant part of query
        const query = result.query.trim().toUpperCase();
        
        if (query.startsWith('SELECT')) {
            // Try to find FROM clause
            const fromMatch = query.match(/FROM\s+([a-zA-Z0-9_.]+)/);
            if (fromMatch) {
                const table = fromMatch[1].split('.').pop();
                return `${table} (${result.rowCount})`;
            }
            return `Query (${result.rowCount})`;
        }

        // For other query types, use first few words
        const firstWords = result.query.trim().split(/\s+/).slice(0, 3).join(' ');
        return firstWords.length > 20 ? firstWords.substring(0, 20) + '...' : firstWords;
    }

    /**
     * Close the panel
     */
    public dispose(): void {
        if (this.panel) {
            this.panel.dispose();
            this.panel = undefined;
        }
        this.tabs = [];
        ResultsPanel.instance = undefined;
    }
}
















