// Starting points, as on the web editor's start screen: a new map from a template, a copy of an example
// map (with the files it includes) in a folder of one's choice, or a map imported from a DBC file. The
// templates, the examples and the import come from the language server (they ship with mapcan), so it is
// started for them if no map is open yet.

import { homedir } from "node:os";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { updateServer } from "./version";

/** The first mapcan whose language server serves the templates and the examples. */
const STARTERS_SERVER = "0.21.1";
/** The first mapcan whose language server imports a DBC file. */
const IMPORT_SERVER = "0.23.3";

interface Starters {
  templates: { id: string; label: string }[];
  examples: { name: string; title: string }[];
}

type Client = () => Promise<LanguageClient | undefined>;

/** What a request needs of the server, for the message when it is older. */
interface Need {
  what: string;
  since: string;
}

const STARTERS: Need = { what: "creating a map and opening an example need", since: STARTERS_SERVER };

async function request<T>(client: Client, command: string, args?: object, need = STARTERS): Promise<T | undefined> {
  const c = await client();
  if (!c?.isRunning()) {
    void vscode.window.showErrorMessage("mapcan: the language server is not running, so its templates and examples are unavailable.");
    return undefined;
  }
  try {
    return (await c.sendRequest(ExecuteCommandRequest.type, { command, arguments: args ? [args] : [] })) as T;
  } catch {
    // An older mapcan does not have the command
    const version = c.initializeResult?.serverInfo?.version ?? "an older version";
    const choice = await vscode.window.showErrorMessage(
      `mapcan: ${need.what} mapcan ${need.since} or newer; the language server is ${version}.`, "Update");
    if (choice === "Update") updateServer();
    return undefined;
  }
}

/** The folder new files go to by default: the first workspace folder, else the home folder. */
function defaultFolder(): vscode.Uri {
  return vscode.workspace.workspaceFolders?.[0]?.uri ?? vscode.Uri.file(homedir());
}

async function openMap(uri: vscode.Uri): Promise<void> {
  await vscode.window.showTextDocument(uri, { preview: false });
  await vscode.commands.executeCommand("workbench.view.extension.mapcan");
}

async function newMap(client: Client): Promise<void> {
  const starters = await request<Starters>(client, "mapcan.lsp.starters");
  if (!starters) return;
  const template = await vscode.window.showQuickPick(
    starters.templates.map((t) => ({ label: t.label, id: t.id })),
    { title: "Create a mapcan map (1/2): template", placeHolder: "What the map starts with" });
  if (!template) return;
  const title = await vscode.window.showInputBox({
    title: "Create a mapcan map (2/2): title", prompt: "The title of the map's document", value: "New map",
    validateInput: (v) => (v.trim() ? undefined : "Enter a title"),
  });
  if (!title) return;
  // The map's documents are in the language of VS Code (Russian or English; document.language changes it)
  const language = vscode.env.language.startsWith("ru") ? "ru" : "en";
  const result = await request<{ text?: string; error?: string }>(client, "mapcan.lsp.newMap",
    { template: template.id, title: title.trim(), language });
  if (!result?.text) {
    if (result?.error) void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
    return;
  }
  const slug = title.trim().toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "map";
  const target = await vscode.window.showSaveDialog({
    title: "Save the new map", saveLabel: "Create Map",
    defaultUri: vscode.Uri.joinPath(defaultFolder(), `${slug}.yaml`), filters: { "mapcan map": ["yaml", "yml"] },
  });
  if (!target) return;
  await vscode.workspace.fs.writeFile(target, Buffer.from(result.text, "utf8"));
  await openMap(target);
}

