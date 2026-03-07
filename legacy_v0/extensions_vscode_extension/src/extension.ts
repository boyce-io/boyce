/**
 * DataShark VS Code Extension
 * Main extension entry point
 */

import * as vscode from 'vscode';
import { SchemaTreeDataProvider } from './providers/schemaTreeProvider';
import { SQLEditorProvider } from './providers/sqlEditorProvider';
import { DataSharkCompletionProvider } from './providers/completionProvider';
import { MCPClient } from './mcp/client';
import { SettingsPanel } from './settings/settingsPanel';
import { CredentialManager } from './settings/credentialManager';
import { ProfileManager } from './settings/profileManager';
import { InstanceAPI } from './utils/instanceApi';
import { NewInstancePanel } from './panels/NewInstancePanel';
import { QueryConsolePanel } from './panels/queryConsolePanel';
import { TelemetryLogger } from './utils/telemetry';

let mcpClient: MCPClient;
let schemaTreeProvider: SchemaTreeDataProvider;
let sqlEditorProvider: SQLEditorProvider;
let statusBarItem: vscode.StatusBarItem;
let buildStatusBarItem: vscode.StatusBarItem;
let credentialManager: CredentialManager;
let profileManager: ProfileManager;
let instanceApi: InstanceAPI;

export async function activate(context: vscode.ExtensionContext) {
    console.log('🦈 DataShark extension activating...');

    // Initialize Credential Manager and Profile Manager (FIRST - before anything else)
    credentialManager = new CredentialManager(context);
    profileManager = new ProfileManager(context, credentialManager);
    console.log('✅ CredentialManager initialized (using VS Code Secret Storage)');

    // Check for environment variable migration (one-time only)
    await migrateEnvironmentVariables(profileManager);

    // Initialize MCP client (now with CredentialManager)
    mcpClient = new MCPClient(context, credentialManager);
    await mcpClient.initialize();

    // Initialize Instance API
    instanceApi = new InstanceAPI(mcpClient);

    // Initialize providers
    schemaTreeProvider = new SchemaTreeDataProvider(mcpClient, context, instanceApi);
    vscode.window.registerTreeDataProvider('datashark.schemaTree', schemaTreeProvider);
    
    // Update schema tree with active instance info
    await updateSchemaTreeTitle(context);
    
    sqlEditorProvider = new SQLEditorProvider(mcpClient, context);
    context.subscriptions.push(sqlEditorProvider);

    // Register SQL completion provider
    const completionProvider = new DataSharkCompletionProvider(mcpClient);
    context.subscriptions.push(
        vscode.languages.registerCompletionItemProvider(
            { language: 'sql', scheme: 'file' },
            completionProvider,
            '.', // Trigger on dot (for schema.table)
            ' ', // Trigger on space (for keywords)
            ',' // Trigger on comma (for column lists)
        )
    );

    // Create status bar items
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = "$(database) DataShark";
    statusBarItem.command = 'datashark.toggleDatabaseMode';
    statusBarItem.tooltip = 'Click to toggle Database Mode';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Build instance status bar item
    buildStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 99);
    buildStatusBarItem.text = "$(gear) Build Instance";
    buildStatusBarItem.command = 'datashark.buildInstance';
    buildStatusBarItem.tooltip = 'Build active instance (run ingestion)';
    buildStatusBarItem.show();
    context.subscriptions.push(buildStatusBarItem);

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.toggleDatabaseMode', async () => {
            await toggleDatabaseMode(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.refreshMetadata', async () => {
            await schemaTreeProvider.refresh();
            vscode.window.showInformationMessage('DataShark: Metadata refreshed');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.refreshSchemas', async () => {
            // Clear cache and refresh
            await context.globalState.update('datashark.schemaTree', undefined);
            await schemaTreeProvider.refresh();
            vscode.window.showInformationMessage('DataShark: Schemas refreshed');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.connectDatabase', async () => {
            await mcpClient.connect();
            await schemaTreeProvider.refresh();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.executeQuery', async () => {
            await sqlEditorProvider.executeCurrentQuery();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.formatQuery', async () => {
            await sqlEditorProvider.formatQuery();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.exportResults', async () => {
            vscode.window.showInformationMessage('Export feature coming soon!');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.openSettings', () => {
            SettingsPanel.show(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.previewTableData', async (item) => {
            await previewTableData(item);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.generateSelectQuery', async (item) => {
            await generateSelectQuery(item);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.copyTableName', async (item) => {
            await copyTableName(item);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.findSimilarColumns', async (item) => {
            await findSimilarColumns(item);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.showTableInfo', async (item) => {
            await showTableInfo(item);
        })
    );

    // Instance management commands
    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.newInstance', () => {
            NewInstancePanel.createOrShow(context.extensionUri, instanceApi);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.switchInstance', async () => {
            await switchInstance(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.buildInstance', async () => {
            await buildInstance(context);
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.generateSQL', async () => {
            await generateSQLCommand(context, mcpClient);
        })
    );

    // Query Console command
    context.subscriptions.push(
        vscode.commands.registerCommand('datashark.openQueryConsole', () => {
            const queryConsole = QueryConsolePanel.getInstance(context, mcpClient);
            queryConsole.show();
        })
    );

    // Auto-refresh on startup if enabled
    const config = vscode.workspace.getConfiguration('datashark');
    if (config.get('autoRefresh')) {
        await schemaTreeProvider.refresh();
    }

    console.log('✅ DataShark extension activated');
}

