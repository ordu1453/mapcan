// mapcan for VS Code: starts the mapcan language server (`mapcan lsp`) and shows the Map view.
// The server is started when the first map (a YAML file with a top-level `mapcan:` key) is opened,
// and gets only maps: other YAML files never reach it. It stops when no map has been open for a while.

import * as vscode from "vscode";
import {
  DidOpenTextDocumentNotification, LanguageClient, LanguageClientOptions, Middleware, ServerOptions,
} from "vscode-languageclient/node";
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
/** The start failed: do not try (and show the error) again until the settings change or a restart. */
let failed = false;
/** Documents the server knows (sent with didOpen). */
const synced = new Set<string>();
/** How long the server keeps running with no map open. */
let idleStopMs = 5 * 60_000;
let idleTimer: NodeJS.Timeout | undefined;

function serverOptions(): ServerOptions {
  const config = vscode.workspace.getConfiguration("mapcan.server");
  // MAPCAN_SERVER lets the Extension Development Host use the repository's .venv.
  const command = config.get<string>("path") || process.env.MAPCAN_SERVER || "mapcan";
  const args = config.get<string[]>("args") ?? ["lsp"];
  return { command, args };
}

/**
 * The client syncs every YAML document (a selector cannot look at the text); the middleware sends
 * only maps. A document that becomes a map while it is edited is opened on the server then.
 */
const middleware: Middleware = {
  didOpen: async (doc, next) => {
    if (!isMap(doc)) return;
    synced.add(doc.uri.toString());
    await next(doc);
  },
  didChange: async (e, next) => {
    const uri = e.document.uri.toString();
    if (synced.has(uri)) {
      await next(e);
    } else if (isMap(e.document) && client) {
      synced.add(uri);
      await client.sendNotification(DidOpenTextDocumentNotification.type,
        client.code2ProtocolConverter.asOpenTextDocumentParams(e.document));
    }
  },
  didSave: async (doc, next) => {
    if (synced.has(doc.uri.toString())) await next(doc);
  },
  didClose: async (doc, next) => {
    if (synced.delete(doc.uri.toString())) await next(doc);
  },
  // Hover, completion, inlay hints and the rest: nothing for documents the server does not know.
  sendRequest: (type, param, token, next) => {
    const uri = (param as { textDocument?: { uri?: string } } | undefined)?.textDocument?.uri;
    return uri !== undefined && !synced.has(uri) ? Promise.resolve(null as never) : next(type, param, token);
  },
};

/** Starts the server if a map is open (or, with `force`, anyway) and it is not running yet. */
async function start(force = false): Promise<void> {
  clearTimeout(idleTimer);
  if (client || (!force && (failed || !vscode.workspace.textDocuments.some(isMap)))) return;
  failed = false;
  const clientOptions: LanguageClientOptions = {
    documentSelector: [
      { scheme: "file", language: "yaml" },
      { scheme: "untitled", language: "yaml" },
    ],
    outputChannel: output,
    middleware,
  };
  client = new LanguageClient("mapcan", "mapcan", serverOptions(), clientOptions);
  try {
    await client.start();
  } catch (err) {
    failed = true;
    const { command } = serverOptions() as { command: string };
    const choice = await vscode.window.showErrorMessage(
      `mapcan: could not start the language server (${command}). ` +
        'Install it with `uv tool install "mapcan[lsp]"` (or `pipx install "mapcan[lsp]"`) or set "mapcan.server.path".',
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

/** A map is open in an editor tab. VS Code keeps the document of a closed tab for a while (an unsaved one for
 * good), so the documents alone do not tell that the last map was closed. */
function mapInTab(): boolean {
  const open = new Set<string>();
  for (const group of vscode.window.tabGroups.all) {
    for (const tab of group.tabs) {
      const input = tab.input;
      if (input instanceof vscode.TabInputText) open.add(input.uri.toString());
      else if (input instanceof vscode.TabInputTextDiff) {
        open.add(input.original.toString());
        open.add(input.modified.toString());
      }
    }
  }
  return vscode.workspace.textDocuments.some((d) => isMap(d) && open.has(d.uri.toString()));
}

/** The last map was closed: stop the server unless a map is opened again in time. */
function scheduleIdleStop(): void {
  clearTimeout(idleTimer);
  if (!client || mapInTab()) return;
  idleTimer = setTimeout(async () => {
    if (!client || mapInTab()) return;
    output?.info("No map is open: stopping the language server.");
    await stop();
    await tree?.refresh();
  }, idleStopMs);
}

async function stop(): Promise<void> {
  clearTimeout(idleTimer);
  const c = client;
  client = undefined;
  synced.clear();
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
): Promise<{
  tree: MapTree; form: NodeForm; history: HistoryTree; changes: ChangesPanel;
  client: () => LanguageClient | undefined; setIdleStop: (ms: number) => void;
}> {
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
      await start(true);
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
        failed = false;
        await start();
      }
    }),
    vscode.workspace.onDidOpenTextDocument((doc) => isMap(doc) && start()),
    // A new file becomes a map when `mapcan:` is typed into it.
    vscode.workspace.onDidChangeTextDocument((e) => !client && isMap(e.document) && start()),
    vscode.workspace.onDidCloseTextDocument(() => scheduleIdleStop()),
    // A map whose document VS Code still keeps opens without onDidOpenTextDocument: its new tab starts the server
    vscode.window.tabGroups.onDidChangeTabs((e) => {
      if (e.opened.length && !client && mapInTab()) void start();
      else if (e.closed.length) scheduleIdleStop();
    }),
  );
  registerTreeActions(context, tree, form, () => client);
  const showChanges = registerPreview(context, () => client, currentMap, changes);
  registerHistory(context, history, currentMap, showChanges, () => client);
  await start();
  return { tree, form, history, changes, client: () => client, setIdleStop: (ms) => (idleStopMs = ms) };
}

export function deactivate(): Promise<void> {
  return stop();
}
