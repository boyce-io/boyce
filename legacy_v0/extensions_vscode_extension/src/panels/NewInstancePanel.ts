/**
 * New Instance Panel
 * WebView form for creating a new DataShark instance
 */

import * as vscode from 'vscode';
import { InstanceAPI, InstanceConfig } from '../utils/instanceApi';
import { TelemetryLogger } from '../utils/telemetry';

export class NewInstancePanel {
    public static currentPanel: NewInstancePanel | undefined;
    private static readonly viewType = 'datashark.newInstance';

    private readonly _panel: vscode.WebviewPanel;
    private readonly _extensionUri: vscode.Uri;
    private _disposables: vscode.Disposable[] = [];
    private instanceApi: InstanceAPI;

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, instanceApi: InstanceAPI) {
        this._panel = panel;
        this._extensionUri = extensionUri;
        this.instanceApi = instanceApi;

        // Set the webview's initial html content
        this._update();

        // Listen for when the panel is disposed
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        // Handle messages from the webview
        this._panel.webview.onDidReceiveMessage(
            async (message) => {
                switch (message.command) {
                    case 'createInstance':
                        await this.handleCreateInstance(message.config);
                        return;
                    case 'cancel':
                        this._panel.dispose();
                        return;
                }
            },
            null,
            this._disposables
        );
    }

    public static createOrShow(extensionUri: vscode.Uri, instanceApi: InstanceAPI) {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        // If we already have a panel, show it
        if (NewInstancePanel.currentPanel) {
            NewInstancePanel.currentPanel._panel.reveal(column);
            return;
        }

        // Otherwise, create a new panel
        const panel = vscode.window.createWebviewPanel(
            NewInstancePanel.viewType,
            'Create New DataShark Instance',
            column || vscode.ViewColumn.One,
            {
                enableScripts: true,
                localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'media')],
                retainContextWhenHidden: true
            }
        );

        NewInstancePanel.currentPanel = new NewInstancePanel(panel, extensionUri, instanceApi);
    }

    private async handleCreateInstance(config: InstanceConfig) {
        const startTime = Date.now();
        try {
            const result = await this.instanceApi.createInstance(config);
            const duration = Date.now() - startTime;

            // Log telemetry (instance path available from result)
            TelemetryLogger.getInstance().logEvent('new_instance', {
                value: duration,
                source: 'ui',
                instance_name: config.name
            }, result.path);

            // Send success message to webview
            this._panel.webview.postMessage({
                command: 'instanceCreated',
                result: result
            });

            vscode.window.showInformationMessage(
                `✅ Instance "${config.name}" created successfully at ${result.path}`
            );

            // Close panel after short delay
            setTimeout(() => {
                this._panel.dispose();
            }, 1000);
        } catch (error: any) {
            const duration = Date.now() - startTime;
            TelemetryLogger.getInstance().logEvent('new_instance_failure', {
                value: duration,
                source: 'ui',
                error: error.message
            });

            // Send error to webview
            this._panel.webview.postMessage({
                command: 'instanceCreateError',
                error: error.message
            });

            vscode.window.showErrorMessage(`Failed to create instance: ${error.message}`);
        }
    }

    private _update() {
        const webview = this._panel.webview;
        this._panel.webview.html = this._getHtmlForWebview(webview);
    }

    private _getHtmlForWebview(webview: vscode.Webview) {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Create New Instance</title>
    <style>
        body {
            font-family: var(--vscode-font-family);
            padding: 20px;
            color: var(--vscode-foreground);
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
        }
        input[type="text"], input[type="password"], textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid var(--vscode-input-border);
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border-radius: 2px;
            font-family: var(--vscode-font-family);
        }
        button {
            padding: 8px 16px;
            margin-right: 10px;
            border: none;
            border-radius: 2px;
            cursor: pointer;
            font-weight: 500;
        }
        .btn-primary {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
        }
        .btn-primary:hover {
            background: var(--vscode-button-hoverBackground);
        }
        .btn-secondary {
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
        }
        .error {
            color: var(--vscode-errorForeground);
            margin-top: 10px;
            display: none;
        }
        .success {
            color: var(--vscode-textLink-foreground);
            margin-top: 10px;
            display: none;
        }
        .section {
            margin-bottom: 25px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        .section:last-child {
            border-bottom: none;
        }
        .section-title {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <h1>Create New DataShark Instance</h1>
    
    <form id="instanceForm">
        <div class="section">
            <div class="section-title">Instance Configuration</div>
            <div class="form-group">
                <label for="instanceName">Instance Name *</label>
                <input type="text" id="instanceName" name="instanceName" required 
                       placeholder="e.g., looker_dev, production">
            </div>
        </div>

        <div class="section">
            <div class="section-title">Repository</div>
            <div class="form-group">
                <label for="repoName">Repository Name</label>
                <input type="text" id="repoName" name="repoName" 
                       placeholder="e.g., looker_production">
            </div>
            <div class="form-group">
                <label for="repoPath">Repository Path</label>
                <input type="text" id="repoPath" name="repoPath" 
                       placeholder="~/Projects/Repositories/looker_production">
            </div>
            <div class="form-group">
                <label for="extractor">Extractor</label>
                <input type="text" id="extractor" name="extractor" value="bi_tool"
                       placeholder="bi_tool or database_catalog">
            </div>
        </div>

        <div class="section">
            <div class="section-title">Database (Optional)</div>
            <div class="form-group">
                <label for="dbType">Database Type</label>
                <input type="text" id="dbType" name="dbType" value="redshift"
                       placeholder="redshift, postgres, etc.">
            </div>
            <div class="form-group">
                <label for="dbHost">Host</label>
                <input type="text" id="dbHost" name="dbHost" placeholder="your-host.redshift.amazonaws.com">
            </div>
            <div class="form-group">
                <label for="dbUser">User</label>
                <input type="text" id="dbUser" name="dbUser" placeholder="username">
            </div>
            <div class="form-group">
                <label for="dbPassword">Password</label>
                <input type="password" id="dbPassword" name="dbPassword" placeholder="password">
            </div>
            <div class="form-group">
                <label for="dbDatabase">Database</label>
                <input type="text" id="dbDatabase" name="dbDatabase" placeholder="database_name">
            </div>
        </div>

        <div class="error" id="errorMessage"></div>
        <div class="success" id="successMessage"></div>

        <div style="margin-top: 20px;">
            <button type="submit" class="btn-primary">Create Instance</button>
            <button type="button" class="btn-secondary" onclick="cancel()">Cancel</button>
        </div>
    </form>

    <script>
        const vscode = acquireVsCodeApi();

        const form = document.getElementById('instanceForm');
        const errorDiv = document.getElementById('errorMessage');
        const successDiv = document.getElementById('successMessage');

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const formData = new FormData(form);
            const config = {
                name: formData.get('instanceName'),
                repositories: [],
                database: {}
            };

            // Add repository if provided
            const repoName = formData.get('repoName');
            const repoPath = formData.get('repoPath');
            const extractor = formData.get('extractor');
            if (repoName && repoPath) {
                config.repositories.push({
                    name: repoName,
                    path: repoPath,
                    extractor: extractor || 'bi_tool'
                });
            }

            // Add database config if provided
            const dbType = formData.get('dbType');
            const dbHost = formData.get('dbHost');
            if (dbType && dbHost) {
                config.database = {
                    type: dbType,
                    host: dbHost || '',
                    user: formData.get('dbUser') || '',
                    password: formData.get('dbPassword') || '',
                    database: formData.get('dbDatabase') || ''
                };
            }

            // Hide messages
            errorDiv.style.display = 'none';
            successDiv.style.display = 'none';

            // Send to extension
            vscode.postMessage({
                command: 'createInstance',
                config: config
            });
        });

        function cancel() {
            vscode.postMessage({ command: 'cancel' });
        }

        // Handle messages from extension
        window.addEventListener('message', event => {
            const message = event.data;
            switch (message.command) {
                case 'instanceCreated':
                    successDiv.textContent = \`✅ Instance created at \${message.result.path}\`;
                    successDiv.style.display = 'block';
                    break;
                case 'instanceCreateError':
                    errorDiv.textContent = \`❌ Error: \${message.error}\`;
                    errorDiv.style.display = 'block';
                    break;
            }
        });
    </script>
</body>
</html>`;
    }

    public dispose() {
        NewInstancePanel.currentPanel = undefined;

        // Clean up our resources
        this._panel.dispose();

        while (this._disposables.length) {
            const x = this._disposables.pop();
            if (x) {
                x.dispose();
            }
        }
    }
}