async function generateSQLCommand(context: vscode.ExtensionContext, mcpClient: MCPClient) {
    try {
        // Get prompt from user (selected text or input box)
        const editor = vscode.window.activeTextEditor;
        let prompt = '';
        
        if (editor && !editor.selection.isEmpty) {
            // Use selected text as prompt
            prompt = editor.document.getText(editor.selection);
        } else {
            // Prompt user for input
            const input = await vscode.window.showInputBox({
                prompt: 'Enter your natural language query',
                placeHolder: 'e.g., Total sales revenue by product category for the last 12 months',
                validateInput: (value) => {
                    if (!value || value.trim().length === 0) {
                        return 'Prompt cannot be empty';
                    }
                    return null;
                }
            });
            
            if (!input) {
                return; // User cancelled
            }
            prompt = input;
        }
        
        // Get configuration
        const config = vscode.workspace.getConfiguration('datashark');
        const profile = config.get<string>('profile', '');
        const dialect = config.get<string>('defaultDialect', 'postgres');
        
        // Show progress
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'DataShark: Generating SQL...',
            cancellable: false
        }, async (progress) => {
            progress.report({ increment: 0, message: 'Calling DataShark engine...' });
            
            // Call MCP tool
            const result = await mcpClient.generateSQL(prompt, profile || undefined, dialect);
            
            if (result.error) {
                vscode.window.showErrorMessage(`DataShark: ${result.error}`);
                return;
            }
            
            if (!result.sql) {
                vscode.window.showErrorMessage('DataShark: No SQL generated');
                return;
            }
            
            progress.report({ increment: 50, message: 'SQL generated, inserting into editor...' });
            
            // Create new untitled SQL file and insert SQL
            const doc = await vscode.workspace.openTextDocument({
                language: 'sql',
                content: result.sql
            });
            await vscode.window.showTextDocument(doc);
            
            // Copy to clipboard
            await vscode.env.clipboard.writeText(result.sql);
            
            progress.report({ increment: 100, message: 'Complete' });
            
            // Show success message with audit artifact path
            const auditMsg = result.audit_artifact_path 
                ? `\nAudit artifact: ${result.audit_artifact_path}`
                : '';
            vscode.window.showInformationMessage(
                `DataShark: SQL generated and copied to clipboard!${auditMsg}`,
                'View Audit'
            ).then(selection => {
                if (selection === 'View Audit' && result.audit_artifact_path) {
                    vscode.workspace.openTextDocument(result.audit_artifact_path).then(doc => {
                        vscode.window.showTextDocument(doc);
                    });
                }
            });
            
            // Log to output channel
            const outputChannel = vscode.window.createOutputChannel('DataShark');
            outputChannel.appendLine('=== DataShark: Generate SQL ===');
            outputChannel.appendLine(`Prompt: ${prompt}`);
            outputChannel.appendLine(`Snapshot ID: ${result.snapshot_id}`);
            outputChannel.appendLine(`Audit Artifact: ${result.audit_artifact_path || 'None'}`);
            outputChannel.appendLine(`Generated SQL:\n${result.sql}`);
            outputChannel.show();
        });
    } catch (error: any) {
        vscode.window.showErrorMessage(`DataShark: Failed to generate SQL - ${error.message}`);
        console.error('generateSQLCommand error:', error);
    }
}

