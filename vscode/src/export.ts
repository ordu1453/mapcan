// mapcan: Export… — builds documents, DBC and code from the current text of the map
// (unsaved edits included) into a folder next to it, like `mapcan build`.

import * as path from "path";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";

const FORMATS: { id: string; label: string; detail: string }[] = [
  { id: "dbc", label: "DBC", detail: "One .dbc file per bus, for CANalyzer, BusMaster, SavvyCAN" },
  { id: "c", label: "C code", detail: "Headers and sources: IDs, enums, structs, pack/unpack" },
  { id: "py", label: "Python module", detail: "The same structures for tests and test benches" },
  { id: "xlsx", label: "Excel", detail: "Communication matrix, bit maps, changes" },
  { id: "pdf", label: "PDF", detail: "Document via Typst" },
  { id: "md", label: "Markdown", detail: "For a README or wiki" },
  { id: "html", label: "HTML", detail: "Self-contained page with search" },
];
const LAST_FORMATS = "mapcan.export.lastFormats";

interface ExportResult {
  files?: string[];
  warnings?: string[];
  error?: string;
}

export async function exportMap(
  context: vscode.ExtensionContext,
  client: LanguageClient | undefined,
  uri: vscode.Uri | undefined,
): Promise<void> {
  if (!uri) {
    void vscode.window.showWarningMessage("mapcan: open a map to export it.");
    return;
  }
  if (!client?.isRunning()) {
    void vscode.window.showErrorMessage("mapcan: the language server is not running.");
    return;
  }
  const last = context.globalState.get<string[]>(LAST_FORMATS, ["dbc", "c"]);
  const picked = await vscode.window.showQuickPick(
    FORMATS.map((f) => ({ ...f, picked: last.includes(f.id) })),
    { canPickMany: true, title: "mapcan: Export", placeHolder: "Formats to build" },
  );
  if (!picked || picked.length === 0) {
    return;
  }
  const formats = picked.map((f) => f.id);
  await context.globalState.update(LAST_FORMATS, formats);

  const setting = vscode.workspace.getConfiguration("mapcan.export", uri).get<string>("outputDir") || "build";
  const outDir = path.resolve(path.dirname(uri.fsPath), setting);

  const result = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `mapcan: exporting ${picked.map((f) => f.label).join(", ")}…` },
    () =>
      client.sendRequest(ExecuteCommandRequest.type, {
        command: "mapcan.lsp.export",
        arguments: [{ uri: uri.toString(), formats, outDir }],
      }) as Promise<ExportResult>,
  );
  if (result?.error) {
    void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
    return;
  }
  for (const w of result?.warnings ?? []) {
    void vscode.window.showWarningMessage(`mapcan: ${w}`);
  }
  const files = result?.files ?? [];
  const where = vscode.workspace.asRelativePath(outDir);
  const actions = files.length === 1 ? ["Open", "Reveal in File Explorer"] : ["Reveal in File Explorer"];
  const choice = await vscode.window.showInformationMessage(
    `mapcan: exported ${files.length} file${files.length === 1 ? "" : "s"} to ${where}.`,
    ...actions,
  );
  if (choice === "Open") {
    await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(files[0]));
  } else if (choice === "Reveal in File Explorer") {
    await vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(files[0] ?? outDir));
  }
}
