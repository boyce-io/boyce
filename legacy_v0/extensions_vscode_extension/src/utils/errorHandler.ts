/**
 * Error Handler Utility
 * 
 * Converts technical database errors into user-friendly messages with actionable suggestions.
 */

export interface FriendlyError {
    title: string;
    message: string;
    suggestions: string[];
    originalError: string;
    severity: 'error' | 'warning' | 'info';
}

export class ErrorHandler {
    /**
     * Convert any error into a friendly, actionable message
     */
    static handleError(error: any, context?: string): FriendlyError {
        const errorMsg = error?.message || error?.error || String(error);
        
        // Try to match known error patterns
        if (this.isPermissionError(errorMsg)) {
            return this.permissionError(errorMsg, context);
        }
        
        if (this.isNotFoundError(errorMsg)) {
            return this.notFoundError(errorMsg, context);
        }
        
        if (this.isSyntaxError(errorMsg)) {
            return this.syntaxError(errorMsg, context);
        }
        
        if (this.isConnectionError(errorMsg)) {
            return this.connectionError(errorMsg, context);
        }
        
        if (this.isTimeoutError(errorMsg)) {
            return this.timeoutError(errorMsg, context);
        }
        
        if (this.isDataTypeError(errorMsg)) {
            return this.dataTypeError(errorMsg, context);
        }
        
        if (this.isConstraintError(errorMsg)) {
            return this.constraintError(errorMsg, context);
        }
        
        // Generic error fallback
        return this.genericError(errorMsg, context);
    }

    /**
     * Format error for display
     */
    static formatForDisplay(friendlyError: FriendlyError): string {
        let formatted = `${this.getIcon(friendlyError.severity)} ${friendlyError.title}\n\n`;
        formatted += `${friendlyError.message}\n\n`;
        
        if (friendlyError.suggestions.length > 0) {
            formatted += `💡 Suggestions:\n`;
            friendlyError.suggestions.forEach((suggestion, i) => {
                formatted += `  ${i + 1}. ${suggestion}\n`;
            });
            formatted += `\n`;
        }
        
        formatted += `ℹ️  Technical Details:\n${friendlyError.originalError}`;
        
        return formatted;
    }

    /**
     * Get emoji icon for severity
     */
    private static getIcon(severity: 'error' | 'warning' | 'info'): string {
        switch (severity) {
            case 'error': return '❌';
            case 'warning': return '⚠️';
            case 'info': return 'ℹ️';
        }
    }

    // Error type detection methods
    
    private static isPermissionError(msg: string): boolean {
        return /permission denied|access denied|unauthorized|insufficient privileges/i.test(msg);
    }
    
    private static isNotFoundError(msg: string): boolean {
        return /does not exist|not found|unknown|no such/i.test(msg);
    }
    
    private static isSyntaxError(msg: string): boolean {
        return /syntax error|parse error|invalid syntax|unexpected/i.test(msg);
    }
    
    private static isConnectionError(msg: string): boolean {
        return /connection|could not connect|refused|unreachable|network/i.test(msg);
    }
    
    private static isTimeoutError(msg: string): boolean {
        return /timeout|timed out|time limit exceeded/i.test(msg);
    }
    
    private static isDataTypeError(msg: string): boolean {
        return /type mismatch|invalid type|cannot convert|incompatible types/i.test(msg);
    }
    
    private static isConstraintError(msg: string): boolean {
        return /constraint|foreign key|unique|primary key|check constraint/i.test(msg);
    }

    // Friendly error builders
    