export function deactivate() {
    console.log('DataShark extension deactivating...');
    if (mcpClient) {
        mcpClient.dispose();
    }
}

async function toggleDatabaseMode(context: vscode.ExtensionContext) {
    const currentMode = context.workspaceState.get('databaseMode', false);
    const newMode = !currentMode;
    
    await context.workspaceState.update('databaseMode', newMode);
    
    if (newMode) {
        // Enable database mode
        statusBarItem.text = "$(database) Database Mode";
        statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.prominentBackground');
        
        // Show schema tree
        await vscode.commands.executeCommand('workbench.view.extension.datashark-explorer');
        
        vscode.window.showInformationMessage('🦈 Database Mode enabled');
    } else {
        // Disable database mode
        statusBarItem.text = "$(database) DataShark";
        statusBarItem.backgroundColor = undefined;
        
        vscode.window.showInformationMessage('Database Mode disabled');
    }
}

async function previewTableData(item: any) {
    if (!item.schemaName || !item.table) {
        return;
    }

    try {
        const sql = `SELECT * FROM ${item.schemaName}.${item.table.name} LIMIT 10`;
        const result = await mcpClient.executeQuery(sql, 10);

        if (result.error || result.blocked) {
            vscode.window.showErrorMessage(`Query failed: ${result.error}`);
            return;
        }

        // Create output channel to show results
        const outputChannel = vscode.window.createOutputChannel('DataShark Preview');
        outputChannel.clear();
        outputChannel.appendLine(`Preview: ${item.schemaName}.${item.table.name}`);
        outputChannel.appendLine('='.repeat(80));
        outputChannel.appendLine('');

        // Format as table
        if (result.rows && result.rows.length > 0) {
            const columns = result.columns || Object.keys(result.rows[0]);
            outputChannel.appendLine(columns.join(' | '));
            outputChannel.appendLine('-'.repeat(80));
            
            result.rows.forEach((row: any) => {
                const values = columns.map((col: string) => String(row[col] ?? 'NULL'));
                outputChannel.appendLine(values.join(' | '));
            });
            
            outputChannel.appendLine('');
            outputChannel.appendLine(`Showing ${result.row_count} of ${result.row_count} rows`);
        } else {
            outputChannel.appendLine('No data found');
        }

        outputChannel.show();
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to preview table: ${error}`);
    }
}

async function generateSelectQuery(item: any) {
    if (!item.schemaName || !item.table) {
        return;
    }

    try {
        // Get table info to build proper SELECT with column names
        const tableInfo = await mcpClient.getTableInfo(item.schemaName, item.table.name);
        const columns = tableInfo.columns.map((col: any) => col.name).join(',\n    ');
        
        const query = `SELECT\n    ${columns}\nFROM ${item.schemaName}.${item.table.name}\nLIMIT 100;`;

        // Create new untitled document with the query
        const document = await vscode.workspace.openTextDocument({
            language: 'sql',
            content: query
        });
        
        await vscode.window.showTextDocument(document);
        vscode.window.showInformationMessage('✅ Query generated');
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to generate query: ${error}`);
    }
}

async function copyTableName(item: any) {
    if (!item.schemaName || !item.table) {
        return;
    }

    const fullName = `${item.schemaName}.${item.table.name}`;
    await vscode.env.clipboard.writeText(fullName);
    vscode.window.showInformationMessage(`Copied: ${fullName}`);
}

