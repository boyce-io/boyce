/**
 * Query Store
 * 
 * Reactive state management for query console and results.
 */

export interface QueryState {
    queryText: string;
    queryStatus: 'idle' | 'running' | 'success' | 'error';
    results: any[];
    schema: string[];
    trace: any | null;
    traceId: string | null;
    latency: number;
    error: string | null;
}

class QueryStore {
    private state: QueryState = {
        queryText: '',
        queryStatus: 'idle',
        results: [],
        schema: [],
        trace: null,
        traceId: null,
        latency: 0,
        error: null
    };

    private listeners: Set<(state: QueryState) => void> = new Set();

    /**
     * Get current state
     */
    getState(): QueryState {
        return { ...this.state };
    }

    /**
     * Subscribe to state changes
     */
    subscribe(listener: (state: QueryState) => void): () => void {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    /**
     * Update state and notify listeners
     */
    private setState(updates: Partial<QueryState>): void {
        this.state = { ...this.state, ...updates };
        this.listeners.forEach(listener => listener(this.state));
    }

    /**
     * Set query text
     */
    setQueryText(text: string): void {
        this.setState({ queryText: text });
    }

    /**
     * Set query status
     */
    setQueryStatus(status: QueryState['queryStatus']): void {
        this.setState({ queryStatus: status, error: null });
    }

    /**
     * Set query results
     */
    setResults(results: any[], schema: string[], latency: number, traceId?: string): void {
        this.setState({
            results,
            schema,
            latency,
            traceId: traceId || null,
            queryStatus: 'success',
            error: null
        });
    }

    /**
     * Set query error
     */
    setError(error: string, latency: number): void {
        this.setState({
            error,
            latency,
            queryStatus: 'error',
            results: [],
            schema: []
        });
    }

    /**
     * Set trace data
     */
    setTrace(trace: any): void {
        this.setState({ trace });
    }

    /**
     * Clear state
     */
    clear(): void {
        this.setState({
            queryText: '',
            queryStatus: 'idle',
            results: [],
            schema: [],
            trace: null,
            traceId: null,
            latency: 0,
            error: null
        });
    }
}

// Singleton instance
export const queryStore = new QueryStore();

