/**
 * Chat Panel
 *
 * Webview panel for conversational NL → SQL interaction.
 * Sends user messages to the Boyce /chat endpoint and renders responses.
 */

import * as vscode from "vscode";
import { BoyceClient } from "../client";
import type { ChatMessage } from "../types";

export class ChatPanel {
    private static instance: ChatPanel | undefined;
    private panel: vscode.WebviewPanel | undefined;
    private disposables: vscode.Disposable[] = [];
    private history: ChatMessage[] = [];

    private constructor(
        private context: vscode.ExtensionContext,
        private client: BoyceClient,
    ) {}

    static getInstance(
        context: vscode.ExtensionContext,
        client: BoyceClient,
    ): ChatPanel {
        if (!ChatPanel.instance) {
            ChatPanel.instance = new ChatPanel(context, client);
        }
        return ChatPanel.instance;
    }

    show(): void {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Beside);
            return;
        }

        this.panel = vscode.window.createWebviewPanel(
            "boyceChat",
            "Boyce Chat",
            vscode.ViewColumn.Beside,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            },
        );

        this.panel.webview.html = this.getHtml();

        this.panel.webview.onDidReceiveMessage(
            (msg) => this.handleMessage(msg),
            null,
            this.disposables,
        );

        this.panel.onDidDispose(
            () => {
                this.panel = undefined;
            },
            null,
            this.disposables,
        );
    }

    private async handleMessage(msg: {
        command: string;
        text?: string;
    }): Promise<void> {
        if (msg.command === "send" && msg.text) {
            await this.sendMessage(msg.text);
        }
        if (msg.command === "runSql" && msg.text) {
            await this.runSql(msg.text);
        }
    }

    private async sendMessage(text: string): Promise<void> {
        // Add user message to history
        this.history.push({
            role: "user",
            content: text,
            timestamp: new Date(),
        });
        this.postToWebview("addMessage", { role: "user", content: text });

        // Show typing indicator
        this.postToWebview("setLoading", { loading: true });

        try {
            const response = await this.client.chat(text);

            if (response.error) {
                this.postToWebview("addMessage", {
                    role: "assistant",
                    content: `Error: ${response.error.message}`,
                });
                return;
            }

            const assistantMsg: ChatMessage = {
                role: "assistant",
                content: response.reply,
                timestamp: new Date(),
                toolUsed: response.tool_used,
            };

            // Extract SQL if present in the response data
            const data = response.data as Record<string, unknown>;
            if (data?.sql) {
                assistantMsg.sql = data.sql as string;
            }

            this.history.push(assistantMsg);
            this.postToWebview("addMessage", {
                role: "assistant",
                content: response.reply,
                sql: assistantMsg.sql,
                toolUsed: response.tool_used,
            });
        } catch (err: unknown) {
            const errMsg = err instanceof Error ? err.message : String(err);
            this.postToWebview("addMessage", {
                role: "assistant",
                content: `Connection error: ${errMsg}`,
            });
        } finally {
            this.postToWebview("setLoading", { loading: false });
        }
    }

    private async runSql(sql: string): Promise<void> {
        this.postToWebview("setLoading", { loading: true });

        try {
            const result = await this.client.query(sql);
            if (result.error) {
                this.postToWebview("addMessage", {
                    role: "assistant",
                    content: `Query error: ${result.error}`,
                });
            } else {
                // Format results as a simple table
                const cols = result.columns || [];
                const rows = result.rows || [];
                let table = cols.join(" | ") + "\n" + cols.map(() => "---").join(" | ");
                for (const row of rows.slice(0, 50)) {
                    table +=
                        "\n" + cols.map((c) => String((row as Record<string, unknown>)[c] ?? "NULL")).join(" | ");
                }
                this.postToWebview("addMessage", {
                    role: "assistant",
                    content: `Results (${result.row_count} rows):\n\n\`\`\`\n${table}\n\`\`\``,
                });
            }
        } catch (err: unknown) {
            const errMsg = err instanceof Error ? err.message : String(err);
            this.postToWebview("addMessage", {
                role: "assistant",
                content: `Query failed: ${errMsg}`,
            });
        } finally {
            this.postToWebview("setLoading", { loading: false });
        }
    }

    private postToWebview(command: string, data: Record<string, unknown>): void {
        this.panel?.webview.postMessage({ command, ...data });
    }

    private getHtml(): string {
        const nonce = getNonce();

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
    <title>Boyce Chat</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        #messages {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
        }

        .message {
            margin-bottom: 12px;
            padding: 8px 12px;
            border-radius: 6px;
            max-width: 90%;
            word-wrap: break-word;
            white-space: pre-wrap;
        }

        .message.user {
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            margin-left: auto;
            text-align: right;
        }

        .message.assistant {
            background: var(--vscode-editor-inactiveSelectionBackground);
        }

        .message .tool-badge {
            font-size: 10px;
            opacity: 0.7;
            display: block;
            margin-top: 4px;
        }

        .message .run-sql-btn {
            margin-top: 6px;
            padding: 2px 8px;
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 11px;
        }

        .message .run-sql-btn:hover {
            background: var(--vscode-button-secondaryHoverBackground);
        }

        #loading {
            display: none;
            padding: 8px 12px;
            opacity: 0.6;
            font-style: italic;
        }

        #input-area {
            display: flex;
            gap: 6px;
            padding: 8px 12px;
            border-top: 1px solid var(--vscode-panel-border);
        }

        #input-area textarea {
            flex: 1;
            padding: 6px 10px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 4px;
            font-family: var(--vscode-font-family);
            font-size: var(--vscode-font-size);
            resize: none;
            min-height: 36px;
            max-height: 120px;
        }

        #input-area button {
            padding: 6px 14px;
            background: var(--vscode-button-background);
            color: var(--vscode-button-foreground);
            border: none;
            border-radius: 4px;
            cursor: pointer;
            align-self: flex-end;
        }

        #input-area button:hover {
            background: var(--vscode-button-hoverBackground);
        }

        code, pre {
            font-family: var(--vscode-editor-font-family);
            font-size: var(--vscode-editor-font-size);
        }

        pre {
            background: var(--vscode-textCodeBlock-background);
            padding: 8px;
            border-radius: 4px;
            overflow-x: auto;
            margin: 4px 0;
        }
    </style>
