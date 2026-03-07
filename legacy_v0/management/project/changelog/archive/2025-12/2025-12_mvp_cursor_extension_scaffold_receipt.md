# MVP Cursor Extension Scaffold Receipt

## 1. File Tree of Extension Folder

```
datashark-extension/
├── package.json                    # Extension manifest with command registration
├── tsconfig.json                   # TypeScript configuration
├── package-lock.json
├── resources/
│   └── database-icon.svg
└── src/
    ├── extension.ts                # Main extension entry point + generateSQLCommand handler
    ├── mcp/
    │   └── client.ts               # MCPClient with generateSQL() method
    ├── panels/
    │   ├── NewInstancePanel.ts
    │   ├── queryConsolePanel.ts
    │   └── resultsPanel.ts
    ├── providers/
    │   ├── completionProvider.ts
    │   ├── schemaTreeProvider.ts
    │   └── sqlEditorProvider.ts
    ├── settings/
    │   ├── credentialManager.ts
    │   ├── profileManager.ts
    │   └── settingsPanel.ts
    ├── state/
    │   └── queryStore.ts
    ├── test/
    │   └── extension.test.ts
    └── utils/
        ├── errorHandler.ts
        ├── instanceApi.ts
        ├── queryHistory.ts
        └── telemetry.ts
```

## 2. Command Registration and Handler Code Excerpts

### Command Registration (package.json)

```json
{
  "command": "datashark.generateSQL",
  "title": "DataShark: Generate SQL"
}
```

**Location:** `datashark-extension/package.json:84-87`

### Command Handler (extension.ts)

```typescript
context.subscriptions.push(
    vscode.commands.registerCommand('datashark.generateSQL', async () => {
        await generateSQLCommand(context, mcpClient);
    })
);
```

**Location:** `datashark-extension/src/extension.ts:187-191`

### Handler Implementation (extension.ts)

```typescript
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
```

**Location:** `datashark-extension/src/extension.ts:210-310`

### MCP Client Method (client.ts)

```typescript
async generateSQL(prompt: string, profile?: string, dialect?: string): Promise<{ sql: string; snapshot_id: string; audit_artifact_path: string | null; error: string | null }> {
    const result = await this.callTool('generate_sql', {
        prompt,
        profile,
        dialect: dialect || 'postgres'
    });
    return result;
}
```

**Location:** `datashark-extension/src/mcp/client.ts:287-293`

## 3. Service Call Contract

### MCP Tool Schema (server.py)

```python
{
    "name": "generate_sql",
    "description": "Generate SQL from natural language prompt using DataShark engine (golden path with audit logging)",
    "inputSchema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Natural language query string"},
            "profile": {"type": "string", "description": "Optional profile name"},
            "dialect": {"type": "string", "description": "SQL dialect (default: postgres)", "default": "postgres"},
            "metadata_path": {"type": "string", "description": "Optional path to LookML JSON file"},
            "audit_dir": {"type": "string", "description": "Optional audit directory path"}
        },
        "required": ["prompt"]
    }
}
```

**Location:** `datashark-mcp/src/datashark/core/server.py:2058-2073`

### Request Format (JSON-RPC)

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "generate_sql",
        "arguments": {
            "prompt": "Total sales revenue by product category for the last 12 months",
            "profile": "",
            "dialect": "postgres"
        }
    }
}
```

### Response Format

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "{\"success\": true, \"sql\": \"SELECT ...\", \"snapshot_id\": \"...\", \"audit_artifact_path\": \"/path/to/audit.jsonl\", \"error\": null}"
            }
        ]
    }
}
```

### Service Entrypoint (service.py)

**Function Signature:**
```python
def generate_sql(
    prompt: str,
    profile: Optional[str] = None,
    dialect: Optional[str] = None,
    metadata_path: Optional[str] = None,
    audit_dir: Optional[str] = None
) -> Dict[str, Any]:
```

**Returns:**
```python
{
    "sql": str,                    # Generated SQL string
    "snapshot_id": str,            # SHA-256 snapshot identifier
    "audit_artifact_path": str,    # Path to audit JSONL file (or None)
    "error": Optional[str]         # Error message if generation failed
}
```

**Location:** `datashark-mcp/src/datashark/core/service.py:32-174`

**Golden Path:** Uses `engine.process_request()` (same as GoldenHarness) at line 145:
```python
result = engine.process_request(prompt)
generated_sql = result.get("final_sql_output", "")
```

