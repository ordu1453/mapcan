// The version of the mapcan language server. The extension shows the data of the server (the form's
// fields, the frame layout, edits in several files), so an older mapcan than the one it was made with
// may show a map wrong without an error: it says so and offers to update mapcan.

import * as vscode from "vscode";
import { latestMapcan } from "./install";

/** The oldest mapcan whose language server this extension works with. */
export const MIN_SERVER = "0.24.0";

/** `version` is older than `min`; versions are compared by their first three numbers (0.21.0.dev1 is 0.21.0). */
export function isOlder(version: string, min: string): boolean {
  const parts = (v: string) => (v.match(/\d+/g) ?? []).slice(0, 3).map(Number);
  const a = parts(version);
  const b = parts(min);
  for (let i = 0; i < 3; i++) {
    if ((a[i] ?? 0) !== (b[i] ?? 0)) return (a[i] ?? 0) < (b[i] ?? 0);
  }
  return false;
}

/** Update mapcan (install.ts) and restart the server. */
export function updateServer(): void {
  void vscode.commands.executeCommand("mapcan.installServer");
}

/** Warn when the server is older than the extension needs (or does not tell its version). */
export async function checkServerVersion(version: string | undefined): Promise<void> {
  if (version && !isOlder(version, MIN_SERVER)) return;
  const choice = await vscode.window.showWarningMessage(
    `mapcan: the language server is ${version ? `mapcan ${version}` : "an unknown version of mapcan"}; ` +
      `this extension needs mapcan ${MIN_SERVER} or newer and may show maps wrong with it.`,
    "Update",
    "Open Settings",
  );
  if (choice === "Update") updateServer();
  else if (choice === "Open Settings") void vscode.commands.executeCommand("workbench.action.openSettings", "mapcan.server");
}

/** The update was looked for in this session of VS Code. */
let updateChecked = false;

/**
 * Offers the update when PyPI has a newer mapcan than `version`, once a session of VS Code: for the mapcan the
 * extension installed only, one of the user's own is theirs to update.
 */
export async function checkForUpdate(version: string | undefined): Promise<void> {
  if (updateChecked || !version || !vscode.workspace.getConfiguration("mapcan.server").get<boolean>("checkForUpdates", true)) {
    return;
  }
  updateChecked = true;
  const latest = await latestMapcan();
  if (!latest || !isOlder(version, latest)) return;
  const choice = await vscode.window.showInformationMessage(
    `mapcan ${latest} is available; the extension uses mapcan ${version}.`, "Update", "Not Now");
  if (choice === "Update") updateServer();
}
