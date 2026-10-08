// HTML of the side bar panels (node form, export): a script and the shared stylesheet from media/,
// colors from the VS Code theme. The script is a path in the extension: media/export.js, or
// dist/webview/form.js bundled by esbuild.mjs from webview/form.js and the forms shared with the web editor.

import { randomBytes } from "crypto";
import * as vscode from "vscode";

export function webviewHtml(webview: vscode.Webview, extensionUri: vscode.Uri, script: string, title: string): string {
  const asset = (file: string) => webview.asWebviewUri(vscode.Uri.joinPath(extensionUri, ...file.split("/")));
  const media = (file: string) => asset(`media/${file}`);
  const nonce = randomBytes(16).toString("base64");
  const csp = [
    "default-src 'none'",
    `style-src ${webview.cspSource}`,
    `font-src ${webview.cspSource}`,
    `script-src 'nonce-${nonce}'`,
  ].join("; ");
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link href="${media("panel.css")}" rel="stylesheet">
<title>${title}</title>
</head>
<body>
<main id="app"></main>
<script nonce="${nonce}" src="${asset(script)}"></script>
</body>
</html>`;
}
