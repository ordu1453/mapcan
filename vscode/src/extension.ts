// mapcan for VS Code: starts the mapcan language server (`mapcan lsp`) for YAML files and shows
// the Map view. The server ignores YAML files without a top-level `mapcan:` key.

import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions } from "vscode-languageclient/node";
import { exportMap } from "./export";
import { isMap, MapTree, revealNode } from "./tree";

let client: LanguageClient | undefined;
let output: vscode.LogOutputChannel | undefined;
let tree: MapTree | undefined;

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
  await tree?.refresh();
}

async function stop(): Promise<void> {
  const c = client;
  client = undefined;
  if (c?.isRunning()) {
    await c.stop();
  }
}

/** The map to act on: the active editor if it is a map, else the one shown in the Map view. */
function currentMap(): vscode.Uri | undefined {
  const doc = vscode.window.activeTextEditor?.document;
  return isMap(doc) ? doc.uri : tree?.mapUri;
}

async function openMap(): Promise<void> {
  const picked = await vscode.window.showOpenDialog({
    canSelectMany: false,
    filters: { "mapcan map": ["yaml", "yml"] },
    openLabel: "Open Map",
  });
  if (picked?.[0]) {
    await vscode.window.showTextDocument(picked[0]);
  }
}

/** The returned object is used by the integration tests. */
export async function activate(context: vscode.ExtensionContext): Promise<{ tree: MapTree }> {
  output = vscode.window.createOutputChannel("mapcan", { log: true });
  tree = new MapTree(vscode.Uri.joinPath(context.extensionUri, "media"), () => client);
  const view = vscode.window.createTreeView("mapcan.map", { treeDataProvider: tree, showCollapseAll: true });
  tree.attach(view);
  context.subscriptions.push(
    output,
    tree,
    view,
    vscode.commands.registerCommand("mapcan.restartServer", async () => {
      await stop();
      await start();
    }),
    vscode.commands.registerCommand("mapcan.showOutput", () => output?.show()),
    vscode.commands.registerCommand("mapcan.export", () => exportMap(context, client, currentMap())),
    vscode.commands.registerCommand("mapcan.revealNode", revealNode),
    vscode.commands.registerCommand("mapcan.openMap", openMap),
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("mapcan.server")) {
        await stop();
        await start();
      }
    }),
  );
  await start();
  return { tree };
}

export function deactivate(): Promise<void> {
  return stop();
}
