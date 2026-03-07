/**
 * Query History Manager
 * 
 * Manages persistent query history per instance.
 */

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { InstanceAPI } from './instanceApi';

export interface QueryHistoryEntry {
    id: string;
    timestamp: string;
    query: string;
    queryType: 'sql' | 'dsl' | 'nl';
    resultCount: number;
    duration: number;
    success: boolean;
    error?: string;
    reasoningTraceId?: string;
    explanation?: string;
}

export class QueryHistoryManager {
    private static instance: QueryHistoryManager | undefined;
    private historyFile: string | null = null;
    private entries: QueryHistoryEntry[] = [];
    private maxEntries = 100;

    private constructor() {}

    public static getInstance(): QueryHistoryManager {
        if (!QueryHistoryManager.instance) {
            QueryHistoryManager.instance = new QueryHistoryManager();
        }
        return QueryHistoryManager.instance;
    }

    /**
     * Initialize history manager for current instance
     */
    public async initialize(instanceApi: InstanceAPI): Promise<void> {
        try {
            const activeInstance = await instanceApi.getActiveInstance();
            if (!activeInstance || !activeInstance.path) {
                this.historyFile = null;
                this.entries = [];
                return;
            }

            const instancePath = activeInstance.path;
            const logsDir = path.join(instancePath, 'logs');
            if (!fs.existsSync(logsDir)) {
                fs.mkdirSync(logsDir, { recursive: true });
            }

            this.historyFile = path.join(logsDir, 'query_history.jsonl');
            this.loadHistory();
        } catch (error) {
            console.error('Error initializing query history:', error);
            this.historyFile = null;
            this.entries = [];
        }
    }

    /**
     * Load history from file
     */
    private loadHistory(): void {
        if (!this.historyFile || !fs.existsSync(this.historyFile)) {
            this.entries = [];
            return;
        }

        try {
            const content = fs.readFileSync(this.historyFile, 'utf8');
            this.entries = content
                .split('\n')
                .filter(line => line.trim())
                .map(line => JSON.parse(line))
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
                .slice(0, this.maxEntries);
        } catch (error) {
            console.error('Error loading query history:', error);
            this.entries = [];
        }
    }

    /**
     * Add query to history
     */
    public addQuery(entry: Omit<QueryHistoryEntry, 'id' | 'timestamp'>): void {
        if (!this.historyFile) {
            return;
        }

        const historyEntry: QueryHistoryEntry = {
            id: `query_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            timestamp: new Date().toISOString(),
            ...entry
        };

        this.entries.unshift(historyEntry);
        
        // Keep only last maxEntries
        if (this.entries.length > this.maxEntries) {
            this.entries = this.entries.slice(0, this.maxEntries);
        }

        // Append to file
        try {
            fs.appendFileSync(this.historyFile, JSON.stringify(historyEntry) + '\n', 'utf8');
        } catch (error) {
            console.error('Error saving query history:', error);
        }
    }

    /**
     * Get recent queries
     */
    public getRecent(limit: number = 50): QueryHistoryEntry[] {
        return this.entries.slice(0, limit);
    }

    /**
     * Get query by ID
     */
    public getQuery(id: string): QueryHistoryEntry | undefined {
        return this.entries.find(e => e.id === id);
    }

    /**
     * Search queries by text
     */
    public searchQueries(term: string): QueryHistoryEntry[] {
        const termLower = term.toLowerCase();
        return this.entries.filter(entry =>
            entry.query.toLowerCase().includes(termLower)
        );
    }

    /**
     * Clear history
     */
    public clearHistory(): void {
        this.entries = [];
        if (this.historyFile && fs.existsSync(this.historyFile)) {
            fs.unlinkSync(this.historyFile);
        }
    }
}

