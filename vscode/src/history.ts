// The History view: the Git history of the map shown in the Map view, renames followed. Clicking a
// version shows what changed since it in the Markdown preview; its menu shows the changes it made,
// a YAML diff with the current text, the version itself and its commit ID. Uncommitted changes,
// unsaved edits included, are the first entry.

import { execFile } from "child_process";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { MapTree } from "./tree";
import type { ShowChanges } from "./preview";

const run = promisify(execFile);
const REVISION_SCHEME = "mapcan-rev";
const LIMIT = 200;

export interface Commit {
  hash: string;
  short: string;
  date: string;
  author: string;
  subject: string;
  /** Path of the map in this commit, relative to the repository root. */
  path: string;
  /** Path in the parent commit; undefined if the commit added the map. */
  parentPath: string | undefined;
}

export interface Uncommitted {
  latest: Commit;
}

type Entry = Commit | Uncommitted;
const isCommit = (e: Entry): e is Commit => "hash" in e;

/** Why the history is empty: shown by the view's welcome content. */
type State = "ok" | "noGit" | "noRepo" | "noCommits" | "error";

class GitError extends Error {
  constructor(readonly state: State, message: string) {
    super(message);
  }
}

export async function git(cwd: string, args: string[]): Promise<string> {
  try {
    const { stdout } = await run("git", ["-c", "core.quotepath=off", ...args], { cwd, maxBuffer: 32 * 1024 * 1024 });
    return stdout;
  } catch (err) {
    const e = err as NodeJS.ErrnoException & { stderr?: string };
    if (e.code === "ENOENT") throw new GitError("noGit", "Git is not installed.");
    const stderr = (e.stderr ?? "").trim();
    if (/not a git repository/i.test(stderr)) throw new GitError("noRepo", "The map is not in a Git repository.");
    throw new GitError("error", stderr.split("\n")[0] || e.message);
  }
}

/** Commits that changed the map, newest first. */
export async function mapLog(map: vscode.Uri): Promise<Commit[]> {
  const cwd = path.dirname(map.fsPath);
  const file = path.basename(map.fsPath);
  const prefix = (await git(cwd, ["rev-parse", "--show-prefix"])).trim();
  const out = await git(cwd, [
    "log", "--follow", `-n${LIMIT}`, "--date=short", "--name-status",
    "--format=%x1e%H%x1f%h%x1f%ad%x1f%an%x1f%s", "--", file,
  ]);
  const commits: Commit[] = [];
  let current = prefix + file;
  for (const record of out.split("\x1e").slice(1)) {
    const [header, ...rest] = record.split("\n");
    const [hash, short, date, author, subject] = header.split("\x1f");
    const status = rest.find((l) => /^[A-Z]\d*\t/.test(l))?.split("\t");
    let filePath = current;
    let parentPath: string | undefined = current;
    if (status && /^[RC]/.test(status[0])) {
      [parentPath, filePath] = [status[1], status[2]];
    } else if (status) {
      filePath = parentPath = status[1];
      if (status[0] === "A") parentPath = undefined;
    }
    commits.push({ hash, short, date, author, subject, path: filePath, parentPath });
    current = parentPath ?? filePath;
  }
  return commits;
}

const show = (map: vscode.Uri, ref: string) => git(path.dirname(map.fsPath), ["show", ref]);

/** Read-only document with the map as it was in a commit. */
function revisionUri(map: vscode.Uri, commit: Commit): vscode.Uri {
  const { name, ext } = path.parse(map.fsPath);
  return vscode.Uri.from({
    scheme: REVISION_SCHEME,
    path: `${path.posix.dirname(map.path)}/${name} (${commit.short})${ext}`,
    query: JSON.stringify({ map: map.toString(), ref: `${commit.hash}:${commit.path}` }),
  });
}

class RevisionContent implements vscode.TextDocumentContentProvider {
  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const { map, ref } = JSON.parse(uri.query) as { map: string; ref: string };
    return show(vscode.Uri.parse(map), ref);
  }
}

export class HistoryTree implements vscode.TreeDataProvider<Entry>, vscode.Disposable {
  static readonly viewId = "mapcan.history";

  private readonly changed = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.changed.event;
  private entries: Entry[] = [];
  private uri: vscode.Uri | undefined;
  private view: vscode.TreeView<Entry> | undefined;
  private stale = true;
  /** The saved file differs from the latest commit. */
  private savedChanges = false;
  private generation = 0;
  private timer: NodeJS.Timeout | undefined;
  private repoWatcher: vscode.FileSystemWatcher | undefined;
  private readonly subscriptions: vscode.Disposable[] = [];

