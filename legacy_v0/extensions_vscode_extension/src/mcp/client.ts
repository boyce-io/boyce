/**
 * MCP Client
 * Communicates with DataShark MCP Server
 */

import * as vscode from 'vscode';
import * as child_process from 'child_process';
import { EventEmitter } from 'events';
import { CredentialManager } from '../settings/credentialManager';
import { ProfileManager } from '../settings/profileManager';

export interface Schema {
    name: string;
    table_count: number;
}

export interface Table {
    name: string;
    column_count?: number;
    row_count?: number;
    size_mb?: number;
}

export interface Column {
    name: string;
    type: string;
    nullable?: boolean;
    default?: string | null;
}

export interface TableInfo {
    schema: string;
    table: string;
    columns: Column[];
    primary_keys?: string[];
    foreign_keys?: any[];
    indexes?: any[];
}

export class MCPClient extends EventEmitter {
    private process?: child_process.ChildProcess;
    private context: vscode.ExtensionContext;
    private credentialManager: CredentialManager;
    private profileManager: ProfileManager;
    private requestId = 0;
    private pendingRequests = new Map<number, {
        resolve: (value: any) => void;
        reject: (error: Error) => void;
    }>();
    private healthCheckInterval?: NodeJS.Timeout;
    private lastHealthCheck?: Date;
    private isConnected = false;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 3;
    private reconnectDelay = 2000; // 2 seconds
    private disposed = false;

    constructor(context: vscode.ExtensionContext, credentialManager: CredentialManager) {
        super();
        this.context = context;
        this.credentialManager = credentialManager;
        this.profileManager = new ProfileManager(context, credentialManager);
    }

    async initialize(): Promise<void> {
        console.log('Initializing MCP client...');
        
        // Get active profile with credentials (enterprise-grade: Secret Storage ONLY, no env vars)
        const profileWithCreds = await this.profileManager.getActiveProfileWithCredentials();
        
        if (!profileWithCreds) {
            console.warn('⚠️ No database connection profile configured.');
            
            // Show clear message with action button
            vscode.window.showWarningMessage(
                '🔒 DataShark: Please configure your database connection',
                'Open Settings'
            ).then(selection => {
                if (selection === 'Open Settings') {
                    vscode.commands.executeCommand('datashark.openSettings');
                }
            });
            
            // Use empty profile - server will fail gracefully
            const emptyProfile = {
                host: '',
                port: 5439,
                database: '',
                user: '',
                password: '',
                type: 'redshift' as const
            };
            await this.startMCPServer(emptyProfile);
            return;
        }
        
        console.log(`✅ Using profile: ${profileWithCreds.name} (${profileWithCreds.type}://${profileWithCreds.host}:${profileWithCreds.port}/${profileWithCreds.database})`);
        await this.startMCPServer(profileWithCreds);
    }

