/**
 * Settings Panel
 * 
 * Visual interface for managing database connection profiles and settings.
 */

import * as vscode from 'vscode';
import { ProfileManager, ConnectionProfile } from './profileManager';
import { CredentialManager } from './credentialManager';

export class SettingsPanel {
    private static instance: SettingsPanel | undefined;
    private panel: vscode.WebviewPanel | undefined;
    private profileManager: ProfileManager;
    private credentialManager: CredentialManager;

    private constructor(private context: vscode.ExtensionContext) {
        this.credentialManager = new CredentialManager(context);
        this.profileManager = new ProfileManager(context, this.credentialManager);
    }

    /**
     * Show the settings panel
     */
    public static show(context: vscode.ExtensionContext): void {
        if (!SettingsPanel.instance) {
            SettingsPanel.instance = new SettingsPanel(context);
        }
        SettingsPanel.instance.showPanel();
    }

    /**
     * Create or reveal the settings panel
     */
    private showPanel(): void {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.One);
            return;
        }

        this.panel = vscode.window.createWebviewPanel(
            'datasharkSettings',
            'DataShark Settings',
            vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true
            }
        );

        this.panel.webview.html = this.getWebviewContent();

        // Handle messages from webview
        this.panel.webview.onDidReceiveMessage(
            message => this.handleMessage(message),
            undefined,
            this.context.subscriptions
        );

        // Handle panel disposal
        this.panel.onDidDispose(() => {
            this.panel = undefined;
        });
    }

    /**
     * Handle messages from the webview
     */
    private async handleMessage(message: any): Promise<void> {
        switch (message.command) {
            case 'loadProfiles':
                await this.sendProfiles();
                break;
            case 'saveProfile':
                await this.saveProfile(message.profile, message.password);
                break;
            case 'deleteProfile':
                await this.deleteProfile(message.profileName);
                break;
            case 'testConnection':
                await this.testConnection(message.profile, message.password);
                break;
            case 'setActiveProfile':
                await this.setActiveProfile(message.profileName);
                break;
            case 'exportProfile':
                await this.exportProfile(message.profileName);
                break;
            case 'importProfile':
                await this.importProfile();
                break;
        }
    }

    /**
     * Send profiles to webview
     */
    private async sendProfiles(): Promise<void> {
        if (!this.panel) return;

        const profiles = this.profileManager.getProfiles();
        const activeProfile = this.profileManager.getActiveProfileName();

        this.panel.webview.postMessage({
            command: 'profilesLoaded',
            profiles,
            activeProfile
        });
    }

    /**
     * Save a profile
     */
    private async saveProfile(profile: ConnectionProfile, password: string): Promise<void> {
        try {
            // Validate profile
            const validation = this.profileManager.validateProfile(profile);
            if (!validation.valid) {
                this.showError(`Invalid profile: ${validation.errors.join(', ')}`);
                return;
            }

            // Note: Duplicate check is handled in the UI layer for better UX

            // Save profile
            await this.profileManager.saveProfile(profile, password);
            
            vscode.window.showInformationMessage(`✅ Profile "${profile.name}" saved`);
            
            // Reload profiles
            await this.sendProfiles();
        } catch (error) {
            this.showError(`Failed to save profile: ${error}`);
        }
    }

    /**
     * Delete a profile
     */
    private async deleteProfile(profileName: string): Promise<void> {
        try {
            const answer = await vscode.window.showWarningMessage(
                `Delete profile "${profileName}"?`,
                { modal: true },
                'Delete'
            );

            if (answer !== 'Delete') {
                return;
            }

            await this.profileManager.deleteProfile(profileName);
            
            vscode.window.showInformationMessage(`✅ Profile "${profileName}" deleted`);
            
            // Reload profiles
            await this.sendProfiles();
        } catch (error) {
            this.showError(`Failed to delete profile: ${error}`);
        }
    }

    /**
     * Test a connection
     */
    private async testConnection(profile: ConnectionProfile, password: string): Promise<void> {
        if (!this.panel) return;

        try {
            const result = await this.profileManager.testConnection(profile, password);
            
            this.panel.webview.postMessage({
                command: 'testResult',
                success: result.success,
                message: result.message,
                details: result.details
            });

            if (result.success) {
                vscode.window.showInformationMessage(`✅ ${result.message}`);
            } else {
                vscode.window.showErrorMessage(`❌ ${result.message}`);
            }
        } catch (error) {
            this.panel.webview.postMessage({
                command: 'testResult',
                success: false,
                message: String(error)
            });
            
            vscode.window.showErrorMessage(`Connection test failed: ${error}`);
        }
    }

    /**
     * Set active profile
     */
    private async setActiveProfile(profileName: string): Promise<void> {
        try {
            await this.profileManager.setActiveProfile(profileName);
            vscode.window.showInformationMessage(`✅ Active profile: ${profileName}`);
            await this.sendProfiles();
        } catch (error) {
            this.showError(`Failed to set active profile: ${error}`);
        }
    }

    /**
     * Export a profile
     */
    private async exportProfile(profileName: string): Promise<void> {
        try {
            const profileJson = this.profileManager.exportProfile(profileName);
            if (!profileJson) {
                this.showError(`Profile "${profileName}" not found`);
                return;
            }

            // Save to file
            const uri = await vscode.window.showSaveDialog({
                defaultUri: vscode.Uri.file(`${profileName}-profile.json`),
                filters: { 'JSON Files': ['json'] }
            });

            if (uri) {
                await vscode.workspace.fs.writeFile(uri, Buffer.from(profileJson, 'utf8'));
                vscode.window.showInformationMessage(`✅ Profile exported to ${uri.fsPath}`);
            }
        } catch (error) {
            this.showError(`Failed to export profile: ${error}`);
        }
    }

    /**
     * Import a profile
     */
    private async importProfile(): Promise<void> {
        try {
            const uri = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                filters: { 'JSON Files': ['json'] }
            });

            if (!uri || uri.length === 0) {
                return;
            }

            const content = await vscode.workspace.fs.readFile(uri[0]);
            const json = Buffer.from(content).toString('utf8');

            // Prompt for password
            const password = await vscode.window.showInputBox({
                prompt: 'Enter password for this profile',
                password: true,
                placeHolder: 'Password'
            });

            if (!password) {
                return;
            }

            await this.profileManager.importProfile(json, password);
            
            vscode.window.showInformationMessage(`✅ Profile imported successfully`);
            await this.sendProfiles();
        } catch (error) {
            this.showError(`Failed to import profile: ${error}`);
        }
    }

    /**
     * Show error message
     */
    private showError(message: string): void {
        vscode.window.showErrorMessage(message);
        
        if (this.panel) {
            this.panel.webview.postMessage({
                command: 'error',
                message
            });
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
    <title>DataShark Settings</title>
    <style>${this.getStyles()}</style>
</head>
<body>
    <div class="container">
        <h1>🦈 DataShark Settings</h1>
        
        <!-- Profile List -->
        <div class="section">
            <h2>Connection Profiles</h2>
            <div id="profile-list" class="profile-list"></div>
            <button class="btn btn-primary" onclick="showNewProfileForm()">
                + Add New Profile
            </button>
            <button class="btn" onclick="importProfile()">
                📥 Import Profile
            </button>
        </div>

        <!-- Profile Form -->
        <div id="profile-form" class="section" style="display: none;">
            <h2 id="form-title">New Connection Profile</h2>
            
            <div class="form-group">
                <label>Profile Name *</label>
                <input type="text" id="profile-name" placeholder="e.g., Production">
            </div>

            <div class="form-group">
                <label>Database Type *</label>
                <select id="profile-type">
                    <option value="redshift">Amazon Redshift</option>
                    <option value="postgres">PostgreSQL</option>
                </select>
            </div>

            <div class="form-group">
                <label>Host *</label>
                <input type="text" id="profile-host" placeholder="e.g., my-cluster.redshift.amazonaws.com">
            </div>

            <div class="form-row">
                <div class="form-group">
                    <label>Port *</label>
                    <input type="number" id="profile-port" value="5439">
                </div>
                <div class="form-group">
                    <label>Database *</label>
                    <input type="text" id="profile-database" placeholder="e.g., analytics">
                </div>
            </div>

            <div class="form-group">
                <label>User *</label>
                <input type="text" id="profile-user" placeholder="e.g., readonly_user">
            </div>

            <div class="form-group">
                <label>Password *</label>
                <input type="password" id="profile-password" placeholder="Password">
                <small>Stored securely in OS keychain</small>
            </div>

            <div class="form-group">
                <label>Default Schema (optional)</label>
                <input type="text" id="profile-schema" placeholder="e.g., public">
            </div>

            <details class="advanced-settings">
                <summary>Advanced Settings</summary>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="profile-ssl" checked>
                        Enable SSL
                    </label>
                </div>
                <div class="form-group">
                    <label>Keepalive Interval (seconds)</label>
                    <input type="number" id="profile-keepalive" value="30">
                </div>
                <div class="form-group">
                    <label>Connection Timeout (seconds)</label>
                    <input type="number" id="profile-timeout" value="30">
                </div>
            </details>

            <div class="form-actions">
                <button class="btn" onclick="testConnection()">
                    🔍 Test Connection
                </button>
                <button class="btn btn-primary" onclick="saveProfile()">
                    💾 Save Profile
                </button>
                <button class="btn" onclick="cancelEdit()">
                    Cancel
                </button>
            </div>

            <div id="test-result" class="test-result" style="display: none;"></div>
        </div>
    </div>

    <script nonce="${nonce}">
        ${this.getScript()}
    </script>
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
                padding: 20px;
            }

            .container {
                max-width: 800px;
                margin: 0 auto;
            }

            h1 {
                margin-bottom: 24px;
                font-size: 24px;
            }

            h2 {
                margin-bottom: 16px;
                font-size: 18px;
                font-weight: 600;
            }

            .section {
                background-color: var(--vscode-editor-background);
                border: 1px solid var(--vscode-panel-border);
                border-radius: 4px;
                padding: 20px;
                margin-bottom: 20px;
            }

            .profile-list {
                margin-bottom: 16px;
            }

            .profile-item {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 12px 16px;
                margin-bottom: 8px;
                background-color: var(--vscode-list-inactiveSelectionBackground);
                border-radius: 4px;
                cursor: pointer;
            }

            .profile-item:hover {
                background-color: var(--vscode-list-hoverBackground);
            }

            .profile-item.active {
                background-color: var(--vscode-list-activeSelectionBackground);
                border-left: 3px solid var(--vscode-focusBorder);
            }

            .profile-info {
                flex: 1;
            }

            .profile-name {
                font-weight: 600;
                margin-bottom: 4px;
            }

            .profile-details {
                font-size: 12px;
                opacity: 0.8;
            }

            .profile-actions {
                display: flex;
                gap: 8px;
            }

            .btn {
                padding: 6px 16px;
                background-color: var(--vscode-button-secondaryBackground);
                color: var(--vscode-button-secondaryForeground);
                border: none;
                border-radius: 2px;
                cursor: pointer;
                font-size: 13px;
            }

            .btn:hover {
                background-color: var(--vscode-button-secondaryHoverBackground);
            }

            .btn-primary {
                background-color: var(--vscode-button-background);
                color: var(--vscode-button-foreground);
            }

            .btn-primary:hover {
                background-color: var(--vscode-button-hoverBackground);
            }

            .btn-danger {
                background-color: #d73a49;
                color: white;
            }

            .btn-danger:hover {
                background-color: #cb2431;
            }

            .btn-small {
                padding: 4px 12px;
                font-size: 12px;
            }

            .form-group {
                margin-bottom: 16px;
            }

            .form-row {
                display: grid;
                grid-template-columns: 1fr 2fr;
                gap: 16px;
            }

            label {
                display: block;
                margin-bottom: 6px;
                font-weight: 500;
            }

            input[type="text"],
            input[type="password"],
            input[type="number"],
            select {
                width: 100%;
                padding: 6px 10px;
                background-color: var(--vscode-input-background);
                color: var(--vscode-input-foreground);
                border: 1px solid var(--vscode-input-border);
                border-radius: 2px;
                outline: none;
            }

            input:focus,
            select:focus {
                border-color: var(--vscode-focusBorder);
            }

            small {
                display: block;
                margin-top: 4px;
                font-size: 11px;
                opacity: 0.7;
            }

            .advanced-settings {
                margin: 16px 0;
                border: 1px solid var(--vscode-panel-border);
                border-radius: 4px;
                padding: 12px;
            }

            .advanced-settings summary {
                cursor: pointer;
                font-weight: 500;
                margin-bottom: 12px;
            }

            .form-actions {
                display: flex;
                gap: 12px;
                margin-top: 20px;
            }

            .test-result {
                margin-top: 16px;
                padding: 12px;
                border-radius: 4px;
            }

            .test-result.success {
                background-color: rgba(46, 160, 67, 0.2);
                border: 1px solid rgba(46, 160, 67, 0.5);
            }

            .test-result.error {
                background-color: rgba(215, 58, 73, 0.2);
                border: 1px solid rgba(215, 58, 73, 0.5);
            }

            input[type="checkbox"] {
                margin-right: 8px;
            }
        `;
    }

    /**
     * Get JavaScript code
     */
    private getScript(): string {
        return `
            const vscode = acquireVsCodeApi();
            let profiles = [];
            let activeProfile = null;
            let editingProfile = null;

            // Load profiles on startup
            window.addEventListener('load', () => {
                vscode.postMessage({ command: 'loadProfiles' });
            });

            // Handle messages from extension
            window.addEventListener('message', event => {
                const message = event.data;
                
                switch (message.command) {
                    case 'profilesLoaded':
                        profiles = message.profiles;
                        activeProfile = message.activeProfile;
                        renderProfiles();
                        break;
                    case 'testResult':
                        showTestResult(message);
                        break;
                    case 'error':
                        alert('Error: ' + message.message);
                        break;
                }
            });

            // Render profile list
            function renderProfiles() {
                const list = document.getElementById('profile-list');
                
                if (profiles.length === 0) {
                    list.innerHTML = '<p style="opacity: 0.7;">No profiles configured yet. Click "Add New Profile" to get started.</p>';
                    return;
                }

                list.innerHTML = profiles.map(profile => {
                    const isActive = profile.name === activeProfile;
                    return \`
                        <div class="profile-item \${isActive ? 'active' : ''}" onclick="setActiveProfile('\${profile.name}')">
                            <div class="profile-info">
                                <div class="profile-name">
                                    \${isActive ? '● ' : ''}\${profile.name}
                                </div>
                                <div class="profile-details">
                                    \${profile.type}://\${profile.host}:\${profile.port}/\${profile.database}
                                </div>
                            </div>
                            <div class="profile-actions">
                                <button class="btn btn-small" onclick="event.stopPropagation(); editProfile('\${profile.name}')">
                                    Edit
                                </button>
                                <button class="btn btn-small" onclick="event.stopPropagation(); exportProfile('\${profile.name}')">
                                    Export
                                </button>
                                <button class="btn btn-small btn-danger" onclick="event.stopPropagation(); deleteProfile('\${profile.name}')">
                                    Delete
                                </button>
                            </div>
                        </div>
                    \`;
                }).join('');
            }

            // Show new profile form
            function showNewProfileForm() {
                editingProfile = null;
                document.getElementById('form-title').textContent = 'New Connection Profile';
                clearForm();
                document.getElementById('profile-form').style.display = 'block';
                document.getElementById('profile-name').focus();
            }

            // Edit existing profile
            function editProfile(name) {
                const profile = profiles.find(p => p.name === name);
                if (!profile) return;

                editingProfile = profile;
                document.getElementById('form-title').textContent = 'Edit Profile: ' + name;
                
                // Populate form
                document.getElementById('profile-name').value = profile.name;
                document.getElementById('profile-type').value = profile.type;
                document.getElementById('profile-host').value = profile.host;
                document.getElementById('profile-port').value = profile.port;
                document.getElementById('profile-database').value = profile.database;
                document.getElementById('profile-user').value = profile.user;
                document.getElementById('profile-schema').value = profile.schema || '';
                document.getElementById('profile-ssl').checked = profile.ssl !== false;
                document.getElementById('profile-keepalive').value = profile.keepalive || 30;
                document.getElementById('profile-timeout').value = profile.timeout || 30;
                
                document.getElementById('profile-form').style.display = 'block';
            }

            // Clear form
            function clearForm() {
                document.getElementById('profile-name').value = '';
                document.getElementById('profile-type').value = 'redshift';
                document.getElementById('profile-host').value = '';
                document.getElementById('profile-port').value = '5439';
                document.getElementById('profile-database').value = '';
                document.getElementById('profile-user').value = '';
                document.getElementById('profile-password').value = '';
                document.getElementById('profile-schema').value = '';
                document.getElementById('profile-ssl').checked = true;
                document.getElementById('profile-keepalive').value = '30';
                document.getElementById('profile-timeout').value = '30';
                document.getElementById('test-result').style.display = 'none';
            }

            // Cancel edit
            function cancelEdit() {
                editingProfile = null;
                document.getElementById('profile-form').style.display = 'none';
                clearForm();
            }

            // Save profile
            function saveProfile() {
                const profile = {
                    name: document.getElementById('profile-name').value.trim(),
                    type: document.getElementById('profile-type').value,
                    host: document.getElementById('profile-host').value.trim(),
                    port: parseInt(document.getElementById('profile-port').value),
                    database: document.getElementById('profile-database').value.trim(),
                    user: document.getElementById('profile-user').value.trim(),
                    schema: document.getElementById('profile-schema').value.trim() || undefined,
                    ssl: document.getElementById('profile-ssl').checked,
                    keepalive: parseInt(document.getElementById('profile-keepalive').value),
                    timeout: parseInt(document.getElementById('profile-timeout').value)
                };

                const password = document.getElementById('profile-password').value;

                if (!profile.name || !profile.host || !profile.database || !profile.user || !password) {
                    alert('Please fill in all required fields');
                    return;
                }

                vscode.postMessage({
                    command: 'saveProfile',
                    profile,
                    password,
                    isNew: !editingProfile
                });

                cancelEdit();
            }

            // Test connection
            function testConnection() {
                const profile = {
                    name: document.getElementById('profile-name').value.trim(),
                    type: document.getElementById('profile-type').value,
                    host: document.getElementById('profile-host').value.trim(),
                    port: parseInt(document.getElementById('profile-port').value),
                    database: document.getElementById('profile-database').value.trim(),
                    user: document.getElementById('profile-user').value.trim()
                };

                const password = document.getElementById('profile-password').value;

                vscode.postMessage({
                    command: 'testConnection',
                    profile,
                    password
                });
            }

            // Show test result
            function showTestResult(result) {
                const div = document.getElementById('test-result');
                div.style.display = 'block';
                div.className = 'test-result ' + (result.success ? 'success' : 'error');
                div.innerHTML = \`
                    <strong>\${result.success ? '✅' : '❌'} \${result.message}</strong>
                    \${result.details ? '<pre>' + JSON.stringify(result.details, null, 2) + '</pre>' : ''}
                \`;
            }

            // Set active profile
            function setActiveProfile(name) {
                vscode.postMessage({
                    command: 'setActiveProfile',
                    profileName: name
                });
            }

            // Delete profile
            function deleteProfile(name) {
                vscode.postMessage({
                    command: 'deleteProfile',
                    profileName: name
                });
            }

            // Export profile
            function exportProfile(name) {
                vscode.postMessage({
                    command: 'exportProfile',
                    profileName: name
                });
            }

            // Import profile
            function importProfile() {
                vscode.postMessage({
                    command: 'importProfile'
                });
            }
        `;
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
}

