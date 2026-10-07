// Changes since the last commit in the Map view: the language server compares the map with its
// version in HEAD (`mapcan.lsp.changes`, the same comparison as the Changes tab) and the tree marks
// added and modified nodes as Source Control marks files. Unsaved edits count too.

import * as path from "path";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { git, HistoryTree } from "./history";
import { ChangeStatus, MapTree } from "./tree";

const SETTING = "mapcan.tree.showChanges";

export class ChangeMarks implements vscode.Disposable {
  private timer: NodeJS.Timeout | undefined;
  private generation = 0;
  /** The map in HEAD, by commit and path. */
  private base: { key: string; text: string | null } | undefined;
  /** What the marks were computed for: map, its text version and the commit. */
  private computed = "";
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(
    private readonly tree: MapTree,
    history: HistoryTree,
    private readonly client: () => LanguageClient | undefined,
  ) {
    this.subscriptions.push(
      tree.onDidRefresh(() => this.schedule()),
      // Commits, checkouts and discards are seen by the History view's repository watcher
      history.onDidChangeTreeData(() => this.schedule()),
      vscode.window.onDidChangeWindowState((e) => e.focused && this.schedule()),
      vscode.workspace.onDidChangeConfiguration((e) => e.affectsConfiguration(SETTING) && this.schedule(0, true)),
    );
  }

  private schedule(delay = 400, force = false): void {
    if (force) this.computed = "";
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.update(), delay);
  }

  async update(): Promise<void> {
    const generation = ++this.generation;
    const uri = this.tree.mapUri;
    const client = this.client();
    const enabled = vscode.workspace.getConfiguration().get<boolean>(SETTING, true);
    if (!enabled || !uri || uri.scheme !== "file" || !client?.isRunning()) {
      this.computed = "";
      this.tree.setChanges([]);
      return;
    }
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
    try {
      const cwd = path.dirname(uri.fsPath);
      const [head, prefix] = await Promise.all([
        git(cwd, ["rev-parse", "HEAD"]),
        git(cwd, ["rev-parse", "--show-prefix"]),
      ]);
      const key = `${head.trim()}:${prefix.trim()}${path.basename(uri.fsPath)}`;
      const state = `${uri.toString()}#${doc?.version ?? ""}#${key}`;
      if (state === this.computed) return;
      if (this.base?.key !== key) {
        // A map not in HEAD yet (new or untracked) has no marks, as Source Control shows it as a whole
        this.base = { key, text: await git(cwd, ["show", key]).catch(() => null) };
      }
      const oldText = this.base.text;
      if (generation !== this.generation) return;
      if (oldText === null) {
        this.computed = state;
        this.tree.setChanges([]);
        return;
      }
      const result = (await client.sendRequest(ExecuteCommandRequest.type, {
        command: "mapcan.lsp.changes",
        arguments: [{ uri: uri.toString(), oldText }],
      })) as { nodes?: { path: (string | number)[]; status: ChangeStatus }[]; error?: string } | null;
      if (generation !== this.generation || uri.toString() !== this.tree.mapUri?.toString()) return;
      // A map with errors keeps its last marks until it can be read again
      if (!result?.nodes) return;
      this.computed = state;
      this.tree.setChanges(result.nodes);
    } catch {
      // No Git, no repository or no commits yet: nothing to compare with
      if (generation !== this.generation) return;
      this.computed = "";
      this.tree.setChanges([]);
    }
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.subscriptions.forEach((d) => d.dispose());
  }
}