    /**
     * Start the MCP server process with the given profile
     */
    private async startMCPServer(profile: { host: string; port: number; database: string; user: string; password: string; type: string }): Promise<void> {
        // Start MCP server process
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        const repoRoot = workspaceRoot ?? process.cwd();
        const mcpServerPath = path.join(repoRoot, 'datashark-mcp');
        const pythonPath = 'python3';
        
        this.process = child_process.spawn(pythonPath, ['-u', '-m', 'datashark.core.server'], {
            cwd: mcpServerPath,
            env: {
                ...process.env,
                PYTHONPATH: `${repoRoot}:${path.join(mcpServerPath, 'src')}:${process.env.PYTHONPATH ?? ''}`,
                DATASHARK_CACHE_MODE: 'cache',  // Use cached metadata for fast startup
                REDSHIFT_DATABASE: profile.database,  // From profile!
                REDSHIFT_HOST: profile.host,         // From profile!
                REDSHIFT_USER: profile.user,         // From Secret Storage!
                REDSHIFT_PASSWORD: profile.password, // From Secret Storage!
                REDSHIFT_PORT: profile.port.toString() // From profile!
            }
        });

        // Handle stdout (MCP responses)
        let buffer = '';
        this.process.stdout?.on('data', (data) => {
            buffer += data.toString();
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.trim()) {
                    try {
                        const response = JSON.parse(line);
                        this.handleResponse(response);
                    } catch (e) {
                        console.error('Failed to parse MCP response:', e);
                    }
                }
            }
        });

        // Handle stderr (logs)
        this.process.stderr?.on('data', (data) => {
            console.log(`MCP Server: ${data.toString()}`);
        });

        this.process.on('error', (error) => {
            console.error('MCP server error:', error);
            this.isConnected = false;
            this.emit('error', error);
            this.attemptReconnect();
        });

        this.process.on('exit', (code) => {
            console.log(`MCP server exited with code ${code}`);
            this.isConnected = false;
            this.emit('exit', code);
            
            // Only reconnect if not intentionally disposed and exit was unexpected
            if (!this.disposed && code !== 0) {
                this.attemptReconnect();
            }
        });

        // Send initialize request
        await this.sendRequest('initialize', {});
        this.isConnected = true;
        this.reconnectAttempts = 0;
        
        // Start health check
        this.startHealthCheck();
        
        console.log('✅ MCP client initialized');
    }

    async connect(): Promise<void> {
        // Already connected via initialization
        this.emit('connected');
    }

    private startHealthCheck(): void {
        // Stop existing health check if any
        this.stopHealthCheck();
        
        // Ping server every 30 seconds
        this.healthCheckInterval = setInterval(async () => {
            try {
                if (!this.isConnected || !this.process) {
                    console.warn('Health check: MCP server not connected');
                    return;
                }
                
                // Simple ping via list_schemas (fast cached operation)
                await Promise.race([
                    this.callTool('list_schemas', {}),
                    new Promise((_, reject) => 
                        setTimeout(() => reject(new Error('Health check timeout')), 5000)
                    )
                ]);
                
                this.lastHealthCheck = new Date();
                console.log('Health check: OK');
            } catch (error) {
                console.error('Health check failed:', error);
                this.isConnected = false;
                this.attemptReconnect();
            }
        }, 30000); // Every 30 seconds
    }

    private stopHealthCheck(): void {
        if (this.healthCheckInterval) {
            clearInterval(this.healthCheckInterval);
            this.healthCheckInterval = undefined;
        }
    }

    private async attemptReconnect(): Promise<void> {
        if (this.disposed) {
            console.log('Client disposed, skipping reconnect');
            return;
        }

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached, giving up');
            vscode.window.showErrorMessage(
                'DataShark: Connection lost. Please restart the extension.',
                'Restart'
            ).then(selection => {
                if (selection === 'Restart') {
                    vscode.commands.executeCommand('workbench.action.reloadWindow');
                }
            });
            return;
        }

        this.reconnectAttempts++;
        console.log(`Attempting reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
        
        // Clean up existing process
        if (this.process) {
            this.process.kill();
            this.process = undefined;
        }

        // Wait before reconnecting
        await new Promise(resolve => setTimeout(resolve, this.reconnectDelay));

        try {
            await this.initialize();
            console.log('✅ Reconnected successfully');
            vscode.window.showInformationMessage('DataShark: Reconnected to server');
        } catch (error) {
            console.error('Reconnect failed:', error);
            // Will retry on next failure
        }
    }

    getConnectionStatus(): { connected: boolean; lastHealthCheck?: Date; reconnectAttempts: number } {
        return {
            connected: this.isConnected,
            lastHealthCheck: this.lastHealthCheck,
            reconnectAttempts: this.reconnectAttempts
        };
    }

    async listSchemas(): Promise<Schema[]> {
        const result = await this.callTool('list_schemas', {});
        return result.schemas || [];
    }

    async searchTables(schema: string, pattern: string = '*'): Promise<Table[]> {
        const result = await this.callTool('search_tables', { schema, pattern });
        return result.tables || [];
    }

    async getTableInfo(schema: string, table: string): Promise<TableInfo> {
        const result = await this.callTool('get_table_info', { schema, table });
        return result;
    }

    async executeQuery(sql: string, limit: number = 100): Promise<any> {
        return await this.callTool('execute_query_safe', { sql, limit });
    }

    async generateSQL(prompt: string, profile?: string, dialect?: string): Promise<{ sql: string; snapshot_id: string; audit_artifact_path: string | null; error: string | null }> {
        const result = await this.callTool('generate_sql', {
            prompt,
            profile,
            dialect: dialect || 'postgres'
        });
        return result;
    }

    async callTool(toolName: string, args: any): Promise<any> {
        return await this.callToolInternal(toolName, args);
    }

    private async callToolInternal(toolName: string, args: any): Promise<any> {
        const result = await this.sendRequest('tools/call', {
            name: toolName,
            arguments: args
        });
        
        if (result.content && result.content[0]) {
            return JSON.parse(result.content[0].text);
        }
        
        return result;
    }

    private async sendRequest(method: string, params: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const id = ++this.requestId;
            const request = {
                jsonrpc: '2.0',
                id,
                method,
                params
            };

            this.pendingRequests.set(id, { resolve, reject });

            if (this.process && this.process.stdin) {
                this.process.stdin.write(JSON.stringify(request) + '\n');
            } else {
                reject(new Error('MCP server not running'));
            }

            // Timeout after 30 seconds
            setTimeout(() => {
                if (this.pendingRequests.has(id)) {
                    this.pendingRequests.delete(id);
                    reject(new Error('Request timeout'));
                }
            }, 30000);
        });
    }

    private handleResponse(response: any) {
        const { id, result, error } = response;
        
        if (id !== undefined && this.pendingRequests.has(id)) {
            const pending = this.pendingRequests.get(id)!;
            this.pendingRequests.delete(id);
            
            if (error) {
                pending.reject(new Error(error.message));
            } else {
                pending.resolve(result);
            }
        }
    }

    dispose() {
        console.log('🦈 Disposing MCP client...');
        this.disposed = true;
        this.isConnected = false;
        
        // Stop health checks
        this.stopHealthCheck();
        
        // Reject all pending requests
        for (const [id, pending] of this.pendingRequests.entries()) {
            pending.reject(new Error('Client disposed'));
        }
        this.pendingRequests.clear();
        
        // Kill process
        if (this.process) {
            console.log('🔪 Terminating MCP server process...');
            this.process.kill('SIGTERM');
            
            // Force kill after 2 seconds if still alive
            setTimeout(() => {
                if (this.process && !this.process.killed) {
                    console.log('⚠️ Force killing MCP server process...');
                    this.process.kill('SIGKILL');
                }
            }, 2000);
            
            this.process = undefined;
        }
        
        console.log('✅ MCP client disposed');
    }
}