async function openExample(client: Client, name?: string): Promise<void> {
  const starters = await request<Starters>(client, "mapcan.lsp.starters");
  if (!starters) return;
  const picked = name
    ? starters.examples.find((e) => e.name === name)
    : (await vscode.window.showQuickPick(
      starters.examples.map((e) => ({ label: e.title, description: e.name !== e.title ? `${e.name}.yaml` : undefined, example: e })),
      { title: "Open a mapcan example", placeHolder: "A copy of the example goes to a folder you choose" }))?.example;
  if (!picked) return;
  const folders = await vscode.window.showOpenDialog({
    title: `Copy the example "${picked.title}" to a folder`, openLabel: "Copy Here",
    canSelectFiles: false, canSelectFolders: true, canSelectMany: false, defaultUri: defaultFolder(),
  });
  if (!folders?.length) return;
  const mapFile = `${picked.name}.yaml`;
  const result = await request<{ text?: string; includes?: Record<string, string>; error?: string }>(
    client, "mapcan.lsp.example", { name: picked.name, mapFile });
  if (!result?.text) {
    if (result?.error) void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
    return;
  }
  const files: [vscode.Uri, string][] = [
    [vscode.Uri.joinPath(folders[0], mapFile), result.text],
    ...Object.entries(result.includes ?? {}).map(([f, text]): [vscode.Uri, string] => [vscode.Uri.joinPath(folders[0], f), text]),
  ];
  const existing: string[] = [];
  for (const [uri] of files) {
    try {
      await vscode.workspace.fs.stat(uri);
      existing.push(vscode.workspace.asRelativePath(uri));
    } catch {
      // not there yet
    }
  }
  if (existing.length) {
    const answer = await vscode.window.showWarningMessage(
      `mapcan: ${existing.join(", ")} already exist${existing.length === 1 ? "s" : ""} in that folder. Overwrite?`,
      { modal: true }, "Overwrite");
    if (answer !== "Overwrite") return;
  }
  for (const [uri, text] of files) await vscode.workspace.fs.writeFile(uri, Buffer.from(text, "utf8"));
  await openMap(files[0][0]);
}

/**
 * A map from a DBC file (`dbc`, or one picked in a dialog), written next to it with its name and opened; what the
 * import could not bring over goes to the output channel.
 */
async function importDbc(client: Client, output: vscode.LogOutputChannel, dbc?: vscode.Uri): Promise<void> {
  if (!dbc) {
    const picked = await vscode.window.showOpenDialog({
      title: "Import a DBC file as a mapcan map", openLabel: "Import", canSelectMany: false,
      defaultUri: defaultFolder(), filters: { DBC: ["dbc"] },
    });
    if (!picked?.length) return;
    dbc = picked[0];
  }
  const target = dbc.with({ path: dbc.path.replace(/(\.dbc)?$/i, ".yaml") });
  try {
    await vscode.workspace.fs.stat(target);
    const answer = await vscode.window.showWarningMessage(
      `mapcan: ${vscode.workspace.asRelativePath(target)} already exists. Overwrite?`, { modal: true }, "Overwrite");
    if (answer !== "Overwrite") return;
  } catch {
    // not there yet
  }
  const name = dbc.path.slice(dbc.path.lastIndexOf("/") + 1).replace(/\.dbc$/i, "");
  const language = vscode.env.language.startsWith("ru") ? "ru" : "en";
  const result = await request<{ text?: string; warnings?: string[]; error?: string }>(client, "mapcan.lsp.importDbc",
    { path: dbc.fsPath, title: name, language }, { what: "importing a DBC file needs", since: IMPORT_SERVER });
  if (!result?.text) {
    if (result?.error) void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
    return;
  }
  await vscode.workspace.fs.writeFile(target, Buffer.from(result.text, "utf8"));
  await openMap(target);
  const warnings = result.warnings ?? [];
  if (!warnings.length) return;
  output.warn(`Import of ${dbc.fsPath}:`);
  for (const w of warnings) output.warn(`  ${w}`);
  const choice = await vscode.window.showWarningMessage(
    `mapcan: ${name}.dbc imported with ${warnings.length} warning${warnings.length === 1 ? "" : "s"}.`, "Show");
  if (choice === "Show") output.show();
}

export function registerStarters(context: vscode.ExtensionContext, client: Client, output: vscode.LogOutputChannel): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("mapcan.newMap", () => newMap(client)),
    vscode.commands.registerCommand("mapcan.openExample", (name?: string) => openExample(client, name)),
    vscode.commands.registerCommand("mapcan.importDbc", (dbc?: vscode.Uri) => importDbc(client, output, dbc)),
  );
}