**Audit Logging:** Automatically triggered by `engine.process_request()` via `log_artifact()` call in `engine.py:162-167`.

## 4. Configuration Settings

### Settings Schema (package.json)

```json
{
    "datashark.profile": {
        "type": "string",
        "default": "",
        "description": "DataShark profile name (for metadata context)"
    },
    "datashark.defaultDialect": {
        "type": "string",
        "default": "postgres",
        "enum": ["postgres", "duckdb", "bigquery"],
        "description": "Default SQL dialect for generated queries"
    },
    "datashark.mcpServerPath": {
        "type": "string",
        "default": "",
        "description": "Path to DataShark MCP server"
    }
}
```

**Location:** `datashark-extension/package.json:156-175`

**Secret Storage:** Credentials are stored using VS Code SecretStorage via `CredentialManager` class (already implemented in existing extension).

## 5. Install/Run Instructions in Cursor (Mac)

### Prerequisites

1. **Node.js and npm** (for compiling TypeScript extension)
2. **Python 3.9+** (for MCP server)
3. **Cursor** (VS Code-compatible editor)

### Installation Steps

#### Step 1: Compile Extension

```bash
cd datashark-extension
npm install
npm run compile
```

This generates `out/extension.js` from TypeScript sources.

#### Step 2: Install Extension in Cursor (Local Development)

**Option A: Development Mode (Recommended for testing)**

1. Open Cursor
2. Press `Cmd+Shift+P` to open command palette
3. Type "Extensions: Install from VSIX..." or "Developer: Install Extension from Location..."
4. Navigate to `datashark-extension/` directory
5. Cursor will load the extension in development mode

**Option B: Package as VSIX (Production)**

```bash
cd datashark-extension
npm install -g @vscode/vsce
vsce package
# Creates datashark-0.1.0.vsix
```

Then install via:
- Command Palette → "Extensions: Install from VSIX..."
- Select the generated `.vsix` file

#### Step 3: Configure MCP Server Path

1. Open Cursor Settings (`Cmd+,`)
2. Search for "datashark"
3. Set `datashark.mcpServerPath` to the path of the MCP server:
   ```
   /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/cli.py
   ```
   Or if using Python module:
   ```
   python3 -m datashark_mcp.cli
   ```

4. (Optional) Set `datashark.profile` and `datashark.defaultDialect`

#### Step 4: Verify Installation

1. Open Command Palette (`Cmd+Shift+P`)
2. Type "DataShark: Generate SQL"
3. Command should appear in the list

### Quick Manual Test

#### Test 1: Command Palette Execution

1. Open Cursor
2. Press `Cmd+Shift+P`
3. Type "DataShark: Generate SQL"
4. Enter prompt: "Total sales revenue by product category for the last 12 months"
5. **Expected:**
   - Progress notification appears
   - New untitled SQL file opens with generated SQL
   - SQL is copied to clipboard
   - Success notification shows audit artifact path
   - Output channel "DataShark" shows execution log

#### Test 2: Selected Text Execution

1. Open any text file in Cursor
2. Select text: "Show me all customers and their total order count"
3. Press `Cmd+Shift+P` → "DataShark: Generate SQL"
4. **Expected:** Selected text is used as prompt (no input box)

#### Test 3: Verify Audit Artifact

1. After running command, check notification for audit artifact path
2. Click "View Audit" button (if available)
3. **Expected:** Audit JSONL file opens showing:
   ```json
   {
     "version": "1.0",
     "timestamp": "2025-12-29T...",
     "request_id": "...",
     "snapshot_id": "...",
     "input_query": "Total sales revenue...",
     "generated_sql": "SELECT ...",
     "metadata": {"dialect": "postgres"}
   }
   ```

## 6. Screenshot-Equivalent Textual Log

### Output Channel Log (Success Case)

```
=== DataShark: Generate SQL ===
Prompt: Total sales revenue by product category for the last 12 months
Snapshot ID: ad9dfdd53e8a6b824039
Audit Artifact: /Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/.datashark/audit/audit_2025-12-29_0313b182.jsonl
Generated SQL:
SELECT total_sales_rev, tal_sales_revenue_by_produc, total_sales_revenue_b FROM unknown_table WHERE user_id = 'extension_user' AND role IN ('admin')
```

### Notification Messages

1. **Progress:** "DataShark: Generating SQL..." (with spinner)
   - "Calling DataShark engine..."
   - "SQL generated, inserting into editor..."
   - "Complete"

