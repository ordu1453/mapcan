// The Map view: the same tree as the web editor's (buses, devices, frames, signals, flags, SDO
// exchanges, frames a device receives) from the language server's `mapcan/tree` request.
// Clicking a node selects it in the editor; moving the cursor selects the node under it.
// Nodes with problems are colored like files in the Explorer; nodes changed since the last commit
// are marked like files in Source Control (A — added, M — modified).

import * as vscode from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

const MAP_HEADER = /^(mapcan|canmap)\s*:/m;
/** A file included by a map (`part_of:`): the server analyses it as a part of that map. */
const PART_HEADER = /^part_of\s*:/m;
const DECORATION_SCHEME = "mapcan-node";

/** A map open for editing, or a file included by one: versions from the history (read-only documents) are not. */
export function isMap(doc: vscode.TextDocument | undefined): doc is vscode.TextDocument {
  if (doc === undefined || (doc.uri.scheme !== "file" && doc.uri.scheme !== "untitled") || doc.languageId !== "yaml") {
    return false;
  }
  const text = doc.getText();
  return MAP_HEADER.test(text) || PART_HEADER.test(text);
}

export type Kind = "bus" | "device" | "frame" | "signal" | "flag" | "sdo";

export const KIND_TITLE: Record<Kind, string> = {
  bus: "Bus", device: "Device", frame: "Frame", signal: "Signal", flag: "Flag", sdo: "SDO exchange",
};

/**
 * A node as the server sends it; ranges are [line, character, line, character]. The label is the
 * human-readable title, as in the web editor's tree; `ident` is the identifier from YAML.
 */
interface RawNode {
  kind: Kind;
  label: string;
  ident?: string;
  description: string;
  dir?: "tx" | "rx" | null;
  from?: string;
  path: (string | number)[];
  name: [number, number] | null;
  range: [number, number, number, number];
  selection: [number, number, number, number];
  children: RawNode[];
  /** The node comes from an included file (`include`): its full path; ranges are in that file. */
  file?: string;
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

  get kind(): Kind {
    return this.raw.kind;
  }

  get path(): (string | number)[] {
    return this.raw.path;
  }

  /** Position of the node's name value, for rename. */
  get namePosition(): vscode.Position | undefined {
    return this.raw.name ? new vscode.Position(this.raw.name[0], this.raw.name[1]) : undefined;
  }

  /** Links to frames of other devices are not part of this node's text. */
  get isLink(): boolean {
    return this.raw.from !== undefined;
  }

  /** The other file of the map the node is described in: its edits go to that file. */
  get file(): vscode.Uri | undefined {
    return this.raw.file ? vscode.Uri.file(this.raw.file) : undefined;
  }

  /** The node's text is in the map itself (not a link, not from an included file). */
  get isOwn(): boolean {
    return !this.isLink && !this.raw.file;
  }
}

type Level = "error" | "warning";
export type ChangeStatus = "added" | "modified";

const pathKey = (path: (string | number)[]) => JSON.stringify(path.map(String));

export class MapTree implements vscode.TreeDataProvider<MapNode>, vscode.FileDecorationProvider, vscode.Disposable {
  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private readonly decorationsChanged = new vscode.EventEmitter<undefined>();
  readonly onDidChangeFileDecorations = this.decorationsChanged.event;

  private roots: MapNode[] = [];
  private uri: vscode.Uri | undefined;
  private view: vscode.TreeView<MapNode> | undefined;
  private refreshTimer: NodeJS.Timeout | undefined;
  private revealTimer: NodeJS.Timeout | undefined;
  /** Problems per node id: the worst level and how many belong to the node itself. */
  private problems = new Map<string, { level: Level; own: number }>();
  /** Changes since the last commit by node path; nodes with changed descendants by node id. */
  private changes = new Map<string, ChangeStatus>();
  private changedInside = new Set<string>();
  private readonly refreshed = new vscode.EventEmitter<void>();
  /** The map was read again (another map, or its text changed). */
  readonly onDidRefresh = this.refreshed.event;
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(
    private readonly media: vscode.Uri,
    private readonly client: () => LanguageClient | undefined,
  ) {}

