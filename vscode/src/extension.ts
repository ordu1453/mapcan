// mapcan for VS Code: starts the mapcan language server (`mapcan lsp`) and shows the Map view.
// The server is started when the first map (a YAML file with a top-level `mapcan:` key) is opened,
// and gets only maps: other YAML files never reach it. It stops when no map has been open for a while.

import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import {
  DidOpenTextDocumentNotification, LanguageClient, LanguageClientOptions, Middleware,
} from "vscode-languageclient/node";
import { registerTreeActions } from "./actions";
import { ChangesPanel } from "./changes";
import { ExportView } from "./export";
import { hiddenChanges, inTabs, saveTogether } from "./files";
import { NodeForm } from "./form";
import { HistoryTree, registerHistory } from "./history";
import { ChangeMarks } from "./marks";
import { registerPreview } from "./preview";
import { registerSchemas, schemaOf } from "./schema";
import { registerStarters } from "./starters";
import { registerTour } from "./tour";
import { isMap, MapTree, revealNode } from "./tree";
import { installMapcan, managedMapcan } from "./install";
import { checkForUpdate, checkServerVersion, isOlder } from "./version";

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
let extensionVersion = "";
let idleTimer: NodeJS.Timeout | undefined;

/** The command the server was last started with, and where it was found. */
let serverCommand = "mapcan";
let serverSource: ServerSource = "path";
/** The Python of the environment selected in the Python extension, when its mapcan is the server. */
let serverPython: string | undefined;
let starting: Promise<void> | undefined;
let storage: vscode.Uri | undefined;

type ServerSource = "setting" | "python" | "managed" | "path";

/** The language server's command: the setting, MAPCAN_SERVER (the Extension Development Host uses the
 * repository's .venv), mapcan in the Python environment selected in the Python extension, the mapcan the
 * extension installed, or mapcan on PATH. */
async function serverOptions(): Promise<{ command: string; args: string[]; source: ServerSource; python?: string }> {
  const config = vscode.workspace.getConfiguration("mapcan.server");
  const args = config.get<string[]>("args") ?? ["lsp"];
  const setting = config.get<string>("path") || process.env.MAPCAN_SERVER;
  if (setting) return { command: setting, args, source: "setting" };
  const env = await pythonEnvMapcan();
  if (env) return { command: env.mapcan, args, source: "python", python: env.python };
  const managed = storage && managedMapcan(storage);
  if (managed) return { command: managed, args, source: "managed" };
  return { command: "mapcan", args, source: "path" };
}

/** mapcan installed in the Python environment selected in the Python extension, if that is installed. */
async function pythonEnvMapcan(): Promise<{ mapcan: string; python: string } | undefined> {
  const ext = vscode.extensions.getExtension<PythonApi>("ms-python.python");
  if (!ext) return undefined;
  try {
    const envs = (ext.isActive ? ext.exports : await ext.activate())?.environments;
    const selected = envs?.getActiveEnvironmentPath(vscode.window.activeTextEditor?.document.uri);
    const env = selected ? await envs?.resolveEnvironment(selected) : undefined;
    const python = env?.executable?.uri?.fsPath;
    if (!python) return undefined;
    const exe = process.platform === "win32" ? "mapcan.exe" : "mapcan";
    // A venv has mapcan next to python; a conda or system Python on Windows has it in Scripts
    const mapcan = [path.join(path.dirname(python), exe), path.join(path.dirname(python), "Scripts", exe)]
      .find((p) => fs.existsSync(p));
    return mapcan ? { mapcan, python } : undefined;
  } catch {
    return undefined;
  }
}