  constructor(private readonly tree: MapTree) {}

  attach(view: vscode.TreeView<Entry>): void {
    this.view = view;
    this.subscriptions.push(
      // The Map view fires on every edit: the log is read again only for another map.
      this.tree.onDidChangeTreeData(() => {
        if (this.tree.mapUri?.toString() !== this.uri?.toString()) this.schedule(0);
        else this.updateUncommitted();
      }),
      vscode.workspace.onDidSaveTextDocument((d) => d.uri.toString() === this.uri?.toString() && this.schedule()),
      view.onDidChangeVisibility((e) => e.visible && this.stale && this.refresh()),
    );
  }

  /** The commits shown, newest first. */
  get commits(): Commit[] {
    return this.entries.filter(isCommit);
  }

  get mapUri(): vscode.Uri | undefined {
    return this.uri;
  }

  getTreeItem(entry: Entry): vscode.TreeItem {
    if (!isCommit(entry)) {
      const item = new vscode.TreeItem("Uncommitted Changes");
      item.id = "uncommitted";
      item.iconPath = new vscode.ThemeIcon("diff-modified", new vscode.ThemeColor("gitDecoration.modifiedResourceForeground"));
      item.contextValue = "uncommitted";
      item.tooltip = `Changes since ${entry.latest.short}, unsaved edits included`;
      item.command = { command: "mapcan.history.showChangesSince", title: "Show Changes", arguments: [entry] };
      return item;
    }
    const item = new vscode.TreeItem(entry.subject || "(no message)");
    item.id = entry.hash;
    item.description = `${entry.date} · ${entry.author}`;
    item.iconPath = new vscode.ThemeIcon("git-commit");
    item.contextValue = entry.parentPath === undefined ? "commit.added" : "commit";
    const tooltip = new vscode.MarkdownString();
    tooltip.appendMarkdown(`**${entry.subject.replace(/[\\`*_[\]<>]/g, "\\$&")}**\n\n`);
    tooltip.appendMarkdown(`${entry.author} · ${entry.date} · \`${entry.short}\``);
    item.tooltip = tooltip;
    item.command = { command: "mapcan.history.showChangesSince", title: "Show Changes", arguments: [entry] };
    return item;
  }

  getChildren(entry?: Entry): Entry[] {
    return entry ? [] : this.entries;
  }

  async refresh(): Promise<void> {
    const map = this.tree.mapUri;
    this.uri = map;
    if (!this.view?.visible) {
      this.stale = true;
      return;
    }
    this.stale = false;
    const generation = ++this.generation;
    let commits: Commit[] = [];
    let savedChanges = false;
    let state: State = "ok";
    let message: string | undefined;
    if (map?.scheme === "file") {
      try {
        const cwd = path.dirname(map.fsPath);
        const [log, status] = await Promise.all([
          mapLog(map),
          git(cwd, ["status", "--porcelain", "--", path.basename(map.fsPath)]),
        ]);
        commits = log;
        savedChanges = status.trim() !== "";
        if (commits.length === 0) state = "noCommits";
        if (commits.length === LIMIT) message = `Latest ${LIMIT} commits`;
      } catch (err) {
        state = err instanceof GitError ? err.state : "error";
        if (state === "error") message = err instanceof Error ? err.message : String(err);
      }
    } else if (map) {
      state = "noCommits";
    }
    if (generation !== this.generation) return;
    this.watchRepo(map, state);
    this.entries = commits;
    this.savedChanges = savedChanges;
    this.view.message = message;
    void vscode.commands.executeCommand("setContext", "mapcan.historyState", map ? state : "ok");
    this.updateUncommitted(true);
  }

  /** Shows the uncommitted entry for unsaved edits or a saved file that differs from the latest commit. */
  private updateUncommitted(force = false): void {
    const commits = this.commits;
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === this.uri?.toString());
    const dirty = commits.length > 0 && (this.savedChanges || (doc?.isDirty ?? false));
    const shown = commits.length !== this.entries.length;
    if (!force && shown === dirty) return;
    this.entries = dirty ? [{ latest: commits[0] }, ...commits] : commits;
    this.changed.fire();
  }

  /** Refreshes on commits, checkouts and staging in the map's repository. */
  private watchRepo(map: vscode.Uri | undefined, state: State): void {
    this.repoWatcher?.dispose();
    this.repoWatcher = undefined;
    if (!map || state === "noGit" || state === "noRepo") return;
    void git(path.dirname(map.fsPath), ["rev-parse", "--absolute-git-dir"]).then((dir) => {
      if (map.toString() !== this.uri?.toString()) return;
      const pattern = new vscode.RelativePattern(vscode.Uri.file(dir.trim()), "{HEAD,index,refs/**}");
      this.repoWatcher = vscode.workspace.createFileSystemWatcher(pattern);
      const changed = () => this.schedule();
      this.repoWatcher.onDidChange(changed);
      this.repoWatcher.onDidCreate(changed);
      this.repoWatcher.onDidDelete(changed);
    }, () => undefined);
  }

  private schedule(delay = 500): void {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.refresh(), delay);
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.repoWatcher?.dispose();
    this.changed.dispose();
    this.subscriptions.forEach((d) => d.dispose());
  }
}