</head>
<body>
    <div id="messages"></div>
    <div id="loading">Thinking...</div>
    <div id="input-area">
        <textarea id="input"
                  placeholder="Ask Boyce a question..."
                  rows="1"></textarea>
        <button id="send-btn" onclick="send()">Send</button>
    </div>

    <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();
        const messagesEl = document.getElementById('messages');
        const loadingEl = document.getElementById('loading');
        const inputEl = document.getElementById('input');

        function send() {
            const text = inputEl.value.trim();
            if (!text) return;
            vscode.postMessage({ command: 'send', text });
            inputEl.value = '';
            inputEl.style.height = '36px';
        }

        // Auto-resize textarea
        inputEl.addEventListener('input', () => {
            inputEl.style.height = '36px';
            inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
        });

        // Enter to send, Shift+Enter for newline
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
            }
        });

        function escapeHtml(text) {
            const d = document.createElement('div');
            d.textContent = text;
            return d.innerHTML;
        }

        function renderContent(text) {
            // Simple markdown: code blocks
            return escapeHtml(text).replace(
                /\`\`\`([\\s\\S]*?)\`\`\`/g,
                '<pre>$1</pre>'
            ).replace(
                /\`([^\`]+)\`/g,
                '<code>$1</code>'
            );
        }

        window.addEventListener('message', (event) => {
            const msg = event.data;

            if (msg.command === 'addMessage') {
                const div = document.createElement('div');
                div.className = 'message ' + msg.role;
                let html = renderContent(msg.content);

                if (msg.toolUsed && msg.toolUsed !== 'none') {
                    html += '<span class="tool-badge">via ' + escapeHtml(msg.toolUsed) + '</span>';
                }

                if (msg.sql) {
                    html += '<button class="run-sql-btn" data-sql="' +
                            escapeHtml(msg.sql).replace(/"/g, '&quot;') +
                            '">Run SQL</button>';
                }

                div.innerHTML = html;

                // Attach click handler for Run SQL buttons
                const btn = div.querySelector('.run-sql-btn');
                if (btn) {
                    btn.addEventListener('click', () => {
                        vscode.postMessage({ command: 'runSql', text: btn.getAttribute('data-sql') });
                    });
                }

                messagesEl.appendChild(div);
                messagesEl.scrollTop = messagesEl.scrollHeight;
            }

            if (msg.command === 'setLoading') {
                loadingEl.style.display = msg.loading ? 'block' : 'none';
            }
        });

        inputEl.focus();
    </script>
</body>
</html>`;
    }

    dispose(): void {
        this.disposables.forEach((d) => d.dispose());
        this.panel?.dispose();
        this.panel = undefined;
        ChatPanel.instance = undefined;
    }
}

function getNonce(): string {
    const chars =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let nonce = "";
    for (let i = 0; i < 32; i++) {
        nonce += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return nonce;
}