  attach(view: vscode.TreeView<MapNode>): void {
    this.view = view;
    this.subscriptions.push(
      vscode.window.registerFileDecorationProvider(this),
      vscode.window.onDidChangeActiveTextEditor(() => this.refresh()),
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (e.document.uri.toString() === this.uri?.toString() || e.document === vscode.window.activeTextEditor?.document) {
          this.scheduleRefresh();
        }
      }),
      vscode.workspace.onDidCloseTextDocument(() => this.refresh()),
      vscode.languages.onDidChangeDiagnostics((e) => {
        if (this.uri && e.uris.some((u) => u.toString() === this.uri!.toString())) {
          this.updateProblems();
          this.changed.fire();
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

  private icon(name: string): { light: vscode.Uri; dark: vscode.Uri } {
    return {
      light: vscode.Uri.joinPath(this.media, "tree", "light", `${name}.svg`),
      dark: vscode.Uri.joinPath(this.media, "tree", "dark", `${name}.svg`),
    };
  }

  getTreeItem(node: MapNode): vscode.TreeItem {
    const { kind, label, ident, description, dir, from } = node.raw;
    const state = node.children.length === 0
      ? vscode.TreeItemCollapsibleState.None
      : kind === "bus" || kind === "device"
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;
    const item = new vscode.TreeItem(label, state);
    item.id = node.id;
    item.description = from !== undefined ? `${description} ↪`.trim() : description;
    // A node of another file is edited in that file
    item.contextValue = node.isLink ? "frameLink" : node.file ? `${kind}.included` : kind;
    // The identifier is not in the label (only titles are), so the tooltip shows it
    const lines = [`${KIND_TITLE[kind]} ${ident ?? label}`];
    if (kind === "frame") {
      item.iconPath = this.icon(dir === "tx" ? "frame-tx" : dir === "rx" ? "frame-rx" : "frame-broadcast");
      lines.push(from !== undefined
        ? `Received from ${from || "outside the map"}`
        : dir === "tx" ? "TX" : dir === "rx" ? "RX" : "Broadcast");
    } else {
      item.iconPath = this.icon(kind);
    }
    const problem = node.isLink ? undefined : this.problems.get(node.id);
    const change = node.isLink ? undefined : this.changes.get(pathKey(node.path));
    const inside = !node.isLink && this.changedInside.has(node.id);
    if (problem || change || inside) {
      // Only the decoration provider reads this URI: it colors the label like a file with problems
      // or with changes in Source Control.
      const query = new URLSearchParams();
      if (problem) {
        query.set("level", problem.level);
        query.set("own", String(problem.own));
      }
      if (change) query.set("change", change);
      else if (inside) query.set("change", "inside");
      item.resourceUri = vscode.Uri.from({ scheme: DECORATION_SCHEME, path: `/${node.id}`, query: query.toString() });
    }
    if (change) lines.push(change === "added" ? "Added since the last commit" : "Modified since the last commit");
    // The map is one tree whatever file it is split into: the file is only named here, and clicking the node
    // opens it there
    if (node.file && !node.isLink) lines.push(`In ${vscode.workspace.asRelativePath(node.file)}`);
    item.tooltip = lines.join("\n");
    item.command = { command: "mapcan.revealNode", title: "Reveal", arguments: [node.file ?? this.uri, node.selection] };
    return item;
  }

  provideFileDecoration(uri: vscode.Uri): vscode.FileDecoration | undefined {
    if (uri.scheme !== DECORATION_SCHEME) {
      return undefined;
    }
    const query = new URLSearchParams(uri.query);
    const level = query.get("level");
    const count = Number(query.get("own") ?? 0);
    const change = query.get("change");
    // Problems are shown over changes, as in the Explorer
    if (count > 0 || (level && change !== "added" && change !== "modified")) {
      return {
        color: new vscode.ThemeColor(level === "error" ? "list.errorForeground" : "list.warningForeground"),
        badge: count > 0 ? (count > 9 ? "9+" : String(count)) : undefined,
        tooltip: count > 0 ? `${count} problem${count === 1 ? "" : "s"}` : undefined,
      };
    }
    if (change === "added" || change === "modified") {
      return {
        color: new vscode.ThemeColor(level === "error" ? "list.errorForeground" : level === "warning"
          ? "list.warningForeground" : change === "added" ? "gitDecoration.addedResourceForeground"
            : "gitDecoration.modifiedResourceForeground"),
        badge: change === "added" ? "A" : "M",
        tooltip: change === "added" ? "Added" : "Modified",
      };
    }
    // Changes inside a node: colored like a folder with changed files, without a badge
    return change === "inside" ? { color: new vscode.ThemeColor("gitDecoration.modifiedResourceForeground") } : undefined;
  }

  /** Marks nodes changed since the last commit; an empty list removes the marks. */
  setChanges(nodes: { path: (string | number)[]; status: ChangeStatus }[]): void {
    const changes = new Map(nodes.map((n) => [pathKey(n.path), n.status] as const));
    if (changes.size === this.changes.size && [...changes].every(([k, v]) => this.changes.get(k) === v)) return;
    this.changes = changes;
    this.updateChangedInside();
    this.changed.fire();
  }

  private updateChangedInside(): void {
    this.changedInside.clear();
    for (const node of this.nodes()) {
      if (!this.changes.has(pathKey(node.path))) continue;
      for (let p = node.parent; p; p = p.parent) this.changedInside.add(p.id);
    }
  }

  getChildren(node?: MapNode): MapNode[] {
    return node ? node.children : this.roots;
  }

  getParent(node: MapNode): MapNode | undefined {
    return node.parent;
  }

  /** All nodes (not links), depth first. */
  *nodes(level: MapNode[] = this.roots): Generator<MapNode> {
    for (const n of level) {
      if (n.isLink) continue;
      yield n;
      yield* this.nodes(n.children);
    }
  }

  /** The node (not a link) at a YAML path. */
  nodeByPath(path: (string | number)[]): MapNode | undefined {
    for (const n of this.nodes()) {
      if (n.path.length === path.length && n.path.every((x, i) => String(x) === String(path[i]))) return n;
    }
    return undefined;
  }

  /** The deepest node whose text contains the position. */
  nodeAt(pos: vscode.Position): MapNode | undefined {
    let found: MapNode | undefined;
    let level = this.roots;
    for (;;) {
      const next = level.find((n) => n.isOwn && n.range.contains(pos));
      if (!next) return found;
      found = next;
      level = next.children;
    }
  }

  async refresh(): Promise<void> {
    // Refreshes overlap (switching editors fires several events, some for an editor active only for a moment):
    // only the last one sets the tree, whichever answer of the server comes last
    const generation = ++this.generation;
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
    if (generation !== this.generation) return;
    this.setRoots(doc.uri, (nodes ?? []).map((n, i) => new MapNode(n, String(i), undefined)));
    this.scheduleReveal();
  }

  private setRoots(uri: vscode.Uri | undefined, roots: MapNode[]): void {
    if (uri?.toString() !== this.uri?.toString()) this.changes.clear();
    this.uri = uri;
    this.roots = roots;
    this.updateProblems();
    this.updateChangedInside();
    void vscode.commands.executeCommand("setContext", "mapcan.mapOpen", uri !== undefined);
    this.changed.fire();
    this.refreshed.fire();
  }

  private updateProblems(): void {
    this.problems.clear();
    if (this.uri) {
      for (const d of vscode.languages.getDiagnostics(this.uri)) {
        if (d.source !== "mapcan" || d.severity > vscode.DiagnosticSeverity.Warning) continue;
        const level: Level = d.severity === vscode.DiagnosticSeverity.Error ? "error" : "warning";
        let node = this.nodeAt(d.range.start);
        let own = true;
        for (; node; node = node.parent, own = false) {
          const p = this.problems.get(node.id) ?? { level, own: 0 };
          if (level === "error") p.level = "error";
          if (own) p.own += 1;
          this.problems.set(node.id, p);
        }
      }
    }
    this.decorationsChanged.fire(undefined);
  }

  private generation = 0;

  private scheduleRefresh(): void {
    clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => void this.refresh(), 300);
  }

  private scheduleReveal(): void {
    clearTimeout(this.revealTimer);
    this.revealTimer = setTimeout(() => void this.revealCursor(), 150);
  }

  /** Select the deepest node whose text contains the cursor of the active editor. */
  async revealCursor(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    if (!this.view?.visible || !editor || editor.document.uri.toString() !== this.uri?.toString()) {
      return;
    }
    const found = this.nodeAt(editor.selection.active);
    if (found && this.view.selection[0]?.id !== found.id) {
      await revealInView(this.view, found);
    }
  }

  /** The node a tree command acts on: the clicked one, else the selected one. */
  target(node: MapNode | undefined): MapNode | undefined {
    return node ?? this.view?.selection[0];
  }

  dispose(): void {
    clearTimeout(this.refreshTimer);
    clearTimeout(this.revealTimer);
    this.changed.dispose();
    this.refreshed.dispose();
    this.decorationsChanged.dispose();
    this.subscriptions.forEach((d) => d.dispose());
  }
}

/**
 * Select a node in the tree view. Right after a refresh VS Code may not have fetched the new
 * children yet and reveal() fails with "Cannot resolve tree item": retry a few times, then give up
 * quietly (selecting the node is a convenience, not part of the edit).
 */
export async function revealInView(view: vscode.TreeView<MapNode>, node: MapNode): Promise<void> {
  for (let attempt = 0; attempt < 10; attempt++) {
    try {
      await view.reveal(node, { select: true, focus: false, expand: true });
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
}

export async function revealNode(uri: vscode.Uri | undefined, range: vscode.Range | undefined): Promise<void> {
  if (!uri || !range) {
    return;
  }
  // Focus stays in the Map view (as in Outline), so the tree can still be browsed with the keyboard.
  const editor = await vscode.window.showTextDocument(uri, { preserveFocus: true, preview: false });
  // Whole lines of the block are selected (as when clicking line numbers), with the cursor at the
  // start, so the editor shows the beginning.
  const doc = editor.document;
  const end = range.end.line + 1 < doc.lineCount
    ? new vscode.Position(range.end.line + 1, 0)
    : doc.lineAt(range.end.line).range.end;
  editor.selection = new vscode.Selection(end, new vscode.Position(range.start.line, 0));
  const lines = editor.visibleRanges[0];
  const fits = lines && range.end.line - range.start.line < lines.end.line - lines.start.line;
  editor.revealRange(fits ? range : new vscode.Range(range.start, range.start),
    fits ? vscode.TextEditorRevealType.InCenterIfOutsideViewport : vscode.TextEditorRevealType.AtTop);
}
