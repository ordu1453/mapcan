// The node form in the side bar: fields of a bus, device, frame, signal, flag or SDO exchange.
// Opened by the Map view's "+" buttons (for the new node) and by "Edit…". Every change is written
// to the YAML right away by the language server (`mapcan.lsp.set`), so the editor shows it as it
// is typed and Undo works as for any other edit. While open, the form follows the tree selection.
// Frames, signals, flags and SDO exchanges also show the frame's bit layout, as in the web editor:
// dragging over free bits adds a signal, dragging a signal moves it, its edges change its length.
// Signals have their value table and flags. These changes are operations of the web editor
// (`mapcan.lsp.ops`).

import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { addOthers, Others, reportHidden, TextEdit } from "./files";
import { KIND_TITLE, Kind, MapNode, MapTree, revealInView } from "./tree";
import { webviewHtml } from "./webview";

type Path = (string | number)[];

/** The node's data as the server sends it (`mapcan/node`). */
interface NodeFields {
  kind: Kind;
  path: Path;
  lang: string;
  protocol: string;
  /** The bus is CAN FD. */
  fd: boolean;
  /** BRS of the frames as set on the bus (null: not set, on). */
  busBrs: boolean | null;
  owner: string | null;
  devices: { name: string; label: string }[];
  signalEncoding: string | null;
  /** The other file of the map the node is described in (full path): the form's changes go to that file. */
  file?: string | null;
  /** The node cannot be edited in the form. */
  readonly?: boolean;
  /** Name of a value table from value_tables when the node's values refer to one. */
  valueTableRef?: string | null;
  /** Frame direction computed from the map (tx/rx), also when the field is not set. */
  frameDirection: string | null;
  /** Signal length computed from the map (bits). */
  bitLength: number | null;
  /** Another signal of the frame is the multiplexer selector. */
  hasSelector: boolean;
  /** Fields; a nested one (the SDO exchange's value) is under "value.<field>". */
  values: Record<string, unknown>;
  /** CANopen frame types for the frame's Type field; `taken` names the frame with the same CAN ID. */
  frameTypes: { type: string; label: string; taken: string | null }[];
  /** The frame the node belongs to as the web editor shows it (signals with their bits), if the map is read. */
  frame: unknown;
  palette: string[];
  /** Rows of the value table (`values`) of a signal or flag; null — the node has none. */
  valueTable: unknown[] | null;
  /** Flags of a bit field signal; null — the signal has none. */
  flags: unknown[] | null;
}

interface SetResult {
  edits?: TextEdit[];
  others?: Others;
  error?: string;
}

interface OpsResult {
  edit?: TextEdit;
  others?: Others;
  error?: string;
}

type Message =
  | { type: "ready" }
  | { type: "set"; key: string; value: unknown }
  | { type: "ops"; ops: object[]; select?: Path }
  | { type: "select"; path: Path }
  | { type: "done" }
  | { type: "discard" }
  | { type: "reveal" }
  | { type: "rendered"; path: Path | null; fields: string[] };

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
    private readonly treeView: vscode.TreeView<MapNode>,
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
    view.webview.options = {
      enableScripts: true,
      // media/ holds the stylesheet, dist/webview/ the bundled script
      localResourceRoots: [
        vscode.Uri.joinPath(this.extensionUri, "media"),
        vscode.Uri.joinPath(this.extensionUri, "dist", "webview"),
      ],
    };
    view.webview.html = webviewHtml(view.webview, this.extensionUri, "dist/webview/form.js", "mapcan: node");
    view.webview.onDidReceiveMessage((m: Message) => this.onMessage(m));
    view.onDidDispose(() => (this.view = undefined));
  }

  /** The node and fields the webview last drew: proof that its script loaded (checked by the integration tests). */
  rendered: { path: Path | null; fields: string[] } | undefined;

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
    if (node) await vscode.commands.executeCommand("mapcan.revealNode", node.file ?? this.tree.mapUri, node.selection);
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
          const path = [...this.path, ...m.key.split(".")];
          this.queue = this.queue.then(() => this.set(path, m.value)).catch((err) => console.error(err));
        }
        break;
      case "ops":
        this.queue = this.queue.then(() => this.applyOps(m.ops, m.select)).catch((err) => console.error(err));
        break;
      case "select":
        void this.queue.then(() => this.select(m.path));
        break;
      case "done":
        void this.queue.then(() => this.close());
        break;
      case "discard":
        void this.queue.then(() => this.discard());
        break;
      case "reveal":
        void this.reveal();
        break;
      case "rendered":
        this.rendered = { path: m.path, fields: m.fields };
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
    if (result?.error) {
      void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
      return;
    }
    const edits = result?.edits ?? [];
    if (!edits.length && !result?.others?.length) return;
    const edit = new vscode.WorkspaceEdit();
    for (const e of edits) edit.replace(uri, new vscode.Range(...e.range), e.text);
    const others = addOthers(edit, result?.others);
    if (!(await vscode.workspace.applyEdit(edit))) return;
    void reportHidden(others);
    // The editor follows the form: show the line just written, without taking the focus
    const editor = vscode.window.visibleTextEditors.find((ed) => ed.document.uri.toString() === uri.toString());
    if (editor && edits.length) {
      const [sl, sc] = edits[0].range;
      const at = new vscode.Position(sl, sc);
      editor.revealRange(new vscode.Range(at, at), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    }
  }

  /** Operations of the web editor in one edit; `select` — then show that node (a signal just added). */
  private async applyOps(ops: object[], select?: Path): Promise<void> {
    const uri = this.tree.mapUri;
    const client = this.client();
    if (!uri || !client?.isRunning()) return;
    const result = (await client.sendRequest(ExecuteCommandRequest.type, {
      command: "mapcan.lsp.ops",
      arguments: [{ uri: uri.toString(), ops }],
    })) as OpsResult | null;
    if (result?.error) {
      void vscode.window.showErrorMessage(`mapcan: ${result.error}`);
      void this.refresh();
      return;
    }
    if (!result?.edit && !result?.others?.length) return;
    const edit = new vscode.WorkspaceEdit();
    if (result.edit) edit.replace(uri, new vscode.Range(...result.edit.range), result.edit.text);
    const others = addOthers(edit, result.others);
    if (!(await vscode.workspace.applyEdit(edit))) return;
    void reportHidden(others);
    if (select) {
      await this.tree.refresh();
      await this.select(select);
    }
  }

  /** Show another node of the map in the form and select it in the Map view. */
  private async select(path: Path): Promise<void> {
    if (!this.path || samePath(path, this.path)) return;
    this.created = undefined;
    this.path = path;
    await this.refresh();
    const node = this.tree.nodeByPath(path);
    if (node && this.treeView.visible) await revealInView(this.treeView, node);
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
