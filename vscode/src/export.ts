// The Export panel in the side bar: builds documents, DBC and code from the current text of the map
// (unsaved edits included) into a folder next to it, like `mapcan build`.

import * as path from "path";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { MapTree } from "./tree";
import { webviewHtml } from "./webview";

export const FORMATS: { id: string; label: string; detail: string }[] = [
  { id: "dbc", label: "DBC", detail: "One .dbc file per bus, for CANalyzer, BusMaster, SavvyCAN" },
  { id: "eds", label: "EDS", detail: "One .eds file per CANopen device: mapped objects and PDOs" },
  { id: "c", label: "C", detail: "Headers and sources: IDs, enums, structs, pack/unpack" },
  { id: "py", label: "Python", detail: "The same structures for tests and test benches" },
  { id: "xlsx", label: "Excel", detail: "Communication matrix, bit maps, changes" },
  { id: "pdf", label: "PDF", detail: "Document, typeset with Typst" },
  { id: "md", label: "Markdown", detail: "For a README or wiki" },
  { id: "html", label: "HTML", detail: "Self-contained page with search" },
];
const LAST_FORMATS = "mapcan.export.lastFormats";
/** Output folder chosen in the panel, per map (else the mapcan.export.outputDir setting). */
const OUT_DIRS = "mapcan.export.outDirs";

interface ExportResult {
  files?: string[];
  warnings?: string[];
  error?: string;
}

type Message =
  | { type: "ready" }
  | { type: "export"; formats: string[]; outDir: string }
  | { type: "browse" }
  | { type: "open"; file: string }
  | { type: "reveal"; file: string };

export class ExportView implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewId = "mapcan.export";

  private view: vscode.WebviewView | undefined;
  private busy = false;
  private last: { map: string; result: ExportResult; outDir: string } | undefined;
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly tree: MapTree,
    private readonly client: () => LanguageClient | undefined,
  ) {
    this.subscriptions.push(tree.onDidChangeTreeData(() => this.update()));
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = {
      enableScripts: true,
      localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, "media")],
    };
    view.webview.html = webviewHtml(view.webview, this.context.extensionUri, "export", "mapcan: export");
    view.webview.onDidReceiveMessage((m: Message) => this.onMessage(m));
    view.onDidDispose(() => (this.view = undefined));
  }

  /** The output folder as typed in the panel or set in the settings (relative to the map's folder). */
  private outDir(uri: vscode.Uri): string {
    const chosen = this.context.workspaceState.get<Record<string, string>>(OUT_DIRS, {})[uri.toString()];
    return chosen || vscode.workspace.getConfiguration("mapcan.export", uri).get<string>("outputDir") || "build";
  }

  private update(): void {
    const uri = this.tree.mapUri;
    void this.view?.webview.postMessage({
      type: "state",
      map: uri ? path.basename(uri.fsPath) : null,
      saved: uri?.scheme === "file",
      formats: FORMATS,
      picked: this.context.globalState.get<string[]>(LAST_FORMATS, ["dbc", "c"]),
      outDir: uri ? this.outDir(uri) : "",
      busy: this.busy,
      last: this.last && this.last.map === uri?.toString()
        ? { ...this.last.result, outDir: this.last.outDir }
        : null,
    });
  }

  private async onMessage(m: Message): Promise<void> {
    const uri = this.tree.mapUri;
    switch (m.type) {
      case "ready":
        this.update();
        break;
      case "browse": {
        if (!uri) return;
        const base = path.dirname(uri.fsPath);
        const picked = await vscode.window.showOpenDialog({
          canSelectFiles: false, canSelectFolders: true, canSelectMany: false,
          defaultUri: vscode.Uri.file(path.resolve(base, this.outDir(uri))), openLabel: "Export Here",
        });
        if (picked?.[0]) {
          const rel = path.relative(base, picked[0].fsPath);
          await this.setOutDir(uri, rel && !rel.startsWith("..") && !path.isAbsolute(rel) ? rel : picked[0].fsPath);
          this.update();
        }
        break;
      }
      case "export":
        if (uri) {
          await this.setOutDir(uri, m.outDir.trim());
          await this.context.globalState.update(LAST_FORMATS, m.formats);
          await this.run(uri, m.formats);
        }
        break;
      case "open":
        await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(m.file));
        break;
      case "reveal":
        await vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(m.file));
        break;
    }
  }

  private async setOutDir(uri: vscode.Uri, dir: string): Promise<void> {
    const dirs = { ...this.context.workspaceState.get<Record<string, string>>(OUT_DIRS, {}) };
    const setting = vscode.workspace.getConfiguration("mapcan.export", uri).get<string>("outputDir") || "build";
    if (!dir || dir === setting) delete dirs[uri.toString()];
    else dirs[uri.toString()] = dir;
    await this.context.workspaceState.update(OUT_DIRS, dirs);
  }

  private async run(uri: vscode.Uri, formats: string[]): Promise<void> {
    const client = this.client();
    if (!client?.isRunning()) {
      void vscode.window.showErrorMessage("mapcan: the language server is not running.");
      return;
    }
    if (formats.length === 0) return;
    const outDir = path.resolve(path.dirname(uri.fsPath), this.outDir(uri));
    this.busy = true;
    this.update();
    try {
      const result = await vscode.window.withProgress(
        { location: { viewId: ExportView.viewId } },
        () => client.sendRequest(ExecuteCommandRequest.type, {
          command: "mapcan.lsp.export",
          arguments: [{ uri: uri.toString(), formats, outDir }],
        }) as Promise<ExportResult>,
      );
      this.last = { map: uri.toString(), result: result ?? {}, outDir };
    } finally {
      this.busy = false;
      this.update();
    }
  }

  /** The palette command: show the panel. */
  async reveal(): Promise<void> {
    if (!this.tree.mapUri) {
      void vscode.window.showWarningMessage("mapcan: open a map to export it.");
      return;
    }
    await vscode.commands.executeCommand(`${ExportView.viewId}.focus`);
  }

  dispose(): void {
    this.subscriptions.forEach((d) => d.dispose());
  }
}
