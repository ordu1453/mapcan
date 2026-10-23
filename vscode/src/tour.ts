// The buttons of "Get started with mapcan" (the walkthrough in package.json) that show a feature in place: a
// problem with its quick fix, the hover of a frame, the History panel. A problem is shown on a small map of the
// extension's own, written to its global storage, so the user's maps are never changed.

import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as vscode from "vscode";
import { isMap, MapTree } from "./tree";

/** Two signals in the same byte: one error, which the quick fix moves to free bits. */
const TOUR_MAP = `mapcan: 2

document:
  title: Battery
  version: 0.1.0
  language: en

buses:
  - name: vehicle
    title: Vehicle CAN
    protocol: can
    bitrate: 500000
    devices:
      - name: bms
        short: BMS
        title: Battery management
        frames:
          - name: battery_status
            title: Battery status
            id: 0x100
            length: 8
            cycle_ms: 100
            signals:
              - name: pack_voltage
                title: Pack voltage
                encoding: number
                byte: 0
                byte_length: 2
                factor: 0.1
                unit: V
              - name: pack_current
                title: Pack current
                encoding: number
                byte: 1
                byte_length: 2
                representation: twos_complement
                factor: 0.1
                unit: A
              - name: state_of_charge
                title: State of charge
                encoding: number
                byte: 4
                byte_length: 1
                factor: 0.5
                unit: "%"
`;

/** Waits for `fn` to return something, or gives up after `ms`. */
async function until<T>(fn: () => T | undefined, ms: number): Promise<T | undefined> {
  const end = Date.now() + ms;
  for (;;) {
    const value = fn();
    if (value || Date.now() > end) return value;
    await new Promise((r) => setTimeout(r, 200));
  }
}

/** The tour's map, written again so it has its mistake; opened in an editor. */
async function openTourMap(storage: vscode.Uri): Promise<vscode.TextEditor> {
  const file = path.join(storage.fsPath, "tour", "battery.yaml");
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, TOUR_MAP);
  const editor = await vscode.window.showTextDocument(vscode.Uri.file(file), { preview: false });
  // Opened before and edited (the quick fix applied, say): back to the text on the disk
  if (editor.document.isDirty || editor.document.getText() !== TOUR_MAP) {
    await vscode.commands.executeCommand("workbench.action.files.revert");
  }
  return editor;
}

function place(editor: vscode.TextEditor, at: vscode.Position): void {
  editor.selection = new vscode.Selection(at, at);
  editor.revealRange(new vscode.Range(at, at), vscode.TextEditorRevealType.InCenter);
}

/** The tour's map with its error under the cursor and the quick fixes open. */
async function showProblem(storage: vscode.Uri): Promise<void> {
  const editor = await openTourMap(storage);
  const error = await until(() => vscode.languages.getDiagnostics(editor.document.uri)
    .find((d) => d.source === "mapcan" && d.severity === vscode.DiagnosticSeverity.Error), 30_000);
  if (!error) {
    void vscode.window.showWarningMessage("mapcan: the language server is not running, so the map is not checked.");
    return;
  }
  place(editor, error.range.start);
  await vscode.commands.executeCommand("editor.action.quickFix");
}

/** The hover of the first frame of the map in the editor, or of the tour's map. */
async function showHover(storage: vscode.Uri): Promise<void> {
  const active = vscode.window.activeTextEditor;
  const editor = isMap(active?.document) && active ? active : await openTourMap(storage);
  const match = /^\s*frames:\s*\n\s*- name: /m.exec(editor.document.getText());
  if (!match) {
    void vscode.window.showInformationMessage("mapcan: this map has no frames yet.");
    return;
  }
  place(editor, editor.document.positionAt(match.index + match[0].length + 1));
  // The server answers once it knows the document
  await new Promise((r) => setTimeout(r, 500));
  await vscode.commands.executeCommand("editor.action.showHover");
}

async function showHistory(tree: MapTree): Promise<void> {
  if (!tree.mapUri) {
    void vscode.window.showInformationMessage("mapcan: open a map to see its history.");
    return;
  }
  await vscode.commands.executeCommand("mapcan.history.focus");
}

export function registerTour(context: vscode.ExtensionContext, tree: MapTree): void {
  const storage = context.globalStorageUri;
  context.subscriptions.push(
    vscode.commands.registerCommand("mapcan.tour.showProblem", () => showProblem(storage)),
    vscode.commands.registerCommand("mapcan.tour.showHover", () => showHover(storage)),
    vscode.commands.registerCommand("mapcan.tour.showHistory", () => showHistory(tree)),
  );
}