/** The part of the Python extension's API used here. */
interface PythonApi {
  environments?: {
    getActiveEnvironmentPath(resource?: vscode.Uri): { id: string; path: string };
    resolveEnvironment(env: { id: string; path: string }): Promise<{ executable?: { uri?: vscode.Uri } } | undefined>;
  };
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
function start(force = false): Promise<void> {
  // Finding the command takes a moment: a second call meanwhile waits for the first one
  starting ??= startNow(force).finally(() => (starting = undefined));
  return starting;
}

async function startNow(force: boolean): Promise<void> {
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
  const options = await serverOptions();
  serverCommand = options.command;
  serverSource = options.source;
  serverPython = options.python;
  client = new LanguageClient("mapcan", "mapcan", { command: options.command, args: options.args }, clientOptions);
  try {
    await client.start();
    // The walkthrough's first step is done once a server runs: mapcan is installed
    void vscode.commands.executeCommand("setContext", "mapcan.serverRunning", true);
    const version = serverVersion();
    output?.info(`mapcan language server ${version ?? "(no version)"}, extension ${extensionVersion}`);
    void checkServerVersion(version);
    if (serverSource === "managed") void checkForUpdate(version);
  } catch (err) {
    failed = true;
    client = undefined;
    console.error(err);
    // Nothing was found: mapcan is not installed. Otherwise the mapcan that was found does not start.
    const missing = serverSource === "path";
    const choice = await vscode.window.showErrorMessage(
      missing
        ? "mapcan: the extension needs the mapcan tool. Install it? It is downloaded once, with Python " +
          "(about 100 MB), and serves every folder. A mapcan of your own can be chosen in \"mapcan.server.path\"."
        : `mapcan: could not start the language server (${serverCommand}).`,
      ...(missing ? ["Install", "Open Settings"] : ["Show Output", "Open Settings", "Install"]),
    );
    if (choice === "Install") {
      // Not awaited: the server's start waits for this start to end
      void installServer();
    } else if (choice === "Open Settings") {
      void vscode.commands.executeCommand("workbench.action.openSettings", "mapcan.server");
    } else if (choice === "Show Output") {
      output?.show();
    }
  }
  await tree?.refresh();
}

/** A map is open in an editor tab. VS Code keeps the document of a closed tab for a while (an unsaved one for
 * good), so the documents alone do not tell that the last map was closed. */
function mapInTab(): boolean {
  const open = inTabs();
  return vscode.workspace.textDocuments.some((d) => isMap(d) && open.has(d.uri.toString()));
}

/** The version the running language server reported. */
function serverVersion(): string | undefined {
  return client?.initializeResult?.serverInfo?.version;
}

const REPO_URL = "https://github.com/ordu1453/mapcan";

/** The versions of the extension, of mapcan and of VS Code, for a bug report. */
function versions(): string {
  const server = client ? `mapcan ${serverVersion() ?? "(no version)"}` : "not running";
  return `mapcan extension ${extensionVersion}; language server: ${server} (${serverCommand}); ` +
    `VS Code ${vscode.version}, ${process.platform}`;
}

/** A new issue on GitHub with the versions filled in. */
function reportIssue(): Thenable<boolean> {
  const body = `\n\n---\n${versions()}`;
  return vscode.env.openExternal(vscode.Uri.parse(`${REPO_URL}/issues/new?body=${encodeURIComponent(body)}`));
}

/**
 * Installs mapcan into the extension's environment, or updates it, and restarts the server. A mapcan in the
 * environment selected in the Python extension comes first, so that one is updated in its place.
 */
async function installServer(): Promise<void> {
  if (!storage || !output) return;
  await starting;
  if (serverSource === "setting") {
    const choice = await vscode.window.showInformationMessage(
      `mapcan: the language server is the one set in "mapcan.server.path" (${serverCommand}): update that mapcan, ` +
        "or clear the setting to let the extension install its own.",
      "Open Settings");
    if (choice) void vscode.commands.executeCommand("workbench.action.openSettings", "mapcan.server");
    return;
  }
  const into = serverSource === "python" ? serverPython : undefined;
  const running = client !== undefined;
  // A running server keeps its files open: on Windows they could not be replaced
  await stop();
  try {
    await installMapcan(storage, output, into);
  } catch (err) {
    void vscode.window.showErrorMessage(
      `mapcan: could not install mapcan: ${err instanceof Error ? err.message : String(err)}`, "Show Output")
      .then((choice) => choice && output?.show());
    // An update failed: the mapcan that was running still works
    if (!running) return;
  }
  failed = false;
  await start(true);
  scheduleIdleStop();
}

async function showServerVersion(): Promise<void> {
  const text = versions();
  output?.info(text);
  const choice = await vscode.window.showInformationMessage(text, "Copy", "Report Issue");
  if (choice === "Copy") await vscode.env.clipboard.writeText(text);
  else if (choice === "Report Issue") await reportIssue();
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
  void vscode.commands.executeCommand("setContext", "mapcan.serverRunning", false);
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
  tree: MapTree; form: NodeForm; exportView: ExportView; history: HistoryTree; changes: ChangesPanel;
  client: () => LanguageClient | undefined; setIdleStop: (ms: number) => void;
  hiddenChanges: typeof hiddenChanges; serverVersion: () => string | undefined; isOlder: typeof isOlder; schemaOf: typeof schemaOf;
}> {
  output = vscode.window.createOutputChannel("mapcan", { log: true });
  extensionVersion = String(context.extension.packageJSON.version ?? "");
  storage = context.globalStorageUri;
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
    vscode.commands.registerCommand("mapcan.installServer", installServer),
    saveTogether(),
    vscode.commands.registerCommand("mapcan.showServerVersion", showServerVersion),
    vscode.commands.registerCommand("mapcan.openRepository", () => vscode.env.openExternal(vscode.Uri.parse(REPO_URL))),
    vscode.commands.registerCommand("mapcan.reportIssue", reportIssue),
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
    // Restricted Mode reads the server settings from the user's settings only: once the folder is trusted,
    // its own settings apply
    vscode.workspace.onDidGrantWorkspaceTrust(async () => {
      if (!client) return;
      await stop();
      failed = false;
      await start();
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
  registerTour(context, tree);
  registerSchemas(context);
  // The templates and the examples come from the server: it is started for them, and stops again later if
  // no map gets opened
  registerStarters(context, async () => {
    if (!client) {
      await start(true);
      scheduleIdleStop();
    }
    return client;
  }, output);
  const showChanges = registerPreview(context, () => client, currentMap, changes);
  registerHistory(context, history, currentMap, showChanges, () => client);
  await start();
  return { tree, form, exportView, history, changes, client: () => client, setIdleStop: (ms) => (idleStopMs = ms),
    hiddenChanges, serverVersion, isOlder, schemaOf };
}

export function deactivate(): Promise<void> {
  return stop();
}
