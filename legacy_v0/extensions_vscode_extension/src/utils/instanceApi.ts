/**
 * Instance Management API
 * Thin wrappers around MCP instance management commands
 */

import { MCPClient } from '../mcp/client';
import * as vscode from 'vscode';

export interface InstanceConfig {
    name: string;
    repositories?: Array<{
        name: string;
        path: string;
        extractor: string;
    }>;
    database?: {
        type: string;
        host: string;
        user: string;
        password: string;
        database: string;
    };
}

export interface InstanceInfo {
    path: string;
    version: string;
    created: string;
}

export interface InstanceRegistry {
    active: string | null;
    instances: Record<string, InstanceInfo>;
}

export class InstanceAPI {
    constructor(private mcpClient: MCPClient) {}

    /**
     * List all instances from registry
     */
    async listInstances(): Promise<InstanceRegistry> {
        try {
            // Try to call MCP tool first
            const result = await this.mcpClient.callTool('list_instances', {});
            if (result && result.instances) {
                return result;
            }
        } catch (error) {
            console.debug('MCP list_instances not available, falling back to registry file');
        }

        // Fallback: read registry file directly
        const registryPath = vscode.Uri.joinPath(
            vscode.Uri.file(require('os').homedir()),
            '.datashark',
            'instances.json'
        );

        try {
            const data = await vscode.workspace.fs.readFile(registryPath);
            return JSON.parse(Buffer.from(data).toString());
        } catch (error) {
            console.error('Failed to read registry file:', error);
            return { active: null, instances: {} };
        }
    }

    /**
     * Get active instance info
     */
    async getActiveInstance(): Promise<InstanceInfo | null> {
        try {
            const registry = await this.listInstances();
            if (registry.active && registry.instances[registry.active]) {
                return registry.instances[registry.active];
            }
        } catch (error) {
            console.error('Failed to get active instance:', error);
        }
        return null;
    }

    /**
     * Create a new instance
     */
    async createInstance(config: InstanceConfig): Promise<{ path: string }> {
        try {
            // Try MCP tool first
            const result = await this.mcpClient.callTool('create_instance', {
                name: config.name,
                config: config
            });
            if (result && result.path) {
                return result;
            }
        } catch (error) {
            console.debug('MCP create_instance not available, using fallback');
        }

        // Fallback: call Python CLI via subprocess would go here
        // For now, return error
        throw new Error('Instance creation via MCP not yet implemented');
    }

    /**
     * Switch active instance
     */
    async switchInstance(name: string): Promise<void> {
        try {
            await this.mcpClient.callTool('switch_instance', { name });
        } catch (error) {
            console.error('Failed to switch instance:', error);
            throw error;
        }
    }

    /**
     * Build instance (run ingestion)
     */
    async buildInstance(name?: string): Promise<{
        instance: string;
        manifests_generated: number;
        status: string;
    }> {
        try {
            const result = await this.mcpClient.callTool('build_instance', {
                name: name || undefined
            });
            return result;
        } catch (error) {
            console.error('Failed to build instance:', error);
            throw error;
        }
    }
}
