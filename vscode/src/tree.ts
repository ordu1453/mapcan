// The Map view: buses, devices, frames, signals and flags of the active map, from the
// language server's document symbols. Follows the cursor and reveals nodes on click.

import * as vscode from "vscode";
import { DocumentSymbol, DocumentSymbolRequest, LanguageClient } from "vscode-languageclient/node";

const MAP_HEADER = /^(mapcan|canmap)\s*:/m;

export function isMap(doc: vscode.TextDocument | undefined): doc is vscode.TextDocument {
  return doc !== undefined && doc.languageId === "yaml" && MAP_HEADER.test(doc.getText());
}

// Kinds the server sends for each level of the map.
const KIND: Partial<Record<vscode.SymbolKind, { context: string; icon: string }>> = {
  [vscode.SymbolKind.Namespace]: { context: "bus", icon: "symbol-namespace" },
  [vscode.SymbolKind.Module]: { context: "device", icon: "symbol-module" },
  [vscode.SymbolKind.Struct]: { context: "frame", icon: "symbol-struct" },
  [vscode.SymbolKind.Field]: { context: "signal", icon: "symbol-field" },
  [vscode.SymbolKind.Boolean]: { context: "flag", icon: "symbol-boolean" },
};

export class MapNode {
  readonly children: MapNode[];

  constructor(
    readonly symbol: vscode.DocumentSymbol,
    readonly id: string,
    readonly parent: MapNode | undefined,
  ) {
    this.children = symbol.children.map((c, i) => new MapNode(c, `${id}/${i}:${c.name}`, this));
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

  constructor(private readonly client: () => LanguageClient | undefined) {}

  attach(view: vscode.TreeView<MapNode>): void {
    this.view = view;
    this.subscriptions.push(
      vscode.window.onDidChangeActiveTextEditor(() => this.refresh()),
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (e.document === vscode.window.activeTextEditor?.document) {
          this.scheduleRefresh();
        }
      }),
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

  getTreeItem(node: MapNode): vscode.TreeItem {
    const s = node.symbol;
    const kind = KIND[s.kind];
    const state = node.children.length === 0
      ? vscode.TreeItemCollapsibleState.None
      : kind?.context === "bus" || kind?.context === "device"
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;
    const item = new vscode.TreeItem(s.name, state);
    item.id = node.id;
    item.description = s.detail;
    item.contextValue = kind?.context;
    item.iconPath = new vscode.ThemeIcon(kind?.icon ?? "symbol-misc");
    item.command = {
      command: "mapcan.revealNode",
      title: "Reveal",
      arguments: [this.uri, s.selectionRange],
    };
    return item;
  }

  getChildren(node?: MapNode): MapNode[] {
    return node ? node.children : this.roots;
  }

  getParent(node: MapNode): MapNode | undefined {
    return node.parent;
  }

  async refresh(): Promise<void> {
    const doc = vscode.window.activeTextEditor?.document;
    if (!isMap(doc)) {
      // Keep showing the last map while another editor (e.g. Output) is focused, unless it was closed.
      if (this.uri && !vscode.workspace.textDocuments.some((d) => d.uri.toString() === this.uri!.toString())) {
        this.setRoots(undefined, []);
      }
      return;
    }
    const client = this.client();
    if (!client?.isRunning()) {
      return;
    }
    const result = await client.sendRequest(DocumentSymbolRequest.type, {
      textDocument: { uri: doc.uri.toString() },
    });
    const symbols = result
      ? await client.protocol2CodeConverter.asDocumentSymbols(
          result.filter((s): s is DocumentSymbol => "selectionRange" in s),
        )
      : [];
    this.setRoots(doc.uri, symbols.map((s, i) => new MapNode(s, `${i}:${s.name}`, undefined)));
    this.scheduleReveal();
  }

  private setRoots(uri: vscode.Uri | undefined, roots: MapNode[]): void {
    this.uri = uri;
    this.roots = roots;
    void vscode.commands.executeCommand("setContext", "mapcan.mapOpen", uri !== undefined);
    if (this.view) {
      this.view.description = uri ? vscode.workspace.asRelativePath(uri) : undefined;
    }
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

  /** Select the deepest node containing the cursor of the active editor. */
  private async revealCursor(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!this.view?.visible || !editor || editor.document.uri.toString() !== this.uri?.toString()) {
      return;
    }
    const pos = editor.selection.active;
    let found: MapNode | undefined;
    let level = this.roots;
    for (;;) {
      const next = level.find((n) => n.symbol.range.contains(pos));
      if (!next) {
        break;
      }
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
