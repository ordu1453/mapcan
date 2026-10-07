// The Map view: the same tree as the web editor's (buses, devices, frames, signals, flags, SDO
// exchanges, frames a device receives) from the language server's `mapcan/tree` request.
// Clicking a node selects it in the editor; moving the cursor selects the node under it.

import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

const MAP_HEADER = /^(mapcan|canmap)\s*:/m;

export function isMap(doc: vscode.TextDocument | undefined): doc is vscode.TextDocument {
  return doc !== undefined && doc.languageId === "yaml" && MAP_HEADER.test(doc.getText());
}

type Kind = "bus" | "device" | "frame" | "signal" | "flag" | "sdo";

/** A node as the server sends it; ranges are [line, character, line, character]. */
interface RawNode {
  kind: Kind;
  label: string;
  description: string;
  dir?: "tx" | "rx" | null;
  from?: string;
  range: [number, number, number, number];
  selection: [number, number, number, number];
  children: RawNode[];
}

const toRange = (r: number[]) => new vscode.Range(r[0], r[1], r[2], r[3]);

export class MapNode {
  readonly children: MapNode[];
  readonly range: vscode.Range;
  readonly selection: vscode.Range;

  constructor(
    readonly raw: RawNode,
    readonly id: string,
    readonly parent: MapNode | undefined,
  ) {
    this.range = toRange(raw.range);
    this.selection = toRange(raw.selection);
    this.children = raw.children.map((c, i) => new MapNode(c, `${id}/${i}`, this));
  }

  /** Links to frames of other devices are not part of this node's text. */
  get isLink(): boolean {
    return this.raw.from !== undefined;
  }
}

export class MapTree implements vscode.TreeDataProvider<MapNode>, vscode.Disposable {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;

  private roots: MapNode[] = [];
  private uri: vscode.Uri | undefined;
  private view: vscode.TreeView<MapNode> | undefined;
  private refreshTimer: NodeJS.Timeout | undefined;
  private revealTimer: NodeJS.Timeout | undefined;
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(
    private readonly media: vscode.Uri,
    private readonly client: () => LanguageClient | undefined,
  ) {}

  attach(view: vscode.TreeView<MapNode>): void {
    this.view = view;
    this.subscriptions.push(
      vscode.window.onDidChangeActiveTextEditor(() => this.refresh()),
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (e.document.uri.toString() === this.uri?.toString() || e.document === vscode.window.activeTextEditor?.document) {
          this.scheduleRefresh();
        }
      }),
      vscode.workspace.onDidCloseTextDocument(() => this.refresh()),
      vscode.window.onDidChangeTextEditorSelection((e) => {
        if (e.textEditor === vscode.window.activeTextEditor && e.kind !== undefined) {
          this.scheduleReveal();
        }
      }),
      view.onDidChangeVisibility((e) => e.visible && this.refresh()),
    );
  }

  get mapUri(): vscode.Uri | undefined {
    return this.uri;
  }

  private icon(name: string): { light: vscode.Uri; dark: vscode.Uri } {
    return {
      light: vscode.Uri.joinPath(this.media, "tree", "light", `${name}.svg`),
      dark: vscode.Uri.joinPath(this.media, "tree", "dark", `${name}.svg`),
    };
  }

  getTreeItem(node: MapNode): vscode.TreeItem {
    const { kind, label, description, dir, from } = node.raw;
    const state = node.children.length === 0
      ? vscode.TreeItemCollapsibleState.None
      : kind === "bus" || kind === "device"
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;
    const item = new vscode.TreeItem(label, state);
    item.id = node.id;
    item.description = from !== undefined ? `${description} ↪`.trim() : description;
    item.contextValue = node.isLink ? "frameLink" : kind;
    if (kind === "frame") {
      item.iconPath = this.icon(dir === "tx" ? "frame-tx" : dir === "rx" ? "frame-rx" : "frame-broadcast");
      item.tooltip = from !== undefined
        ? `Received from ${from || "outside the map"}`
        : dir === "tx" ? "TX" : dir === "rx" ? "RX" : "Broadcast";
    } else {
      item.iconPath = this.icon(kind);
    }
    item.command = { command: "mapcan.revealNode", title: "Reveal", arguments: [this.uri, node.selection] };
    return item;
  }

  getChildren(node?: MapNode): MapNode[] {
    return node ? node.children : this.roots;
  }

  getParent(node: MapNode): MapNode | undefined {
    return node.parent;
  }

  async refresh(): Promise<void> {
    const active = vscode.window.activeTextEditor?.document;
    // Another editor (Output, settings, a non-map file) keeps the last map until that map is closed.
    const doc = isMap(active)
      ? active
      : vscode.workspace.textDocuments.find((d) => d.uri.toString() === this.uri?.toString());
    const client = this.client();
    if (!isMap(doc) || !client?.isRunning()) {
      if (!isMap(doc)) this.setRoots(undefined, []);
      return;
    }
    const nodes = await client.sendRequest<RawNode[] | null>("mapcan/tree", {
      textDocument: { uri: doc.uri.toString() },
    });
    this.setRoots(doc.uri, (nodes ?? []).map((n, i) => new MapNode(n, String(i), undefined)));
    this.scheduleReveal();
  }

  private setRoots(uri: vscode.Uri | undefined, roots: MapNode[]): void {
    this.uri = uri;
    this.roots = roots;
    void vscode.commands.executeCommand("setContext", "mapcan.mapOpen", uri !== undefined);
    this.changed.fire();
  }

  private scheduleRefresh(): void {
    clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => void this.refresh(), 300);
  }

  private scheduleReveal(): void {
    clearTimeout(this.revealTimer);
    this.revealTimer = setTimeout(() => void this.revealCursor(), 150);
  }

  /** Select the deepest node whose text contains the cursor of the active editor. */
  private async revealCursor(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!this.view?.visible || !editor || editor.document.uri.toString() !== this.uri?.toString()) {
      return;
    }
    const pos = editor.selection.active;
    let found: MapNode | undefined;
    let level = this.roots;
    for (;;) {
      const next = level.find((n) => !n.isLink && n.range.contains(pos));
      if (!next) break;
      found = next;
      level = next.children;
    }
    if (found && this.view.selection[0]?.id !== found.id) {
      await this.view.reveal(found, { select: true, focus: false, expand: false });
    }
  }

  dispose(): void {
    clearTimeout(this.refreshTimer);
    clearTimeout(this.revealTimer);
    this.changed.dispose();
    this.subscriptions.forEach((d) => d.dispose());
  }
}

export async function revealNode(uri: vscode.Uri | undefined, range: vscode.Range | undefined): Promise<void> {
  if (!uri || !range) {
    return;
  }
  const editor = await vscode.window.showTextDocument(uri, { preserveFocus: false, preview: false });
  editor.selection = new vscode.Selection(range.start, range.end);
  editor.revealRange(range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
}
