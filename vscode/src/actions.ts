// Map view commands: add, edit, duplicate, rename and delete nodes. The language server builds the
// edit; it is applied to the document, so Undo works as for any other edit. A node added with "+"
// opens in the node form, where its fields are filled in. A node of another file of the map (an included
// file, or the main file when an included one is open) is added, copied and deleted in that file. A device
// can also be added in a file of its own, which the map includes; deleting it deletes the file left empty and its
// line of include.

import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { addOthers, keepBackground, Others, TextEdit } from "./files";
import { NodeForm } from "./form";
import { Kind, MapNode, MapTree } from "./tree";

interface EditResult {
  edit?: { range: [number, number, number, number]; text: string };
  cursor?: [number, number];
  /** The other file of the map the edit and the cursor are in; none: the map in the tree. */
  uri?: string;
  /** Why the edit cannot be made (a new signal has no room in its frame). */
  error?: string;
  /** An included file a delete left adding nothing to the map (a device's own file): it is deleted, and `edits` and
   * `others` remove it from `include`. */
  delete?: string;
  edits?: TextEdit[];
  others?: Others;
}

/** Apply a tree edit; returns the node under the new cursor (the added or copied node). */
async function runEdit(
  client: LanguageClient | undefined,
  tree: MapTree,
  args: { action: "add" | "duplicate" | "delete"; path: (string | number)[]; kind?: Kind },
): Promise<MapNode | undefined> {
  const uri = tree.mapUri;
  if (!uri || !client?.isRunning()) return undefined;
  const result = (await client.sendRequest(ExecuteCommandRequest.type, {
    command: "mapcan.lsp.edit",
    arguments: [{ uri: uri.toString(), ...args }],
  })) as EditResult | null;
  if (result?.error) void vscode.window.showWarningMessage(result.error);
  if (result?.delete) {
    const edit = new vscode.WorkspaceEdit();
    for (const e of result.edits ?? []) edit.replace(uri, new vscode.Range(...e.range), e.text);
    const others = addOthers(edit, result.others);
    edit.deleteFile(vscode.Uri.parse(result.delete), { ignoreIfNotExists: true });
    if (await vscode.workspace.applyEdit(edit)) keepBackground([uri, ...others]);
    await tree.refresh();
    return undefined;
  }
  if (!result?.edit) return undefined;
  const target = result.uri ? vscode.Uri.parse(result.uri) : uri;
  const [sl, sc, el, ec] = result.edit.range;
  const edit = new vscode.WorkspaceEdit();
  edit.replace(target, new vscode.Range(sl, sc, el, ec), result.edit.text);
  if (!(await vscode.workspace.applyEdit(edit))) return undefined;
  if (result.uri && args.action === "delete") {
    // The tree stays on its map: nothing is to be shown in the other file
    keepBackground([target]);
    await tree.refresh();
    return undefined;
  }
  // A new node in another file opens that file, and the tree shows the map from it
  const editor = await vscode.window.showTextDocument(target, { preserveFocus: true, preview: false });
  if (!result.cursor) return undefined;
  // Select the new name, so it is visible in the editor (and can be typed over right away)
  const pos = new vscode.Position(result.cursor[0], result.cursor[1]);
  const word = editor.document.getWordRangeAtPosition(pos, /[\w.-]+/);
  editor.selection = word ? new vscode.Selection(word.start, word.end) : new vscode.Selection(pos, pos);
  editor.revealRange(editor.selection, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
  await tree.refresh();
  await tree.revealCursor();
  return tree.nodeAt(pos);
}

interface SetResult {
  edits?: TextEdit[];
  others?: Others;
  error?: string;
}

async function renameNode(tree: MapTree, node: MapNode, client: LanguageClient | undefined): Promise<void> {
  const uri = tree.mapUri;
  const pos = node.namePosition;
  if (!uri || !pos) return;
  // The position of the name is in the node's own file
  const doc = await vscode.workspace.openTextDocument(node.file ?? uri);
  const current = doc.getText(doc.getWordRangeAtPosition(pos, /[^\s,{}[\]#]+/));
  const name = await vscode.window.showInputBox({
    title: `Rename ${node.kind}`,
    value: current.replace(/^["']|["']$/g, ""),
    validateInput: (v) => (v.trim() ? undefined : "Enter a name"),
  });
  if (!name || name === current) return;
  if (node.file) {
    // A node of another file of the map: written there as by the form, a device with the references to it
    if (!client?.isRunning()) return;
    const result = (await client.sendRequest(ExecuteCommandRequest.type, {
      command: "mapcan.lsp.set",
      arguments: [{ uri: uri.toString(), path: [...node.path, "name"], value: name.trim() }],
    })) as SetResult | null;
    if (result?.error) {
      void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
      return;
    }
    const edit = new vscode.WorkspaceEdit();
    for (const e of result?.edits ?? []) edit.replace(uri, new vscode.Range(...e.range), e.text);
    const others = addOthers(edit, result?.others);
    if (await vscode.workspace.applyEdit(edit)) keepBackground(others);
    return;
  }
  const edit = await vscode.commands.executeCommand<vscode.WorkspaceEdit>(
    "vscode.executeDocumentRenameProvider", uri, pos, name.trim());
  if (edit) await vscode.workspace.applyEdit(edit);
}

interface DeviceFileResult {
  /** The default name of the file, relative to the map (the first request, without a file). */
  file?: string;
  create?: { uri: string; text: string };
  /** The device's name in the new file. */
  cursor?: [number, number];
  edits?: TextEdit[];
  others?: Others;
  error?: string;
}

/**
 * A new device of a bus in a file of its own (#136): the file is created with the device and added to `include` of
 * the map, in one edit undone together. The file opens, and the device in the node form.
 */
async function addDeviceFile(client: LanguageClient | undefined, tree: MapTree, form: NodeForm, bus: MapNode):
  Promise<void> {
  const uri = tree.mapUri;
  if (!uri || !client?.isRunning()) return;
  const request = (file?: string) => client.sendRequest(ExecuteCommandRequest.type, {
    command: "mapcan.lsp.deviceFile",
    arguments: [{ uri: uri.toString(), path: bus.path, file }],
  }) as Promise<DeviceFileResult | null>;
  const first = await request();
  if (first?.error || !first?.file) {
    if (first?.error) void vscode.window.showErrorMessage(`mapcan: ${first.error}`);
    return;
  }
  const name = first.file.lastIndexOf("/") + 1;
  const file = await vscode.window.showInputBox({
    title: "Add device in a new file",
    prompt: "The file, relative to the map; the map includes it",
    value: first.file,
    valueSelection: [name, first.file.length - ".yaml".length],
    validateInput: (v) => (v.trim() ? undefined : "Enter a file name"),
  });
  if (!file) return;
  const result = await request(file.trim());
  if (result?.error || !result?.create) {
    if (result?.error) void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
    return;
  }
  // The included file's devices come after the map's own ones: the new device is the last of the bus
  const path = [...bus.path, "devices", bus.children.filter((n) => n.kind === "device" && !n.isLink).length];
  const created = vscode.Uri.parse(result.create.uri);
  const edit = new vscode.WorkspaceEdit();
  edit.createFile(created, { contents: new TextEncoder().encode(result.create.text) });
  for (const e of result.edits ?? []) edit.replace(uri, new vscode.Range(...e.range), e.text);
  const others = addOthers(edit, result.others);
  if (!(await vscode.workspace.applyEdit(edit))) return;
  keepBackground([uri, ...others]);
  const editor = await vscode.window.showTextDocument(created, { preserveFocus: true, preview: false });
  const [line, col] = result.cursor ?? [0, 0];
  const word = editor.document.getWordRangeAtPosition(new vscode.Position(line, col), /[\w.-]+/);
  if (word) editor.selection = new vscode.Selection(word.start, word.end);
  await tree.refresh();
  await form.open(path, true);
}

export function registerTreeActions(
  context: vscode.ExtensionContext,
  tree: MapTree,
  form: NodeForm,
  client: () => LanguageClient | undefined,
): void {
  const on = (id: string, fn: (node: MapNode) => Promise<void> | void) =>
    vscode.commands.registerCommand(id, (node?: MapNode) => {
      const target = tree.target(node);
      return target && !target.isLink ? fn(target) : undefined;
    });
  const add = async (path: (string | number)[], kind: Kind) => {
    const added = await runEdit(client(), tree, { action: "add", path, kind });
    if (added && added.kind === kind) await form.open(added.path, true);
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("mapcan.addBus", () => add([], "bus")),
    on("mapcan.addDevice", (node) => add(node.path, "device")),
    on("mapcan.addDeviceFile", (node) => addDeviceFile(client(), tree, form, node)),
    on("mapcan.addFrame", (node) => add(node.path, "frame")),
    on("mapcan.addSignal", (node) => add(node.path, "signal")),
    on("mapcan.editNode", (node) => form.open(node.path)),
    on("mapcan.duplicateNode", async (node) => {
      await runEdit(client(), tree, { action: "duplicate", path: node.path });
    }),
    on("mapcan.deleteNode", async (node) => {
      // The form would show the next node, which takes the deleted node's place in the list
      const open = form.openPath;
      if (open && open.length >= node.path.length && node.path.every((x, i) => String(x) === String(open[i]))) {
        await form.close();
      }
      await runEdit(client(), tree, { action: "delete", path: node.path });
    }),
    on("mapcan.renameNode", (node) => renameNode(tree, node, client())),
    // Also of a link: it has the path of its frame
    vscode.commands.registerCommand("mapcan.copyPath", async (node?: MapNode) => {
      const path = tree.target(node)?.canonicalPath;
      if (!path) return;
      await vscode.env.clipboard.writeText(path);
      vscode.window.setStatusBarMessage(`Copied ${path}`, 3000);
    }),
  );
}
