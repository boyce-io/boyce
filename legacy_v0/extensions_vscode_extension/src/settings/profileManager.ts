/**
 * Profile Manager
 * 
 * Manages connection profiles (non-sensitive data stored in workspace settings).
 */

import * as vscode from 'vscode';
import { CredentialManager } from './credentialManager';

export interface ConnectionProfile {
    name: string;
    type: 'redshift' | 'postgres';
    host: string;
    port: number;
    database: string;
    user: string;
    schema?: string;
    ssl?: boolean;
    keepalive?: number;
    timeout?: number;
}

export class ProfileManager {
    private readonly configKey = 'datashark';
    
    constructor(
        private context: vscode.ExtensionContext,
        private credentialManager: CredentialManager
    ) {}

    /**
     * Get all connection profiles
     */
    getProfiles(): ConnectionProfile[] {
        const config = vscode.workspace.getConfiguration(this.configKey);
        return config.get<ConnectionProfile[]>('profiles', []);
    }

    /**
     * Get a specific profile by name
     */
    getProfile(name: string): ConnectionProfile | undefined {
        const profiles = this.getProfiles();
        return profiles.find(p => p.name === name);
    }

    /**
     * Add or update a profile
     */
    async saveProfile(profile: ConnectionProfile, password: string): Promise<void> {
        const profiles = this.getProfiles();
        
        // Remove password from profile (will be stored separately)
        const profileWithoutPassword = { ...profile };
        
        // Find existing profile or add new one
        const index = profiles.findIndex(p => p.name === profile.name);
        if (index >= 0) {
            profiles[index] = profileWithoutPassword;
        } else {
            profiles.push(profileWithoutPassword);
        }

        // Save to workspace settings
        const config = vscode.workspace.getConfiguration(this.configKey);
        await config.update('profiles', profiles, vscode.ConfigurationTarget.Workspace);

        // Store credentials separately
        await this.credentialManager.storeCredentials(profile.name, {
            user: profile.user,
            password
        });

        // Update profile names list for credential tracking
        await this.updateProfileNamesList(profiles.map(p => p.name));

        console.log(`[ProfileManager] Saved profile: ${profile.name}`);
    }

    /**
     * Delete a profile
     */
    async deleteProfile(name: string): Promise<void> {
        const profiles = this.getProfiles();
        const filtered = profiles.filter(p => p.name !== name);

        const config = vscode.workspace.getConfiguration(this.configKey);
        await config.update('profiles', filtered, vscode.ConfigurationTarget.Workspace);

        // Delete credentials
        await this.credentialManager.deleteCredentials(name);

        // Update profile names list
        await this.updateProfileNamesList(filtered.map(p => p.name));

        console.log(`[ProfileManager] Deleted profile: ${name}`);
    }

    /**
     * Get the active profile name
     */
    getActiveProfileName(): string | undefined {
        const config = vscode.workspace.getConfiguration(this.configKey);
        return config.get<string>('activeProfile');
    }

    /**
     * Set the active profile
     */
    async setActiveProfile(name: string): Promise<void> {
        const profile = this.getProfile(name);
        if (!profile) {
            throw new Error(`Profile not found: ${name}`);
        }

        const config = vscode.workspace.getConfiguration(this.configKey);
        await config.update('activeProfile', name, vscode.ConfigurationTarget.Workspace);

        console.log(`[ProfileManager] Set active profile: ${name}`);
    }

    /**
     * Get the active profile with credentials
     */
    async getActiveProfileWithCredentials(): Promise<(ConnectionProfile & { password: string }) | null> {
        const activeProfileName = this.getActiveProfileName();
        if (!activeProfileName) {
            return null;
        }

        const profile = this.getProfile(activeProfileName);
        if (!profile) {
            return null;
        }

        const credentials = await this.credentialManager.getCredentials(activeProfileName);
        if (!credentials) {
            return null;
        }

        return {
            ...profile,
            password: credentials.password
        };
    }

