/**
 * Boyce Process Manager
 *
 * Spawns and manages `boyce serve --http` as a child process.
 * Auto-starts on extension activation if configured; graceful shutdown on deactivate.
 */

import * as vscode from "vscode";
import * as child_process from "child_process";

export class BoyceProcess {
    private proc: child_process.ChildProcess | undefined;
    private outputChannel: vscode.OutputChannel;
    private _isRunning = false;

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel("Boyce Server");
    }

    get isRunning(): boolean {
        return this._isRunning;
    }

    /**
     * Start `boyce serve --http` if not already running.
     * Checks /health first — if an existing server responds, skip spawning.
     */
    async start(): Promise<boolean> {
        if (this._isRunning) {
            return true;
        }

        const baseUrl = vscode.workspace
            .getConfiguration("boyce")
            .get<string>("serverUrl", "http://localhost:8741");

        // Check if server is already running externally
        if (await this.healthCheck(baseUrl)) {
            this._isRunning = true;
            this.outputChannel.appendLine(
                `Boyce server already running at ${baseUrl}`,
            );
            return true;
        }

        // Parse port from URL
        const url = new URL(baseUrl);
        const port = url.port || "8741";

        // Spawn child process
        this.outputChannel.appendLine(
            `Starting Boyce server on port ${port}...`,
        );

        this.proc = child_process.spawn(
            "boyce",
            ["serve", "--http", "--port", port],
            {
                cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
                env: { ...process.env },
                stdio: ["ignore", "pipe", "pipe"],
            },
        );

        // Pipe stdout/stderr to output channel
        this.proc.stdout?.on("data", (data: Buffer) => {
            this.outputChannel.appendLine(data.toString().trimEnd());
        });

        this.proc.stderr?.on("data", (data: Buffer) => {
            this.outputChannel.appendLine(data.toString().trimEnd());
        });

        this.proc.on("error", (err: Error) => {
            this._isRunning = false;
            this.outputChannel.appendLine(`Server error: ${err.message}`);
            vscode.window.showErrorMessage(
                `Boyce server failed to start: ${err.message}. ` +
                `Is boyce installed? (pip install boyce)`,
            );
        });

        this.proc.on("exit", (code: number | null) => {
            this._isRunning = false;
            this.outputChannel.appendLine(
                `Boyce server exited with code ${code}`,
            );
        });

        // Wait for server to become healthy (up to 10s)
        const healthy = await this.waitForHealthy(baseUrl, 10_000);
        if (healthy) {
            this._isRunning = true;
            this.outputChannel.appendLine("Boyce server is ready.");
        } else {
            this.outputChannel.appendLine(
                "Boyce server did not become healthy within 10s.",
            );
            vscode.window.showWarningMessage(
                "Boyce server started but is not responding on /health. " +
                "Check the Boyce Server output channel for details.",
            );
        }

        return this._isRunning;
    }

    /**
     * Gracefully stop the child process.
     */
    stop(): void {
        if (!this.proc) {
            return;
        }

        this.outputChannel.appendLine("Stopping Boyce server...");
        this.proc.kill("SIGTERM");

        // Force kill after 3s if still alive
        const forceKillTimer = setTimeout(() => {
            if (this.proc && !this.proc.killed) {
                this.proc.kill("SIGKILL");
            }
        }, 3000);

        this.proc.on("exit", () => {
            clearTimeout(forceKillTimer);
        });

        this.proc = undefined;
        this._isRunning = false;
    }

    /**
     * Single health check — GET /health, returns true if 200.
     */
    private async healthCheck(baseUrl: string): Promise<boolean> {
        try {
            const resp = await fetch(`${baseUrl}/health`, {
                method: "GET",
                signal: AbortSignal.timeout(2000),
            });
            return resp.ok;
        } catch {
            return false;
        }
    }

    /**
     * Poll /health until it responds or timeout expires.
     */
    private async waitForHealthy(
        baseUrl: string,
        timeoutMs: number,
    ): Promise<boolean> {
        const start = Date.now();
        while (Date.now() - start < timeoutMs) {
            if (await this.healthCheck(baseUrl)) {
                return true;
            }
            await new Promise((r) => setTimeout(r, 500));
        }
        return false;
    }

    dispose(): void {
        this.stop();
        this.outputChannel.dispose();
    }
}
