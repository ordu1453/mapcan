// The version of the mapcan language server. The extension shows the data of the server (the form's
// fields, the frame layout, edits in several files), so an older mapcan than the one it was made with
// may show a map wrong without an error: it says so and offers the command that updates mapcan.

import * as vscode from "vscode";

/** The oldest mapcan whose language server this extension works with. */
export const MIN_SERVER = "0.21.0";

/** The command that installs or updates mapcan with the language server. */
export const INSTALL = 'uv tool install --upgrade "mapcan[lsp]"';

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

/** Open a terminal with the install command typed in but not run: the user runs it (or types pipx instead). */
export function openInstallTerminal(): void {
  const terminal = vscode.window.createTerminal("mapcan: install");
  terminal.show();
  terminal.sendText(INSTALL, false);
}

/** Warn when the server is older than the extension needs (or does not tell its version). */
export async function checkServerVersion(version: string | undefined): Promise<void> {
  if (version && !isOlder(version, MIN_SERVER)) return;
  const choice = await vscode.window.showWarningMessage(
    `mapcan: the language server is ${version ? `mapcan ${version}` : "an unknown version of mapcan"}; ` +
      `this extension needs mapcan ${MIN_SERVER} or newer and may show maps wrong with it. Update mapcan ` +
      '(`uv tool install --upgrade "mapcan[lsp]"` or `pipx install --force "mapcan[lsp]"`).',
    "Update in Terminal",
    "Open Settings",
  );
  if (choice === "Update in Terminal") openInstallTerminal();
  else if (choice === "Open Settings") void vscode.commands.executeCommand("workbench.action.openSettings", "mapcan.server");
}
