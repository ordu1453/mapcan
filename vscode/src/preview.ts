// Document preview and comparison of map versions, both shown in VS Code's Markdown preview.
// The Markdown comes from the language server and lives in virtual `mapcan-preview:` documents.

import * as path from "path";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";

const SCHEME = "mapcan-preview";

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
  let result: { text?: string; error?: string } | null;
  try {
    result = await client.sendRequest(ExecuteCommandRequest.type, { command, arguments: [args] });
  } catch (err) {
    void vscode.window.showErrorMessage(`mapcan: ${err instanceof Error ? err.message : String(err)}`);
    return undefined;
  }
  if (result?.error) {
    void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
  }
  return result?.text;
}

function previewUri(map: vscode.Uri, title: string): vscode.Uri {
  return vscode.Uri.from({ scheme: SCHEME, path: `/${title}.md`, query: map.toString() });
}

/** Shows what changed between two versions of a map; without `newText` the newer one is its current text. */
export type ShowChanges = (map: vscode.Uri, title: string, oldText: string, newText?: string) => Promise<void>;

export function registerPreview(
  context: vscode.ExtensionContext,
  client: () => LanguageClient | undefined,
  currentMap: () => vscode.Uri | undefined,
): ShowChanges {
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
  );

  return async (map, title, oldText, newText) => {
    const text = await serverText(client(), "mapcan.lsp.diff", { uri: map.toString(), oldText, newText });
    if (text === undefined) return;
    const target = previewUri(map, title);
    content.set(target, text.trim() ? text : "No changes.\n");
    await vscode.commands.executeCommand("markdown.showPreviewToSide", target);
  };
}