/** Runs a history command, reporting Git errors instead of failing silently. */
function guarded<A extends unknown[]>(fn: (...args: A) => Promise<unknown>): (...args: A) => Promise<void> {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (err) {
      void vscode.window.showErrorMessage(`mapcan: ${err instanceof Error ? err.message : String(err)}`);
    }
  };
}

export function registerHistory(
  context: vscode.ExtensionContext,
  history: HistoryTree,
  currentMap: () => vscode.Uri | undefined,
  showChanges: ShowChanges,
): void {
  const map = () => history.mapUri;
  const fileName = (uri: vscode.Uri) => path.basename(uri.fsPath);
  const stem = (uri: vscode.Uri) => path.parse(uri.fsPath).name;
  const latest = (e: Entry) => (isCommit(e) ? e : e.latest);

  const changesSince = async (commit: Commit, uri: vscode.Uri) => {
    const oldText = await show(uri, `${commit.hash}:${commit.path}`);
    await showChanges(uri, `${stem(uri)} since ${commit.short}`, oldText);
  };

  context.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider(REVISION_SCHEME, new RevisionContent()),

    vscode.commands.registerCommand("mapcan.history.refresh", () => history.refresh()),

    vscode.commands.registerCommand("mapcan.history.showChangesSince", guarded(async (e: Entry) => {
      const uri = map();
      if (uri) await changesSince(latest(e), uri);
    })),

    vscode.commands.registerCommand("mapcan.history.showCommitChanges", guarded(async (c: Commit) => {
      const uri = map();
      if (!uri || c.parentPath === undefined) return;
      const [oldText, newText] = await Promise.all([
        show(uri, `${c.hash}^:${c.parentPath}`),
        show(uri, `${c.hash}:${c.path}`),
      ]);
      await showChanges(uri, `${stem(uri)} in ${c.short}`, oldText, newText);
    })),

    vscode.commands.registerCommand("mapcan.history.openDiff", async (e: Entry) => {
      const uri = map();
      if (!uri) return;
      const c = latest(e);
      await vscode.commands.executeCommand("vscode.diff", revisionUri(uri, c), uri,
        `${fileName(uri)} (${c.short}) ↔ ${fileName(uri)}`);
    }),

    vscode.commands.registerCommand("mapcan.history.openVersion", async (c: Commit) => {
      const uri = map();
      if (uri) await vscode.window.showTextDocument(revisionUri(uri, c), { preview: true });
    }),

    vscode.commands.registerCommand("mapcan.history.copyCommitId", async (c: Commit) => {
      await vscode.env.clipboard.writeText(c.hash);
    }),

    vscode.commands.registerCommand("mapcan.compareWithRevision", guarded(async () => {
      const uri = currentMap();
      if (!uri) {
        void vscode.window.showInformationMessage("mapcan: open a map first.");
        return;
      }
      if (uri.scheme !== "file") {
        void vscode.window.showInformationMessage("mapcan: save the map to compare it with its history.");
        return;
      }
      const commits = await mapLog(uri);
      if (commits.length === 0) {
        void vscode.window.showInformationMessage("mapcan: the map has no commits yet.");
        return;
      }
      const picked = await vscode.window.showQuickPick(
        commits.map((c) => ({ label: c.subject, description: `${c.short} · ${c.date} · ${c.author}`, commit: c })),
        { title: "Compare with Revision", placeHolder: "Version to compare the current map with", matchOnDescription: true },
      );
      if (picked) await changesSince(picked.commit, uri);
    })),
  );
}
