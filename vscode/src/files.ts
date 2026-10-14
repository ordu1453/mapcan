// Edits the language server makes in the other files of a map: a node of an included file is written in
// that file. They are applied together with the edit of the map in one WorkspaceEdit, so Undo in either file
// offers to undo them in all the files. A file changed that way may not be open in any tab: then it is
// said, so that its unsaved changes are not left behind.

import * as vscode from "vscode";

export type TextEdit = { range: [number, number, number, number]; text: string };

/** Edits of the other files of the map. */
export type Others = { uri: string; edit: TextEdit }[];

/** Add the edits of the other files of the map; returns those files. */
export function addOthers(edit: vscode.WorkspaceEdit, others: Others | undefined): vscode.Uri[] {
  const uris: vscode.Uri[] = [];
  for (const o of others ?? []) {
    const uri = vscode.Uri.parse(o.uri);
    edit.replace(uri, new vscode.Range(...o.edit.range), o.edit.text);
    uris.push(uri);
  }
  return uris;
}

/** Documents open in editor tabs (a diff counts both its sides). */
export function inTabs(): Set<string> {
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
  return open;
}

/** Files changed by an edit, with unsaved changes, that no tab shows. */
export function hiddenChanges(uris: vscode.Uri[]): vscode.TextDocument[] {
  const open = inTabs();
  const seen = new Set<string>();
  const out: vscode.TextDocument[] = [];
  for (const uri of uris) {
    const key = uri.toString();
    if (seen.has(key) || open.has(key)) continue;
    seen.add(key);
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === key);
    if (doc?.isDirty) out.push(doc);
  }
  return out;
}

/** Tell that the edit changed files no tab shows, and offer to save or open them. */
export async function reportHidden(uris: vscode.Uri[]): Promise<void> {
  const docs = hiddenChanges(uris);
  if (!docs.length) return;
  const names = docs.map((d) => vscode.workspace.asRelativePath(d.uri)).join(", ");
  const choice = await vscode.window.showInformationMessage(
    `mapcan: the change was also written to ${names}, which is not open in an editor and is not saved yet.`,
    "Save", "Open");
  if (choice === "Save") {
    for (const d of docs) await d.save();
  } else if (choice === "Open") {
    for (const d of docs) await vscode.window.showTextDocument(d, { preview: false, preserveFocus: true });
  }
}