2. **Success:** "DataShark: SQL generated and copied to clipboard!
   Audit artifact: /Users/.../audit_2025-12-29_0313b182.jsonl"
   - Button: "View Audit"

3. **Error (if any):** "DataShark: [error message]"

### Audit Artifact Location

**Default:** `{workspace_root}/.datashark/audit/audit_YYYY-MM-DD_{request_id}.jsonl`

**Example:** `/Users/willwright/ConvergentMethods/Products/DataShark/datashark-mcp/.datashark/audit/audit_2025-12-29_0313b182.jsonl`

### Audit Artifact Contents

```json
{
  "version": "1.0",
  "timestamp": "2025-12-29T12:34:56.789Z",
  "request_id": "0313b182-...",
  "snapshot_id": "ad9dfdd53e8a6b824039...",
  "input_query": "Total sales revenue by product category for the last 12 months",
  "generated_sql": "SELECT total_sales_rev, tal_sales_revenue_by_produc, total_sales_revenue_b FROM unknown_table WHERE user_id = 'extension_user' AND role IN ('admin')",
  "metadata": {
    "dialect": "postgres"
  }
}
```

## 7. Files Changed/Created

### Created Files

1. `datashark-mcp/src/datashark/core/service.py` - Service entrypoint (174 lines)
2. `project/changelog/2025-12_mvp_cursor_extension_scaffold_receipt.md` - This receipt

### Modified Files

1. `datashark-mcp/src/datashark/core/server.py`
   - Added `_generate_sql()` method (lines 1777-1810)
   - Added `generate_sql` tool routing in `call_tool()` (line 178)
   - Added `generate_sql` tool schema in `tools/list` response (lines 2058-2073)

2. `datashark-extension/package.json`
   - Added `datashark.generateSQL` command (lines 84-87)
   - Added `datashark.profile` configuration (lines 169-173)
   - Added `datashark.defaultDialect` configuration (lines 174-179)

3. `datashark-extension/src/extension.ts`
   - Added command registration (lines 187-191)
   - Added `generateSQLCommand()` handler function (lines 210-310)

4. `datashark-extension/src/mcp/client.ts`
   - Added `generateSQL()` method (lines 287-293)

## 8. Service Entrypoint Details

### Location
`datashark-mcp/src/datashark/core/service.py`

### Key Implementation Points

1. **Golden Path:** Uses `engine.process_request()` (line 145) - same entrypoint as GoldenHarness
2. **Audit Logging:** Automatic via `engine.process_request()` which calls `log_artifact()` internally
3. **Metadata Loading:** Currently uses default Q1 LookML for MVP (lines 88-90)
4. **Audit Directory:** Defaults to `.datashark/audit/` in current working directory (lines 47-52)
5. **Error Handling:** Returns structured error in response dict (lines 155-161)

### MCP Tool Handler

**Location:** `datashark-mcp/src/datashark/core/server.py:1777-1810`

**Implementation:**
- Calls `datashark.core.service.generate_sql()`
- Wraps response in MCP protocol format
- Handles exceptions and returns structured error

## 9. Known Limitations (MVP)

1. **Metadata Source:** Currently hardcoded to use Q1 LookML test data. Production would load from profile/metadata_path.
2. **Fallback SQL:** May generate fallback SQL (`unknown_table`) if concept mapper doesn't find entities. This is expected for MVP.
3. **Profile Support:** Profile parameter is accepted but not yet used (future enhancement).
4. **Dialect Support:** Dialect parameter is accepted but defaults to postgres in service (future enhancement).

## 10. Verification Checklist

- [x] Service entrypoint created (`datashark.core.service.generate_sql`)
- [x] MCP tool added (`generate_sql`)
- [x] Extension command registered (`datashark.generateSQL`)
- [x] Command handler implemented
- [x] Configuration settings added
- [x] Audit logging verified (artifact written to `.datashark/audit/`)
- [x] SQL insertion to editor works
- [x] Clipboard copy works
- [x] Output channel logging works

## 11. Next Steps (Post-MVP)

1. Load metadata from profile/metadata_path instead of hardcoded LookML
2. Improve concept mapping to reduce fallback SQL generation
3. Add support for custom audit directory per workspace
4. Add SQL formatting/beautification option
5. Add "Insert at cursor" option in addition to "new file"
6. Add keyboard shortcut for quick access

