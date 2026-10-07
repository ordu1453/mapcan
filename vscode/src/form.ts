// The node form in the side bar: fields of a bus, device, frame, signal, flag or SDO exchange.
// Opened by the Map view's "+" buttons (for the new node) and by "Edit…". Every change is written
// to the YAML right away by the language server (`mapcan.lsp.set`), so the editor shows it as it
// is typed and Undo works as for any other edit. While open, the form follows the tree selection.

import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { KIND_TITLE, Kind, MapNode, MapTree } from "./tree";
import { webviewHtml } from "./webview";

type Path = (string | number)[];

/** The node's data as the server sends it (`mapcan/node`). */
interface NodeFields {
  kind: Kind;
  path: Path;
  lang: string;
  protocol: string;
  owner: string | null;
  devices: { name: string; label: string }[];
  signalKind: string | null;
  values: Record<string, unknown>;
}

interface SetResult {
  edits?: { range: [number, number, number, number]; text: string }[];
}

type Message =
  | { type: "ready" }
  | { type: "set"; key: string; value: unknown }
  | { type: "done" }
  | { type: "discard" };

const samePath = (a: Path, b: Path) => a.length === b.length && a.every((x, i) => String(x) === String(b[i]));

export class NodeForm implements vscode.WebviewViewProvider, vscode.Disposable {
  static readonly viewId = "mapcan.form";

  private view: vscode.WebviewView | undefined;
  private path: Path | undefined;
  /** Path of the node the "+" button has just added: Discard deletes it. */
  private created: Path | undefined;
  /** Changes are written one after another, each to the text the previous one left. */
  private queue: Promise<void> = Promise.resolve();
  private refreshTimer: NodeJS.Timeout | undefined;
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(
    private readonly extensionUri: vscode.Uri,
    private readonly tree: MapTree,
    private readonly client: () => LanguageClient | undefined,
    treeView: vscode.TreeView<MapNode>,
  ) {
    this.subscriptions.push(
      tree.onDidChangeTreeData(() => {
        if (this.path && !tree.mapUri) void this.close();
      }),
      treeView.onDidChangeSelection((e) => {
        const node = e.selection[0];
        if (this.path && node && !node.isLink && !samePath(node.path, this.path)) {
          this.created = undefined;
          this.path = node.path;
          void this.refresh();
        }
      }),
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (this.path && e.document.uri.toString() === this.tree.mapUri?.toString()) {
          clearTimeout(this.refreshTimer);
          this.refreshTimer = setTimeout(() => void this.refresh(), 300);
        }
      }),
    );
  }

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true, localResourceRoots: [vscode.Uri.joinPath(this.extensionUri, "media")] };
    view.webview.html = webviewHtml(view.webview, this.extensionUri, "form", "mapcan: node");
    view.webview.onDidReceiveMessage((m: Message) => this.onMessage(m));
    view.onDidDispose(() => (this.view = undefined));
  }

  get openPath(): Path | undefined {
    return this.path;
  }

  /** Show the form for a node; `created` — the node was just added by "+". */
  async open(path: Path, created = false): Promise<void> {
    this.path = path;
    this.created = created ? path : undefined;
    await vscode.commands.executeCommand("setContext", "mapcan.formOpen", true);
    await vscode.commands.executeCommand(`${NodeForm.viewId}.focus`);
    await this.refresh(true);
  }

  /** Select the node's lines in the editor (the panel's title button). */
  async reveal(): Promise<void> {
    const node = this.path && this.tree.nodeByPath(this.path);
    if (node) await vscode.commands.executeCommand("mapcan.revealNode", this.tree.mapUri, node.selection);
  }

  async close(): Promise<void> {
    this.path = undefined;
    this.created = undefined;
    await vscode.commands.executeCommand("setContext", "mapcan.formOpen", false);
  }

  private async fields(): Promise<NodeFields | null> {
    const uri = this.tree.mapUri;
    const client = this.client();
    if (!uri || !this.path || !client?.isRunning()) return null;
    return client.sendRequest<NodeFields | null>("mapcan/node", { textDocument: { uri: uri.toString() }, path: this.path });
  }

  /** Send the node's current values to the form; `focus` — put the cursor into the first empty required field. */
  async refresh(focus = false): Promise<void> {
    const path = this.path;
    if (!this.view || !path) return;
    const node = await this.fields();
    // The form may have been closed (and its view disposed) or moved to another node meanwhile
    if (!this.view || this.path !== path) return;
    const created = this.created !== undefined && samePath(this.created, path);
    if (node) {
      const title = (node.values.title as string) || (node.values.name as string) || "";
      this.view.title = created ? `New ${KIND_TITLE[node.kind].toLowerCase()}` : KIND_TITLE[node.kind];
      this.view.description = created ? undefined : title;
    }
    void this.view.webview.postMessage({ type: "node", node, created, focus });
  }

  private onMessage(m: Message): void {
    switch (m.type) {
      case "ready":
        void this.refresh(true);
        break;
      case "set":
        if (this.path) {
          const path = [...this.path, m.key];
          this.queue = this.queue.then(() => this.set(path, m.value)).catch((err) => console.error(err));
        }
        break;
      case "done":
        void this.queue.then(() => this.close());
        break;
      case "discard":
        void this.queue.then(() => this.discard());
        break;
    }
  }

  private async set(path: Path, value: unknown): Promise<void> {
    const uri = this.tree.mapUri;
    const client = this.client();
    if (!uri || !client?.isRunning()) return;
    const result = (await client.sendRequest(ExecuteCommandRequest.type, {
      command: "mapcan.lsp.set",
      arguments: [{ uri: uri.toString(), path, value }],
    })) as SetResult | null;
    const edits = result?.edits ?? [];
    if (!edits.length) return;
    const edit = new vscode.WorkspaceEdit();
    for (const e of edits) edit.replace(uri, new vscode.Range(...e.range), e.text);
    if (!(await vscode.workspace.applyEdit(edit))) return;
    // The editor follows the form: show the line just written, without taking the focus
    const editor = vscode.window.visibleTextEditors.find((ed) => ed.document.uri.toString() === uri.toString());
    if (editor) {
      const [sl, sc] = edits[0].range;
      const at = new vscode.Position(sl, sc);
      editor.revealRange(new vscode.Range(at, at), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    }
  }

  private async discard(): Promise<void> {
    const created = this.created;
    await this.close();
    const node = created && this.tree.nodeByPath(created);
    if (node) await vscode.commands.executeCommand("mapcan.deleteNode", node);
  }

  dispose(): void {
    clearTimeout(this.refreshTimer);
    this.subscriptions.forEach((d) => d.dispose());
  }
}
