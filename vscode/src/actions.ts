// Map view commands: add, edit, duplicate, rename and delete nodes. The language server builds the
// edit; it is applied to the document, so Undo works as for any other edit. A node added with "+"
// opens in the node form, where its fields are filled in.

import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { NodeForm } from "./form";
import { Kind, MapNode, MapTree } from "./tree";

interface EditResult {
  edit?: { range: [number, number, number, number]; text: string };
  cursor?: [number, number];
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
  if (!result?.edit) return undefined;
  const [sl, sc, el, ec] = result.edit.range;
  const edit = new vscode.WorkspaceEdit();
  edit.replace(uri, new vscode.Range(sl, sc, el, ec), result.edit.text);
  if (!(await vscode.workspace.applyEdit(edit))) return undefined;
  const editor = await vscode.window.showTextDocument(uri, { preserveFocus: true, preview: false });
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

async function renameNode(tree: MapTree, node: MapNode): Promise<void> {
  const uri = tree.mapUri;
  const pos = node.namePosition;
  if (!uri || !pos) return;
  const doc = await vscode.workspace.openTextDocument(uri);
  const current = doc.getText(doc.getWordRangeAtPosition(pos, /[^\s,{}[\]#]+/));
  const name = await vscode.window.showInputBox({
    title: `Rename ${node.kind}`,
    value: current.replace(/^["']|["']$/g, ""),
    validateInput: (v) => (v.trim() ? undefined : "Enter a name"),
  });
  if (!name || name === current) return;
  const edit = await vscode.commands.executeCommand<vscode.WorkspaceEdit>(
    "vscode.executeDocumentRenameProvider", uri, pos, name.trim());
  if (edit) await vscode.workspace.applyEdit(edit);
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
    on("mapcan.renameNode", (node) => renameNode(tree, node)),
  );
}
