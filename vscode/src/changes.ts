// The Changes tab: what changed between two versions of a map. One tab for all comparisons, opened
// beside the editor once and then updated in place, without taking the focus.

import * as vscode from "vscode";

export interface ChangesInfo {
  /** What is compared, e.g. "Changes since a1b2c3d". */
  title: string;
  /** The commit: subject, author, date. */
  detail?: string;
}

const escape = (s: string) =>
  s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export class ChangesPanel implements vscode.Disposable {
  static readonly viewType = "mapcan.changes";

  private panel: vscode.WebviewPanel | undefined;
  /** The Markdown shown last, for the tests. */
  markdown: string | undefined;

  constructor(private readonly extensionUri: vscode.Uri) {}

  async show(map: vscode.Uri, info: ChangesInfo, markdown: string): Promise<void> {
    this.markdown = markdown;
    let body: string;
    try {
      body = await vscode.commands.executeCommand<string>("markdown.api.render", markdown);
    } catch {
      body = `<pre>${escape(markdown)}</pre>`;
    }
    const file = map.path.split("/").pop() ?? "";
    if (!this.panel) {
      this.panel = vscode.window.createWebviewPanel(
        ChangesPanel.viewType, "",
        { viewColumn: vscode.ViewColumn.Beside, preserveFocus: true },
        { localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "media")] },
      );
      this.panel.iconPath = vscode.Uri.joinPath(this.extensionUri, "media", "mapcan.svg");
      this.panel.onDidDispose(() => (this.panel = undefined));
    } else if (!this.panel.visible) {
      this.panel.reveal(undefined, true);
    }
    this.panel.title = `Changes: ${file}`;
    this.panel.webview.html = this.html(this.panel.webview, file, info, body);
  }

  private html(webview: vscode.Webview, file: string, info: ChangesInfo, body: string): string {
    const css = webview.asWebviewUri(vscode.Uri.joinPath(this.extensionUri, "media", "changes.css"));
    const csp = `default-src 'none'; style-src ${webview.cspSource}; img-src ${webview.cspSource} https: data:`;
    const detail = [file, info.detail].filter(Boolean).map((s) => escape(s!)).join(" · ");
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="${css}" rel="stylesheet">
<title>Changes</title>
</head>
<body>
<header>
<h1>${escape(info.title)}</h1>
<p class="detail">${detail}</p>
</header>
<article>${body}</article>
</body>
</html>`;
  }

  dispose(): void {
    this.panel?.dispose();
  }
}
