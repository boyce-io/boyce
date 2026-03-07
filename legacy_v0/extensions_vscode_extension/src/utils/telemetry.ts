/**
 * UI Telemetry Logging
 * 
 * Logs UI latency and query duration metrics to telemetry file.
 */

import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';

export interface TelemetryEvent {
    timestamp: string;
    metric: string;
    value: number;
    source: string;
    context?: Record<string, any>;
}

export class TelemetryLogger {
    private static instance: TelemetryLogger | undefined;
    private telemetryFile: string;
    private buffer: TelemetryEvent[] = [];
    private flushInterval: NodeJS.Timeout | undefined;

    private constructor() {
        // Use ~/.datashark/telemetry.jsonl (global) or instance/logs/ui_events.jsonl (instance-specific)
        const homeDir = os.homedir();
        const datasharkDir = path.join(homeDir, '.datashark');
        if (!fs.existsSync(datasharkDir)) {
            fs.mkdirSync(datasharkDir, { recursive: true });
        }
        this.telemetryFile = path.join(datasharkDir, 'telemetry.jsonl');
        
        // Flush buffer every 5 seconds
        this.flushInterval = setInterval(() => this.flush(), 5000);
    }

    /**
     * Get instance-specific telemetry file path
     */
    private getInstanceTelemetryFile(instancePath?: string): string {
        if (instancePath) {
            const instanceLogsDir = path.join(instancePath, 'logs');
            if (!fs.existsSync(instanceLogsDir)) {
                fs.mkdirSync(instanceLogsDir, { recursive: true });
            }
            return path.join(instanceLogsDir, 'ui_events.jsonl');
        }
        return this.telemetryFile;
    }

    /**
     * Log event to instance-specific file if instance path provided
     */
    public logEvent(metric: string, data: any, instancePath?: string): void {
        const event: TelemetryEvent = {
            timestamp: new Date().toISOString(),
            metric: metric,
            value: data.value || 0,
            source: data.source || 'unknown',
            context: data
        };

        // Write to instance-specific file if provided
        if (instancePath) {
            const instanceFile = this.getInstanceTelemetryFile(instancePath);
            try {
                fs.appendFileSync(instanceFile, JSON.stringify(event) + '\n');
            } catch (error) {
                console.error('Failed to write instance telemetry:', error);
            }
        }

        // Also buffer for global file
        this.buffer.push(event);
        if (this.buffer.length > 10) {
            this.flush();
        }
    }

    public static getInstance(): TelemetryLogger {
        if (!TelemetryLogger.instance) {
            TelemetryLogger.instance = new TelemetryLogger();
        }
        return TelemetryLogger.instance;
    }

    /**
     * Log a telemetry event
     */
    public log(metric: string, value: number, source: string, context?: Record<string, any>): void {
        const event: TelemetryEvent = {
            timestamp: new Date().toISOString(),
            metric,
            value,
            source,
            context
        };
        
        this.buffer.push(event);
        
        // Flush immediately for critical metrics
        if (metric.includes('error') || metric.includes('critical')) {
            this.flush();
        }
    }

    /**
     * Log schema load time
     */
    public logSchemaLoad(latencyMs: number, source: 'cache' | 'mcp'): void {
        this.log('schema_load_time_ms', latencyMs, 'schema_tree', { source });
    }

    /**
     * Log autocomplete latency
     */
    public logAutocomplete(latencyMs: number, type: string): void {
        this.log('autocomplete_latency_ms', latencyMs, 'completion_provider', { type });
    }

    /**
     * Log query execution latency
     */
    public logQueryExecution(latencyMs: number, rowCount: number, queryLength: number): void {
        this.log('query_execution_latency_ms', latencyMs, 'query_executor', {
            row_count: rowCount,
            query_length: queryLength
        });
    }

    /**
     * Log query start event
     */
    public logQueryStart(queryType: string, queryLength: number): void {
        this.log('query_start', 0, 'query_console', {
            query_type: queryType,
            query_length: queryLength,
            event: 'query_start'
        });
    }

    /**
     * Log query success event
     */
    public logQuerySuccess(latencyMs: number, rowCount: number, traceLength?: number): void {
        this.log('query_success', latencyMs, 'query_console', {
            event: 'query_success',
            row_count: rowCount,
            reasoning_trace_length: traceLength
        });
    }

    /**
     * Log query error event
     */
    public logQueryError(latencyMs: number, error: string): void {
        this.log('query_error', latencyMs, 'query_console', {
            event: 'query_error',
            error_message: error
        });
    }

    /**
     * Log trace viewed event
     */
    public logTraceViewed(traceId: string): void {
        this.log('trace_viewed', 1, 'query_console', {
            event: 'trace_viewed',
            trace_id: traceId
        });
    }

    /**
     * Log trace copied event
     */
    public logTraceCopied(): void {
        this.log('trace_copied', 1, 'results_panel', {
            event: 'trace_copied'
        });
    }

    /**
     * Log query history opened event
     */
    public logQueryHistoryOpened(queryId?: string): void {
        this.log('query_history_opened', 1, 'query_console', {
            event: 'query_history_opened',
            query_id: queryId
        });
    }

    /**
     * Log trace reinspected event
     */
    public logTraceReinspected(queryId: string, traceId: string): void {
        this.log('trace_reinspected', 1, 'query_console', {
            event: 'trace_reinspected',
            query_id: queryId,
            trace_id: traceId
        });
    }

    /**
     * Flush buffered events to file
     */
    private flush(): void {
        if (this.buffer.length === 0) {
            return;
        }

        try {
            const lines = this.buffer.map(e => JSON.stringify(e)).join('\n') + '\n';
            fs.appendFileSync(this.telemetryFile, lines, 'utf8');
            this.buffer = [];
        } catch (error) {
            console.error('Failed to write telemetry:', error);
        }
    }

    /**
     * Dispose telemetry logger
     */
    public dispose(): void {
        if (this.flushInterval) {
            clearInterval(this.flushInterval);
        }
        this.flush();
    }
}

/**
 * Convenience function to log telemetry
 */
export function logTelemetry(metric: string, value: number, source: string, context?: Record<string, any>): void {
    TelemetryLogger.getInstance().log(metric, value, source, context);
}