    private static permissionError(originalError: string, context?: string): FriendlyError {
        return {
            title: 'Permission Denied',
            message: `You don't have permission to ${context || 'perform this operation'}.`,
            suggestions: [
                'Check if you have the required privileges (SELECT, INSERT, UPDATE, etc.)',
                'Verify you\'re connected with the correct user account',
                'Ask your database administrator for access',
                'Try using a different schema or table'
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static notFoundError(originalError: string, context?: string): FriendlyError {
        // Try to extract what wasn't found
        const tableMatch = originalError.match(/table "?([a-zA-Z0-9_\.]+)"?/i);
        const columnMatch = originalError.match(/column "?([a-zA-Z0-9_]+)"?/i);
        
        let itemType = 'item';
        let itemName = '';
        
        if (tableMatch) {
            itemType = 'table';
            itemName = tableMatch[1];
        } else if (columnMatch) {
            itemType = 'column';
            itemName = columnMatch[1];
        }
        
        return {
            title: `${itemType.charAt(0).toUpperCase() + itemType.slice(1)} Not Found`,
            message: itemName 
                ? `The ${itemType} "${itemName}" doesn't exist in the database.`
                : `The requested ${itemType} doesn't exist.`,
            suggestions: [
                'Check the spelling and case sensitivity',
                'Verify the schema name (e.g., schema.table)',
                'Use the schema browser to find the correct name',
                'Make sure you\'re connected to the right database',
                `Try: SELECT * FROM information_schema.${itemType}s`
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static syntaxError(originalError: string, context?: string): FriendlyError {
        // Try to extract where the syntax error occurred
        const positionMatch = originalError.match(/at position (\d+)|near "([^"]+)"/i);
        let hint = '';
        
        if (positionMatch) {
            hint = `The error is ${positionMatch[1] ? `at position ${positionMatch[1]}` : `near "${positionMatch[2]}"`}.`;
        }
        
        return {
            title: 'SQL Syntax Error',
            message: `There's a syntax error in your SQL query. ${hint}`,
            suggestions: [
                'Check for missing commas, parentheses, or quotes',
                'Verify SQL keyword spelling (SELECT, FROM, WHERE, etc.)',
                'Use the format query command (Shift+Alt+F)',
                'Make sure string values are wrapped in quotes',
                'Check that all opening brackets have closing brackets',
                'Try breaking the query into smaller parts to isolate the issue'
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static connectionError(originalError: string, context?: string): FriendlyError {
        return {
            title: 'Connection Error',
            message: 'Could not connect to the database server.',
            suggestions: [
                'Check your internet connection',
                'Verify the database host and port in Settings',
                'Confirm the database server is running',
                'Check if a firewall is blocking the connection',
                'Try refreshing the connection (Cmd+Shift+P → "DataShark: Connect Database")',
                'Verify your credentials are correct'
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static timeoutError(originalError: string, context?: string): FriendlyError {
        return {
            title: 'Query Timeout',
            message: 'The query took too long to execute and was cancelled.',
            suggestions: [
                'Try adding a LIMIT clause to reduce result size',
                'Add a WHERE clause to filter rows',
                'Check if the table is very large',
                'Consider adding indexes to improve query performance',
                'Break complex queries into smaller parts',
                'Increase the timeout setting in Settings (if available)'
            ],
            originalError,
            severity: 'warning'
        };
    }
    
    private static dataTypeError(originalError: string, context?: string): FriendlyError {
        return {
            title: 'Data Type Mismatch',
            message: 'There\'s a data type incompatibility in your query.',
            suggestions: [
                'Check that you\'re comparing compatible data types',
                'Use CAST() to convert between types explicitly',
                'Verify that string values are in quotes',
                'Check that numbers aren\'t in quotes',
                'Example: CAST(column AS INTEGER) or column::INTEGER'
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static constraintError(originalError: string, context?: string): FriendlyError {
        let specificMessage = 'A database constraint was violated.';
        let specificSuggestions: string[] = [];
        
        if (/foreign key/i.test(originalError)) {
            specificMessage = 'Foreign key constraint violation: The referenced record doesn\'t exist.';
            specificSuggestions = [
                'Make sure the referenced record exists in the parent table',
                'Check the foreign key value you\'re inserting/updating',
                'Verify the relationship between tables is correct'
            ];
        } else if (/unique/i.test(originalError)) {
            specificMessage = 'Unique constraint violation: This value already exists.';
            specificSuggestions = [
                'Check if a record with this value already exists',
                'Use UPDATE instead of INSERT if you want to modify existing data',
                'Remove duplicate values from your data'
            ];
        } else if (/primary key/i.test(originalError)) {
            specificMessage = 'Primary key violation: Duplicate or null primary key value.';
            specificSuggestions = [
                'Ensure the primary key value is unique',
                'Don\'t insert NULL into primary key columns',
                'Let the database auto-generate the primary key if possible'
            ];
        }
        
        return {
            title: 'Constraint Violation',
            message: specificMessage,
            suggestions: specificSuggestions.length > 0 ? specificSuggestions : [
                'Review the table\'s constraints',
                'Check the data you\'re trying to insert/update',
                'Read the specific constraint error message carefully'
            ],
            originalError,
            severity: 'error'
        };
    }
    
    private static genericError(originalError: string, context?: string): FriendlyError {
        return {
            title: 'Query Failed',
            message: context 
                ? `An error occurred while ${context}.`
                : 'An error occurred while executing your query.',
            suggestions: [
                'Review the technical details below',
                'Check the DataShark documentation',
                'Try simplifying your query to isolate the issue',
                'Ask for help in your team\'s database channel'
            ],
            originalError,
            severity: 'error'
        };
    }

    /**
     * Get quick fix suggestions for common errors
     */
    static getQuickFixes(error: string): string[] {
        const fixes: string[] = [];
        
        if (/permission/i.test(error)) {
            fixes.push('Grant privileges: GRANT SELECT ON table TO user');
        }
        
        if (/does not exist/i.test(error)) {
            fixes.push('List tables: SELECT * FROM information_schema.tables');
        }
        
        if (/syntax error.*comma/i.test(error)) {
            fixes.push('Add missing comma in column list');
        }
        
        if (/timeout/i.test(error)) {
            fixes.push('Add LIMIT clause: SELECT * FROM table LIMIT 100');
        }
        
        return fixes;
    }

    /**
     * Extract helpful context from error message
     */
    static extractContext(error: string): { [key: string]: string } {
        const context: { [key: string]: string } = {};
        
        // Extract table name
        const tableMatch = error.match(/table "?([a-zA-Z0-9_\.]+)"?/i);
        if (tableMatch) {
            context.table = tableMatch[1];
        }
        
        // Extract column name
        const columnMatch = error.match(/column "?([a-zA-Z0-9_]+)"?/i);
        if (columnMatch) {
            context.column = columnMatch[1];
        }
        
        // Extract line number
        const lineMatch = error.match(/line (\d+)/i);
        if (lineMatch) {
            context.line = lineMatch[1];
        }
        
        // Extract position
        const posMatch = error.match(/position (\d+)/i);
        if (posMatch) {
            context.position = posMatch[1];
        }
        
        return context;
    }

    /**
     * Check if error is recoverable (user can fix it)
     */
    static isRecoverable(error: string): boolean {
        // These errors can typically be fixed by the user
        const recoverablePatterns = [
            /syntax error/i,
            /does not exist/i,
            /permission denied/i,
            /type mismatch/i,
            /constraint/i
        ];
        
        return recoverablePatterns.some(pattern => pattern.test(error));
    }

    /**
     * Check if error requires admin intervention
     */
    static requiresAdmin(error: string): boolean {
        const adminPatterns = [
            /permission denied/i,
            /insufficient privileges/i,
            /access denied/i
        ];
        
        return adminPatterns.some(pattern => pattern.test(error));
    }
}
