async function findSimilarColumns(item: any) {
    if (!item.column) {
        return;
    }

    try {
        const result = await mcpClient.callTool('search_columns', {
            column_name: item.column.name
        });

        const outputChannel = vscode.window.createOutputChannel('DataShark Column Search');
        outputChannel.clear();
        outputChannel.appendLine(`Tables with column: ${item.column.name}`);
        outputChannel.appendLine('='.repeat(80));
        outputChannel.appendLine('');

        if (result.tables && result.tables.length > 0) {
            result.tables.forEach((table: any) => {
                outputChannel.appendLine(`• ${table.schema}.${table.table} (${table.column_type})`);
            });
            outputChannel.appendLine('');
            outputChannel.appendLine(`Found ${result.count} tables`);
        } else {
            outputChannel.appendLine('No other tables found with this column');
        }

        outputChannel.show();
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to search columns: ${error}`);
    }
}

async function showTableInfo(item: any) {
    if (!item.schemaName || !item.table) {
        return;
    }

    try {
        const tableInfo = await mcpClient.getTableInfo(item.schemaName, item.table.name);

        const outputChannel = vscode.window.createOutputChannel('DataShark Table Info');
        outputChannel.clear();
        outputChannel.appendLine(`Table: ${item.schemaName}.${item.table.name}`);
        outputChannel.appendLine('='.repeat(80));
        outputChannel.appendLine('');

        // Columns
        outputChannel.appendLine('COLUMNS:');
        tableInfo.columns.forEach((col: any) => {
            const nullable = col.nullable ? 'NULL' : 'NOT NULL';
            const defaultVal = col.default ? ` DEFAULT ${col.default}` : '';
            outputChannel.appendLine(`  ${col.name} ${col.type} ${nullable}${defaultVal}`);
        });

        // Primary keys
        if (tableInfo.primary_keys && tableInfo.primary_keys.length > 0) {
            outputChannel.appendLine('');
            outputChannel.appendLine('PRIMARY KEYS:');
            tableInfo.primary_keys.forEach((pk: string) => {
                outputChannel.appendLine(`  ${pk}`);
            });
        }

        // Foreign keys
        if (tableInfo.foreign_keys && tableInfo.foreign_keys.length > 0) {
            outputChannel.appendLine('');
            outputChannel.appendLine('FOREIGN KEYS:');
            tableInfo.foreign_keys.forEach((fk: any) => {
                outputChannel.appendLine(`  ${fk.column} -> ${fk.referenced_table}.${fk.referenced_column}`);
            });
        }

        // Indexes
        if (tableInfo.indexes && tableInfo.indexes.length > 0) {
            outputChannel.appendLine('');
            outputChannel.appendLine('INDEXES:');
            tableInfo.indexes.forEach((idx: any) => {
                outputChannel.appendLine(`  ${idx.index_name} on (${idx.columns.join(', ')})`);
            });
        }

        outputChannel.show();
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to show table info: ${error}`);
    }
}

/**
 * Migrate environment variables to a full connection profile (one-time only)
 * One-time migration for users upgrading from env var-based configuration
 */
async function updateSchemaTreeTitle(context: vscode.ExtensionContext): Promise<void> {
    try {
        const activeInstance = await instanceApi.getActiveInstance();
        if (activeInstance) {
            // Update tree view title would go here
            // VS Code doesn't support dynamic tree view titles, but we can show in status
            const instanceName = activeInstance.path.split('/').pop() || 'unknown';
            buildStatusBarItem.tooltip = `Build instance: ${instanceName}`;
        }
    } catch (error) {
        console.debug('Failed to get active instance for title:', error);
    }
}

async function switchInstance(context: vscode.ExtensionContext): Promise<void> {
    const startTime = Date.now();
    try {
        const registry = await instanceApi.listInstances();
        const instanceNames = Object.keys(registry.instances);

        if (instanceNames.length === 0) {
            vscode.window.showInformationMessage('No instances found. Create one first with "DataShark: New Instance"');
            return;
        }

        const selected = await vscode.window.showQuickPick(instanceNames, {
            placeHolder: 'Select instance to switch to',
            canPickMany: false
        });

        if (!selected) {
            return;
        }

        await instanceApi.switchInstance(selected);
        const duration = Date.now() - startTime;

        // Log telemetry (try to get instance path for instance-specific logging)
        let instancePath: string | undefined;
        try {
            const activeInfo = await instanceApi.getActiveInstance();
            if (activeInfo) {
                instancePath = activeInfo.path;
            }
        } catch (e) {
            // Ignore
        }
        
        TelemetryLogger.getInstance().logEvent('switch_instance', {
            value: duration,
            source: 'ui',
            instance_name: selected
        }, instancePath);

        // Refresh schema tree
        await schemaTreeProvider.refresh();
        await updateSchemaTreeTitle(context);

        vscode.window.showInformationMessage(`✅ Switched to instance: ${selected}`);
    } catch (error: any) {
        const duration = Date.now() - startTime;
        TelemetryLogger.getInstance().logEvent('switch_instance_failure', {
            value: duration,
            source: 'ui',
            error: error.message
        });
        vscode.window.showErrorMessage(`Failed to switch instance: ${error.message}`);
    }
}