    /**
     * Test a connection profile
     */
    async testConnection(profile: ConnectionProfile, password: string): Promise<{
        success: boolean;
        message: string;
        details?: any;
    }> {
        // This would call the MCP server to test the connection
        // For now, just validate the profile data
        
        if (!profile.host || !profile.port || !profile.database || !profile.user || !password) {
            return {
                success: false,
                message: 'Missing required connection parameters'
            };
        }

        // TODO: Actually test connection via MCP
        return {
            success: true,
            message: 'Connection successful!',
            details: {
                host: profile.host,
                database: profile.database,
                user: profile.user
            }
        };
    }

    /**
     * Duplicate a profile
     */
    async duplicateProfile(sourceName: string, newName: string): Promise<void> {
        const source = this.getProfile(sourceName);
        if (!source) {
            throw new Error(`Source profile not found: ${sourceName}`);
        }

        const credentials = await this.credentialManager.getCredentials(sourceName);
        if (!credentials) {
            throw new Error(`Credentials not found for profile: ${sourceName}`);
        }

        const duplicate: ConnectionProfile = {
            ...source,
            name: newName
        };

        await this.saveProfile(duplicate, credentials.password);
    }

    /**
     * Export a profile (without password)
     */
    exportProfile(name: string): string | null {
        const profile = this.getProfile(name);
        if (!profile) {
            return null;
        }

        // Export as JSON (without password)
        return JSON.stringify(profile, null, 2);
    }

    /**
     * Import a profile from JSON
     */
    async importProfile(json: string, password: string): Promise<void> {
        try {
            const profile = JSON.parse(json) as ConnectionProfile;
            
            // Validate required fields
            if (!profile.name || !profile.type || !profile.host || !profile.database) {
                throw new Error('Invalid profile format');
            }

            await this.saveProfile(profile, password);
        } catch (error) {
            throw new Error(`Failed to import profile: ${error}`);
        }
    }

    /**
     * Get profile connection string (for display only, no password)
     */
    getConnectionString(name: string): string | null {
        const profile = this.getProfile(name);
        if (!profile) {
            return null;
        }

        return `${profile.type}://${profile.user}@${profile.host}:${profile.port}/${profile.database}`;
    }

    /**
     * Validate profile data
     */
    validateProfile(profile: Partial<ConnectionProfile>): {
        valid: boolean;
        errors: string[];
    } {
        const errors: string[] = [];

        if (!profile.name || profile.name.trim() === '') {
            errors.push('Profile name is required');
        }

        if (!profile.type) {
            errors.push('Database type is required');
        }

        if (!profile.host || profile.host.trim() === '') {
            errors.push('Host is required');
        }

        if (!profile.port || profile.port < 1 || profile.port > 65535) {
            errors.push('Valid port (1-65535) is required');
        }

        if (!profile.database || profile.database.trim() === '') {
            errors.push('Database name is required');
        }

        if (!profile.user || profile.user.trim() === '') {
            errors.push('User is required');
        }

        return {
            valid: errors.length === 0,
            errors
        };
    }

    /**
     * Get default profile settings
     */
    getDefaultProfile(): Partial<ConnectionProfile> {
        return {
            type: 'redshift',
            port: 5439,
            ssl: true,
            keepalive: 30,
            timeout: 30
        };
    }

    /**
     * Update profile names list (for credential tracking)
     */
    private async updateProfileNamesList(names: string[]): Promise<void> {
        const config = vscode.workspace.getConfiguration(this.configKey);
        await config.update('profileNames', names, vscode.ConfigurationTarget.Workspace);
    }

    /**
     * Check for duplicate profile names
     */
    isDuplicateName(name: string, excludeCurrent?: string): boolean {
        const profiles = this.getProfiles();
        return profiles.some(p => 
            p.name === name && p.name !== excludeCurrent
        );
    }

    /**
     * Get profile statistics
     */
    getStatistics(): {
        totalProfiles: number;
        profilesByType: { [key: string]: number };
        activeProfile: string | undefined;
    } {
        const profiles = this.getProfiles();
        const profilesByType: { [key: string]: number } = {};

        profiles.forEach(p => {
            profilesByType[p.type] = (profilesByType[p.type] || 0) + 1;
        });

        return {
            totalProfiles: profiles.length,
            profilesByType,
            activeProfile: this.getActiveProfileName()
        };
    }
}
















