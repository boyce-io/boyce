/**
 * Credential Manager
 * 
 * Manages secure storage of database credentials using VS Code Secret Storage API.
 * Credentials are stored in OS-native keychain (same as DataGrip).
 */

import * as vscode from 'vscode';

export interface ConnectionCredentials {
    user: string;
    password: string;
}

export class CredentialManager {
    constructor(private context: vscode.ExtensionContext) {}

    /**
     * Store credentials securely in OS keychain
     */
    async storeCredentials(
        profileName: string,
        credentials: ConnectionCredentials
    ): Promise<void> {
        const key = this.getStorageKey(profileName);
        const value = JSON.stringify(credentials);
        
        try {
            await this.context.secrets.store(key, value);
            console.log(`[CredentialManager] Stored credentials for profile: ${profileName}`);
        } catch (error) {
            console.error(`[CredentialManager] Failed to store credentials:`, error);
            throw new Error(`Failed to store credentials: ${error}`);
        }
    }

    /**
     * Retrieve credentials from secure storage
     */
    async getCredentials(profileName: string): Promise<ConnectionCredentials | null> {
        const key = this.getStorageKey(profileName);
        
        try {
            const value = await this.context.secrets.get(key);
            if (!value) {
                return null;
            }
            
            return JSON.parse(value) as ConnectionCredentials;
        } catch (error) {
            console.error(`[CredentialManager] Failed to retrieve credentials:`, error);
            return null;
        }
    }

    /**
     * Delete credentials from secure storage
     */
    async deleteCredentials(profileName: string): Promise<void> {
        const key = this.getStorageKey(profileName);
        
        try {
            await this.context.secrets.delete(key);
            console.log(`[CredentialManager] Deleted credentials for profile: ${profileName}`);
        } catch (error) {
            console.error(`[CredentialManager] Failed to delete credentials:`, error);
            throw new Error(`Failed to delete credentials: ${error}`);
        }
    }

    /**
     * Check if credentials exist for a profile
     */
    async hasCredentials(profileName: string): Promise<boolean> {
        const credentials = await this.getCredentials(profileName);
        return credentials !== null;
    }

    /**
     * Update only the password for a profile
     */
    async updatePassword(profileName: string, newPassword: string): Promise<void> {
        const existing = await this.getCredentials(profileName);
        if (!existing) {
            throw new Error(`No credentials found for profile: ${profileName}`);
        }

        await this.storeCredentials(profileName, {
            ...existing,
            password: newPassword
        });
    }

    /**
     * List all profiles that have stored credentials
     */
    async listProfilesWithCredentials(): Promise<string[]> {
        // VS Code doesn't provide a way to list all keys in secret storage
        // So we'll maintain a separate list in workspace settings
        const config = vscode.workspace.getConfiguration('datashark');
        const profiles = config.get<string[]>('profileNames', []);
        
        // Filter to only profiles that actually have credentials
        const withCredentials: string[] = [];
        for (const profile of profiles) {
            if (await this.hasCredentials(profile)) {
                withCredentials.push(profile);
            }
        }
        
        return withCredentials;
    }

    /**
     * Clear all credentials (for debugging or reset)
     */
    async clearAllCredentials(): Promise<void> {
        const profiles = await this.listProfilesWithCredentials();
        
        for (const profile of profiles) {
            await this.deleteCredentials(profile);
        }
        
        console.log(`[CredentialManager] Cleared all credentials`);
    }

    /**
     * Get storage key for a profile
     */
    private getStorageKey(profileName: string): string {
        return `datashark.credentials.${profileName}`;
    }

    /**
     * Export profile credentials (for backup/migration)
     * WARNING: This exposes passwords - use carefully
     */
    async exportCredentials(profileName: string): Promise<string | null> {
        const credentials = await this.getCredentials(profileName);
        if (!credentials) {
            return null;
        }
        
        // Return as base64 (not encryption, just encoding)
        return Buffer.from(JSON.stringify(credentials)).toString('base64');
    }

    /**
     * Import profile credentials from export
     */
    async importCredentials(profileName: string, exportedData: string): Promise<void> {
        try {
            const decoded = Buffer.from(exportedData, 'base64').toString('utf8');
            const credentials = JSON.parse(decoded) as ConnectionCredentials;
            
            await this.storeCredentials(profileName, credentials);
        } catch (error) {
            throw new Error(`Failed to import credentials: ${error}`);
        }
    }
}
