async function buildInstance(context: vscode.ExtensionContext): Promise<void> {
    const startTime = Date.now();
    try {
        const activeInstance = await instanceApi.getActiveInstance();
        if (!activeInstance) {
            vscode.window.showWarningMessage('No active instance. Please create or switch to an instance first.');
            return;
        }

        // Show progress
        const instanceName = activeInstance.path.split('/').pop() || 'active';
        buildStatusBarItem.text = "$(sync~spin) Building...";
        buildStatusBarItem.command = undefined;

        const result = await instanceApi.buildInstance();
        const duration = Date.now() - startTime;

        // Log telemetry to instance-specific file
        TelemetryLogger.getInstance().logEvent('build_instance', {
            value: duration,
            source: 'ui',
            instance_name: instanceName,
            manifests_generated: result.manifests_generated,
            status: result.status
        }, activeInstance.path);

        // Reset status bar
        buildStatusBarItem.text = "$(gear) Build Instance";
        buildStatusBarItem.command = 'datashark.buildInstance';

        // Refresh schema tree
        await schemaTreeProvider.refresh();

        vscode.window.showInformationMessage(
            `✅ Build complete: ${result.manifests_generated} manifests generated in ${(duration / 1000).toFixed(1)}s`
        );
    } catch (error: any) {
        const duration = Date.now() - startTime;
        TelemetryLogger.getInstance().logEvent('build_instance_failure', {
            value: duration,
            source: 'ui',
            error: error.message
        });

        // Reset status bar
        buildStatusBarItem.text = "$(gear) Build Instance";
        buildStatusBarItem.command = 'datashark.buildInstance';

        vscode.window.showErrorMessage(`Build failed: ${error.message}`);
    }
}

async function migrateEnvironmentVariables(profileManager: ProfileManager): Promise<void> {
    const profileName = 'default';
    
    // Check if a profile already exists
    const existingProfile = profileManager.getProfile(profileName);
    if (existingProfile) {
        console.log('✅ Profile already exists in Settings, skipping migration');
        return;
    }
    
    // Check if all environment variables exist
    const envHost = process.env.REDSHIFT_HOST;
    const envPort = process.env.REDSHIFT_PORT;
    const envDatabase = process.env.REDSHIFT_DATABASE;
    const envUser = process.env.REDSHIFT_USER;
    const envPassword = process.env.REDSHIFT_PASSWORD;
    
    if (!envHost || !envPort || !envDatabase || !envUser || !envPassword) {
        console.log('ℹ️ No complete environment variables found - user will configure via Settings UI');
        return;
    }
    
    // Ask user if they want to migrate
    const migrate = await vscode.window.showInformationMessage(
        '🔒 DataShark now uses secure profiles. Migrate your environment variables to a saved profile?',
        { modal: true },
        'Yes, Migrate',
        'Skip'
    );
    
    if (migrate === 'Yes, Migrate') {
        try {
            // Create full profile from environment variables
            const profile = {
                name: profileName,
                type: 'redshift' as const,
                host: envHost,
                port: parseInt(envPort),
                database: envDatabase,
                user: envUser,
                ssl: true
            };
            
            // Save profile with credentials
            await profileManager.saveProfile(profile, envPassword);
            await profileManager.setActiveProfile(profileName);
            
            vscode.window.showInformationMessage(
                `✅ Profile "${profileName}" created and activated. Environment variables are no longer needed.`,
                'Open Settings'
            ).then(selection => {
                if (selection === 'Open Settings') {
                    vscode.commands.executeCommand('datashark.openSettings');
                }
            });
            
            console.log('✅ Migrated environment variables to profile "default"');
        } catch (error) {
            vscode.window.showErrorMessage(`Failed to migrate: ${error}`);
        }
    } else {
        console.log('ℹ️ User skipped migration - will need to configure via Settings UI');
    }
}

