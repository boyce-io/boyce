import * as path from "path";
import * as vscode from "vscode";
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node";

let client: LanguageClient | undefined;

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const dataSharkCorePath = path.join(
    context.extensionPath,
    "..",
    "DataShark_Core"
  );

  const serverOptions: ServerOptions = {
    command: "python3",
    args: ["-m", "src.interface.server"],
    options: { cwd: dataSharkCorePath },
  };

  const clientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file", language: "sql" }],
  };

  client = new LanguageClient(
    "datashark",
    "DataShark",
    serverOptions,
    clientOptions
  );

  await client.start();
}

export function deactivate(): Thenable<void> | void {
  return client?.stop();
}
