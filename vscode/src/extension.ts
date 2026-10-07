// mapcan for VS Code: starts the mapcan language server (`mapcan lsp`) for YAML files.
// The server ignores YAML files without a top-level `mapcan:` key.

import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions } from "vscode-languageclient/node";

let client: LanguageClient | undefined;
let output: vscode.LogOutputChannel | undefined;

function serverOptions(): ServerOptions {
  const config = vscode.workspace.getConfiguration("mapcan.server");
  // MAPCAN_SERVER lets the Extension Development Host use the repository's .venv.
  const command = config.get<string>("path") || process.env.MAPCAN_SERVER || "mapcan";
  const args = config.get<string[]>("args") ?? ["lsp"];
  return { command, args };
}

async function start(): Promise<void> {
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "yaml" },
      { scheme: "untitled", language: "yaml" },
    ],
    outputChannel: output,
  };
  client = new LanguageClient("mapcan", "mapcan", serverOptions(), clientOptions);
  try {
    await client.start();
  } catch (err) {
    const { command } = serverOptions() as { command: string };
    const choice = await vscode.window.showErrorMessage(
      `mapcan: could not start the language server (${command}). ` +
        'Install it with `pip install "mapcan[lsp]"` or set "mapcan.server.path".',
      "Open Settings",
      "Show Output",
    );
    if (choice === "Open Settings") {
      void vscode.commands.executeCommand("workbench.action.openSettings", "mapcan.server");
    } else if (choice === "Show Output") {
      output?.show();
    }
    client = undefined;
    console.error(err);
  }
}

async function stop(): Promise<void> {
  const c = client;
  client = undefined;
  if (c?.isRunning()) {
    await c.stop();
  }
}

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  output = vscode.window.createOutputChannel("mapcan", { log: true });
  context.subscriptions.push(
    output,
    vscode.commands.registerCommand("mapcan.restartServer", async () => {
      await stop();
      await start();
    }),
    vscode.commands.registerCommand("mapcan.showOutput", () => output?.show()),
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("mapcan.server")) {
        await stop();
        await start();
      }
    }),
  );
  await start();
}

export function deactivate(): Promise<void> {
  return stop();
}
