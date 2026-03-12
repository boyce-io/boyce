/**
 * Boyce VS Code Extension — Main Entry Point
 *
 * Thin GUI over the Boyce HTTP API (boyce serve --http).
 * All LLM logic, SQL generation, and safety checks live server-side.
 * This extension never touches credentials or models directly.
 */

import * as vscode from "vscode";
import { BoyceClient } from "./client";
import { BoyceProcess } from "./process";
import { SchemaTreeProvider } from "./providers/schemaTreeProvider";
import { ChatPanel } from "./panels/chatPanel";

let client: BoyceClient;
let serverProcess: BoyceProcess;
let schemaTreeProvider: SchemaTreeProvider;
let statusBarItem: vscode.StatusBarItem;

export async function activate(
    context: vscode.ExtensionContext,
): Promise<void> {
    console.log("Boyce extension activating...");

    // Initialize HTTP client
    client = new BoyceClient();
    client.loadToken();

    // Initialize server process manager
    serverProcess = new BoyceProcess();

    // Auto-start server if configured
    const autoStart = vscode.workspace
        .getConfiguration("boyce")
        .get<boolean>("autoStart", true);

    if (autoStart) {
        await serverProcess.start();
    }

    // Schema tree sidebar
    schemaTreeProvider = new SchemaTreeProvider(client);
    vscode.window.registerTreeDataProvider(
        "boyce.schemaTree",
        schemaTreeProvider,
    );

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100,
    );
    statusBarItem.text = "$(database) Boyce";
    statusBarItem.command = "boyce.openChat";
    statusBarItem.tooltip = "Open Boyce Chat";
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // -----------------------------------------------------------------------
    // Commands
    // -----------------------------------------------------------------------

    context.subscriptions.push(
        vscode.commands.registerCommand("boyce.connect", async () => {
            const started = await serverProcess.start();
            if (started) {
                client.loadToken();
                schemaTreeProvider.refresh();
                vscode.window.showInformationMessage("Boyce: Connected");
            }
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("boyce.refreshSchema", () => {
            schemaTreeProvider.refresh();
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("boyce.openChat", () => {
            const chatPanel = ChatPanel.getInstance(context, client);
            chatPanel.show();
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("boyce.ask", async () => {
            const query = await vscode.window.showInputBox({
                prompt: "Ask Boyce a question",
                placeHolder:
                    "e.g., Total revenue by customer segment for the last 12 months",
            });
            if (!query) {
                return;
            }

            await vscode.window.withProgress(
                {
                    location: vscode.ProgressLocation.Notification,
                    title: "Boyce: Generating SQL...",
                    cancellable: false,
                },
                async () => {
                    try {
                        const result = await client.ask(query);

                        if (result.error) {
                            vscode.window.showErrorMessage(
                                `Boyce: ${result.error}`,
                            );
                            return;
                        }

                        // Open SQL in a new editor
                        const doc =
                            await vscode.workspace.openTextDocument({
                                language: "sql",
                                content: result.sql,
                            });
                        await vscode.window.showTextDocument(doc);

                        // Copy to clipboard
                        await vscode.env.clipboard.writeText(result.sql);

                        // Show validation status
                        const status = result.validation?.status ?? "unchecked";
                        let msg = `SQL generated and copied to clipboard (${status})`;
                        if (
                            result.null_trap_warnings &&
                            result.null_trap_warnings.length > 0
                        ) {
                            const w = result.null_trap_warnings[0];
                            msg += ` | NULL Trap: ${w.column} (${w.null_pct}% nulls)`;
                        }
                        vscode.window.showInformationMessage(`Boyce: ${msg}`);
                    } catch (err: unknown) {
                        const errMsg =
                            err instanceof Error ? err.message : String(err);
                        vscode.window.showErrorMessage(
                            `Boyce: ${errMsg}`,
                        );
                    }
                },
            );
        }),
    );

    context.subscriptions.push(
        vscode.commands.registerCommand("boyce.runQuery", async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage("No active SQL editor");
                return;
            }

            // Use selection or full document
            const selection = editor.selection;
            const sql = selection.isEmpty
                ? editor.document.getText()
                : editor.document.getText(selection);

            if (!sql.trim()) {
                return;
            }

            await vscode.window.withProgress(
                {
                    location: vscode.ProgressLocation.Notification,
                    title: "Boyce: Running query...",
                    cancellable: false,
                },
                async () => {
                    try {
                        const result = await client.query(sql);

                        if (result.error) {
                            vscode.window.showErrorMessage(
                                `Boyce: ${result.error}`,
                            );
                            return;
                        }

                        // Show results in output channel
                        const out =
                            vscode.window.createOutputChannel("Boyce Results");
                        out.clear();

                        const cols = result.columns || [];
                        out.appendLine(cols.join(" | "));
                        out.appendLine("-".repeat(80));

                        for (const row of result.rows || []) {
                            const r = row as Record<string, unknown>;
                            const vals = cols.map((c) =>
                                String(r[c] ?? "NULL"),
                            );
                            out.appendLine(vals.join(" | "));
                        }

                        out.appendLine("");
                        out.appendLine(`${result.row_count} rows returned`);
                        out.show();
                    } catch (err: unknown) {
                        const errMsg =
                            err instanceof Error ? err.message : String(err);
                        vscode.window.showErrorMessage(
                            `Boyce: ${errMsg}`,
                        );
                    }
                },
            );
        }),
    );

    console.log("Boyce extension activated");
}

export function deactivate(): void {
    console.log("Boyce extension deactivating...");
    serverProcess?.dispose();
}
