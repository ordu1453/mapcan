// mapcan for VS Code: starts the mapcan language server (`mapcan lsp`) for YAML files and shows
// the Map view. The server ignores YAML files without a top-level `mapcan:` key.

import * as vscode from "vscode";
import { LanguageClient, LanguageClientOptions, ServerOptions } from "vscode-languageclient/node";
import { registerTreeActions } from "./actions";
import { ChangesPanel } from "./changes";
import { ExportView } from "./export";
import { NodeForm } from "./form";
import { HistoryTree, registerHistory } from "./history";
import { ChangeMarks } from "./marks";
import { registerPreview } from "./preview";
import { isMap, MapTree, revealNode } from "./tree";

let client: LanguageClient | undefined;
let output: vscode.LogOutputChannel | undefined;
let tree: MapTree | undefined;
let form: NodeForm | undefined;

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
export async function activate(
  context: vscode.ExtensionContext,
): Promise<{ tree: MapTree; form: NodeForm; history: HistoryTree; changes: ChangesPanel }> {
  output = vscode.window.createOutputChannel("mapcan", { log: true });
  tree = new MapTree(vscode.Uri.joinPath(context.extensionUri, "media"), () => client);
  const view = vscode.window.createTreeView("mapcan.map", { treeDataProvider: tree, showCollapseAll: true });
  tree.attach(view);
  form = new NodeForm(context.extensionUri, tree, () => client, view);
  const exportView = new ExportView(context, tree, () => client);
  const history = new HistoryTree(tree);
  const changes = new ChangesPanel(context.extensionUri);
  const historyView = vscode.window.createTreeView(HistoryTree.viewId, { treeDataProvider: history });
  history.attach(historyView);
  const marks = new ChangeMarks(tree, history, () => client);
  context.subscriptions.push(
    output,
    tree,
    view,
    form,
    exportView,
    history,
    historyView,
    marks,
    changes,
    vscode.window.registerWebviewViewProvider(NodeForm.viewId, form),
    vscode.window.registerWebviewViewProvider(ExportView.viewId, exportView),
    vscode.commands.registerCommand("mapcan.restartServer", async () => {
      await stop();
      await start();
    }),
    vscode.commands.registerCommand("mapcan.showOutput", () => output?.show()),
    vscode.commands.registerCommand("mapcan.export", () => exportView.reveal()),
    vscode.commands.registerCommand("mapcan.closeForm", () => form?.close()),
    vscode.commands.registerCommand("mapcan.revealFormNode", () => form?.reveal()),
    vscode.commands.registerCommand("mapcan.revealNode", revealNode),
    vscode.commands.registerCommand("mapcan.openMap", openMap),
    vscode.workspace.onDidChangeConfiguration(async (e) => {
      if (e.affectsConfiguration("mapcan.server")) {
        await stop();
        await start();
      }
    }),
  );
  registerTreeActions(context, tree, form, () => client);
  const showChanges = registerPreview(context, () => client, currentMap, changes);
  registerHistory(context, history, currentMap, showChanges, () => client);
  await start();
  return { tree, form, history, changes };
}

export function deactivate(): Promise<void> {
  return stop();
}
