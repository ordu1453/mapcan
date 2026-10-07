// Document preview and comparison with a Git revision, both shown in VS Code's Markdown preview.
// The Markdown comes from the language server and lives in virtual `mapcan-preview:` documents.

import { execFile } from "child_process";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";

const SCHEME = "mapcan-preview";
const run = promisify(execFile);

class PreviewContent implements vscode.TextDocumentContentProvider {
  private readonly changed = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.changed.event;
  private readonly texts = new Map<string, string>();

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.texts.get(uri.toString()) ?? "";
  }

  set(uri: vscode.Uri, text: string): void {
    this.texts.set(uri.toString(), text);
    this.changed.fire(uri);
  }

  has(uri: vscode.Uri): boolean {
    return this.texts.has(uri.toString());
  }

  dispose(): void {
    this.changed.dispose();
  }
}

async function serverText(
  client: LanguageClient | undefined,
  command: string,
  args: object,
): Promise<string | undefined> {
  if (!client?.isRunning()) {
    void vscode.window.showErrorMessage("mapcan: the language server is not running.");
    return undefined;
  }
  const result = (await client.sendRequest(ExecuteCommandRequest.type, { command, arguments: [args] })) as
    | { text?: string; error?: string }
    | null;
  if (result?.error) {
    void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
  }
  return result?.text;
}

function previewUri(map: vscode.Uri, title: string): vscode.Uri {
  return vscode.Uri.from({ scheme: SCHEME, path: `/${title}.md`, query: map.toString() });
}

async function git(cwd: string, args: string[]): Promise<string> {
  const { stdout } = await run("git", args, { cwd, maxBuffer: 32 * 1024 * 1024 });
  return stdout;
}

export function registerPreview(
  context: vscode.ExtensionContext,
  client: () => LanguageClient | undefined,
  currentMap: () => vscode.Uri | undefined,
): void {
  const content = new PreviewContent();
  let timer: NodeJS.Timeout | undefined;

  const renderInto = async (map: vscode.Uri, target: vscode.Uri) => {
    const text = await serverText(client(), "mapcan.lsp.render", { uri: map.toString() });
    if (text !== undefined) content.set(target, text);
    return text !== undefined;
  };

  context.subscriptions.push(
    content,
    vscode.workspace.registerTextDocumentContentProvider(SCHEME, content),

    vscode.commands.registerCommand("mapcan.openPreview", async () => {
      const map = currentMap();
      if (!map) return;
      const target = previewUri(map, path.parse(map.fsPath).name);
      if (await renderInto(map, target)) {
        await vscode.commands.executeCommand("markdown.showPreviewToSide", target);
      }
    }),

    // The document preview follows edits of its map.
    vscode.workspace.onDidChangeTextDocument((e) => {
      const target = previewUri(e.document.uri, path.parse(e.document.uri.fsPath).name);
      if (!content.has(target)) return;
      clearTimeout(timer);
      timer = setTimeout(() => void renderInto(e.document.uri, target), 500);
    }),

    vscode.commands.registerCommand("mapcan.compareWithRevision", async () => {
      const map = currentMap();
      if (!map || map.scheme !== "file") return;
      const cwd = path.dirname(map.fsPath);
      const file = path.basename(map.fsPath);
      let log: string;
      try {
        log = await git(cwd, ["log", "--format=%H%x1f%h%x1f%ad%x1f%s", "--date=short", "-n", "100", "--", file]);
      } catch {
        void vscode.window.showErrorMessage("mapcan: the map is not in a Git repository.");
        return;
      }
      const items = log.split("\n").filter(Boolean).map((line) => {
        const [hash, short, date, subject] = line.split("\x1f");
        return { label: subject, description: `${short} · ${date}`, hash, short };
      });
      if (items.length === 0) {
        void vscode.window.showInformationMessage("mapcan: the map has no committed versions yet.");
        return;
      }
      const picked = await vscode.window.showQuickPick(items, {
        title: "mapcan: Compare with Revision",
        placeHolder: "Version to compare the current map with",
        matchOnDescription: true,
      });
      if (!picked) return;
      let oldText: string;
      try {
        oldText = await git(cwd, ["show", `${picked.hash}:./${file}`]);
      } catch {
        void vscode.window.showErrorMessage(`mapcan: the map does not exist in ${picked.short}.`);
        return;
      }
      const text = await serverText(client(), "mapcan.lsp.diff", { uri: map.toString(), oldText });
      if (text === undefined) return;
      const target = previewUri(map, `${path.parse(file).name} since ${picked.short}`);
      content.set(target, text.trim() ? text : "No changes.\n");
      await vscode.commands.executeCommand("markdown.showPreviewToSide", target);
    }),
  );
}
