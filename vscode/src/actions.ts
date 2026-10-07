// Map view commands: add, duplicate, rename and delete nodes. The language server builds the
// edit; it is applied to the document, so Undo works as for any other edit.

import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { Kind, MapNode, MapTree } from "./tree";

interface EditResult {
  edit?: { range: [number, number, number, number]; text: string };
  cursor?: [number, number];
}

async function runEdit(
  client: LanguageClient | undefined,
  tree: MapTree,
  args: { action: "add" | "duplicate" | "delete"; path: (string | number)[]; kind?: Kind },
): Promise<void> {
  const uri = tree.mapUri;
  if (!uri || !client?.isRunning()) return;
  const result = (await client.sendRequest(ExecuteCommandRequest.type, {
    command: "mapcan.lsp.edit",
    arguments: [{ uri: uri.toString(), ...args }],
  })) as EditResult | null;
  if (!result?.edit) return;
  const [sl, sc, el, ec] = result.edit.range;
  const edit = new vscode.WorkspaceEdit();
  edit.replace(uri, new vscode.Range(sl, sc, el, ec), result.edit.text);
  if (!(await vscode.workspace.applyEdit(edit))) return;
  const editor = await vscode.window.showTextDocument(uri, { preserveFocus: true, preview: false });
  if (result.cursor) {
    // Select the new name so it can be typed over right away.
    const pos = new vscode.Position(result.cursor[0], result.cursor[1]);
    const word = editor.document.getWordRangeAtPosition(pos, /[\w.-]+/);
    editor.selection = word ? new vscode.Selection(word.start, word.end) : new vscode.Selection(pos, pos);
    editor.revealRange(editor.selection, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    await tree.refresh();
    await tree.revealCursor();
  }
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
  client: () => LanguageClient | undefined,
): void {
  const on = (id: string, fn: (node: MapNode) => Promise<void> | void) =>
    vscode.commands.registerCommand(id, (node?: MapNode) => {
      const target = tree.target(node);
      return target && !target.isLink ? fn(target) : undefined;
    });
  const add = (kind: Kind) => (node: MapNode) => runEdit(client(), tree, { action: "add", path: node.path, kind });
  context.subscriptions.push(
    on("mapcan.addDevice", add("device")),
    on("mapcan.addFrame", add("frame")),
    on("mapcan.addSignal", add("signal")),
    on("mapcan.duplicateNode", (node) => runEdit(client(), tree, { action: "duplicate", path: node.path })),
    on("mapcan.deleteNode", (node) => runEdit(client(), tree, { action: "delete", path: node.path })),
    on("mapcan.renameNode", (node) => renameNode(tree, node)),
  );
}
