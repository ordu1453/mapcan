// Starting points, as on the web editor's start screen: a new map from a template, or a copy of an example
// map (with the files it includes) in a folder of one's choice. The templates and the examples come from
// the language server (they ship with mapcan), so it is started for them if no map is open yet.

import { homedir } from "node:os";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { updateServer } from "./version";

/** The first mapcan whose language server serves the templates and the examples. */
const STARTERS_SERVER = "0.21.1";

interface Starters {
  templates: { id: string; label: string }[];
  examples: { name: string; title: string }[];
}

type Client = () => Promise<LanguageClient | undefined>;

async function request<T>(client: Client, command: string, args?: object): Promise<T | undefined> {
  const c = await client();
  if (!c?.isRunning()) {
    void vscode.window.showErrorMessage("mapcan: the language server is not running, so its templates and examples are unavailable.");
    return undefined;
  }
  try {
    return (await c.sendRequest(ExecuteCommandRequest.type, { command, arguments: args ? [args] : [] })) as T;
  } catch {
    // An older mapcan has no templates and examples for the editors
    const version = c.initializeResult?.serverInfo?.version ?? "an older version";
    const choice = await vscode.window.showErrorMessage(
      `mapcan: creating a map and opening an example need mapcan ${STARTERS_SERVER} or newer; the language server is ${version}.`,
      "Update");
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

export function registerStarters(context: vscode.ExtensionContext, client: Client): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("mapcan.newMap", () => newMap(client)),
    vscode.commands.registerCommand("mapcan.openExample", (name?: string) => openExample(client, name)),
  );
}
