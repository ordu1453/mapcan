// The History view: the Git history of the map shown in the Map view, renames followed. Clicking a
// version shows what changed since it in the Changes tab; its menu compares versions, opens or
// restores one, and records the changes in the map's own revision history (`document.history`).
// Uncommitted changes, unsaved edits included, are the first entry: commit or discard them there.

import { execFile } from "child_process";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";
import { ExecuteCommandRequest, LanguageClient } from "vscode-languageclient/node";
import { MapTree } from "./tree";
import type { ShowChanges } from "./preview";

const run = promisify(execFile);
const REVISION_SCHEME = "mapcan-rev";
const LIMIT = 200;
/** The author of revision history entries, remembered by the extension. */
const AUTHOR_KEY = "mapcan.history.author";

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
type State = "ok" | "noGit" | "noRepo" | "noCommits" | "unsaved" | "error";

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
  /** The version chosen with Select for Compare. */
  private selectedCommit: Commit | undefined;
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

  /** The uncommitted entry is shown. */
  get hasChanges(): boolean {
    return this.entries.length > 0 && !isCommit(this.entries[0]);
  }

  get selected(): Commit | undefined {
    return this.selectedCommit;
  }

  set selected(commit: Commit | undefined) {
    this.selectedCommit = commit;
    void vscode.commands.executeCommand("setContext", "mapcan.historySelected", commit !== undefined);
    this.changed.fire();
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
    if (entry.hash === this.selectedCommit?.hash) item.description += " · selected";
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
    if (map?.toString() !== this.uri?.toString() && this.selectedCommit) this.selected = undefined;
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
      state = "unsaved";
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
    if (!force && this.hasChanges === dirty) return;
    this.entries = dirty ? [{ latest: commits[0] }, ...commits] : commits;
    void vscode.commands.executeCommand("setContext", "mapcan.historyChanges", dirty);
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

/** Runs a language server command; its `{error}` answer is thrown. */
async function serverCommand<T>(client: LanguageClient | undefined, command: string, args: object): Promise<T> {
  if (!client?.isRunning()) throw new Error("the language server is not running.");
  const result = (await client.sendRequest(ExecuteCommandRequest.type, { command, arguments: [args] })) as
    | (T & { error?: string })
    | null;
  if (!result) throw new Error(`no answer to ${command}.`);
  if (result.error) throw new Error(result.error);
  return result;
}

/** Replaces the text of a document with one edit, so Undo restores it. */
async function replaceText(uri: vscode.Uri, text: string): Promise<vscode.TextDocument> {
  const doc = await vscode.workspace.openTextDocument(uri);
  const edit = new vscode.WorkspaceEdit();
  edit.replace(uri, new vscode.Range(0, 0, doc.lineCount, 0), text);
  await vscode.workspace.applyEdit(edit);
  return doc;
}

interface HistoryDraft {
  version: string;
  date: string;
  author: string | null;
  github: string | null;
  changes: string[];
}

export function registerHistory(
  context: vscode.ExtensionContext,
  history: HistoryTree,
  currentMap: () => vscode.Uri | undefined,
  showChanges: ShowChanges,
  client: () => LanguageClient | undefined,
): void {
  const map = () => history.mapUri;
  const fileName = (uri: vscode.Uri) => path.basename(uri.fsPath);
  const latest = (e: Entry) => (isCommit(e) ? e : e.latest);

  const detail = (c: Commit) => `${c.subject} · ${c.author}, ${c.date}`;
  const commit = async (uri: vscode.Uri, message: string) => {
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
    if (doc?.isDirty && !(await doc.save())) return;
    const cwd = path.dirname(uri.fsPath);
    await git(cwd, ["add", "--", fileName(uri)]);
    await git(cwd, ["commit", "-q", "-m", message, "--", fileName(uri)]);
    await history.refresh();
    vscode.window.setStatusBarMessage(`$(check) Committed ${history.commits[0]?.short ?? ""}`, 5000);
  };

  /** Writes the entry first in `document.history`; the document's version and date follow it. */
  const addToHistory = async (uri: vscode.Uri, entry: HistoryDraft) => {
    const result = await serverCommand<{ edit: { range: [number, number, number, number]; text: string }; cursor: [number, number] }>(
      client(), "mapcan.lsp.addHistory", { uri: uri.toString(), ...entry });
    const edit = new vscode.WorkspaceEdit();
    edit.replace(uri, new vscode.Range(...result.edit.range), result.edit.text);
    if (!(await vscode.workspace.applyEdit(edit))) return;
    const editor = await vscode.window.showTextDocument(uri, { preserveFocus: true, preview: false });
    const pos = new vscode.Position(...result.cursor);
    editor.selection = new vscode.Selection(pos, pos);
    editor.revealRange(new vscode.Range(pos, pos), vscode.TextEditorRevealType.InCenterIfOutsideViewport);
  };

  const changesSince = async (commit: Commit, uri: vscode.Uri) => {
    const oldText = await show(uri, `${commit.hash}:${commit.path}`);
    await showChanges(uri, { title: `Changes since ${commit.short}`, detail: detail(commit) }, oldText);
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
      await showChanges(uri, { title: `Changes in ${c.short}`, detail: detail(c) }, oldText, newText);
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

    vscode.commands.registerCommand("mapcan.history.selectForCompare", (c: Commit) => {
      history.selected = c;
    }),

    vscode.commands.registerCommand("mapcan.history.compareWithSelected", guarded(async (c: Commit) => {
      const uri = map();
      const selected = history.selected;
      if (!uri || !selected || selected.hash === c.hash) return;
      const index = (x: Commit) => history.commits.findIndex((y) => y.hash === x.hash);
      const [older, newer] = index(c) > index(selected) ? [c, selected] : [selected, c];
      const [oldText, newText] = await Promise.all([
        show(uri, `${older.hash}:${older.path}`),
        show(uri, `${newer.hash}:${newer.path}`),
      ]);
      await showChanges(uri, {
        title: `Changes from ${older.short} to ${newer.short}`,
        detail: `${older.subject} → ${newer.subject}`,
      }, oldText, newText);
    })),

    vscode.commands.registerCommand("mapcan.history.restore", guarded(async (c: Commit) => {
      const uri = map();
      if (!uri) return;
      await replaceText(uri, await show(uri, `${c.hash}:${c.path}`));
      await vscode.window.showTextDocument(uri, { preserveFocus: true, preview: false });
      vscode.window.setStatusBarMessage(`$(history) Restored ${c.short}. Undo reverts it.`, 5000);
    })),

    vscode.commands.registerCommand("mapcan.history.discard", guarded(async (e?: Uncommitted) => {
      const uri = map();
      const latest = e?.latest ?? history.commits[0];
      if (!uri || !latest) return;
      const answer = await vscode.window.showWarningMessage(
        `Discard the changes in ${fileName(uri)} since ${latest.short}?`,
        { modal: true, detail: "Unsaved edits are lost too." },
        "Discard Changes",
      );
      if (answer !== "Discard Changes") return;
      const doc = await replaceText(uri, await show(uri, `${latest.hash}:${latest.path}`));
      await doc.save();
      await history.refresh();
    })),

    vscode.commands.registerCommand("mapcan.history.commit", guarded(async () => {
      const uri = map();
      if (!uri || uri.scheme !== "file") return;
      const message = await vscode.window.showInputBox({
        title: `Commit ${fileName(uri)}`,
        prompt: "Only this map is committed.",
        placeHolder: "Commit message",
        validateInput: (v) => (v.trim() ? undefined : "Enter a commit message"),
      });
      if (!message) return;
      await commit(uri, message.trim());
    })),

    vscode.commands.registerCommand("mapcan.history.addToHistory", guarded(async (e?: Entry) => {
      const uri = map();
      const since = e ? latest(e) : history.commits[0];
      if (!uri) return;
      if (!since) {
        void vscode.window.showInformationMessage("mapcan: the map has no commits to compare with.");
        return;
      }
      const oldText = await show(uri, `${since.hash}:${since.path}`);
      const draft = await serverCommand<HistoryDraft>(client(), "mapcan.lsp.historyDraft",
        { uri: uri.toString(), oldText });
      if (draft.changes.length === 0) {
        void vscode.window.showInformationMessage(`mapcan: no changes since ${since.short}.`);
        return;
      }
      const title = "Add to Revision History";
      const picked = await vscode.window.showQuickPick(
        draft.changes.map((label) => ({ label, picked: true })),
        { title: `${title} (1/3)`, placeHolder: `Changes since ${since.short} to record`, canPickMany: true },
      );
      if (!picked?.length) return;
      const version = await vscode.window.showInputBox({
        title: `${title} (2/3)`,
        prompt: "Version of the document",
        value: draft.version,
        validateInput: (v) => (v.trim() ? undefined : "Enter a version"),
      });
      if (!version) return;
      // The author entered last time; at first the mapcan profile's name, else Git's
      const remembered = context.globalState.get<string>(AUTHOR_KEY);
      const suggested = remembered ?? draft.author
        ?? ((await git(path.dirname(uri.fsPath), ["config", "user.name"]).catch(() => "")).trim() || undefined);
      const author = (await vscode.window.showInputBox({
        title: `${title} (3/3)`,
        prompt: "Author of the changes. Press Enter to keep the name.",
        placeHolder: "Name",
        value: suggested,
        validateInput: (v) => (v.trim() ? undefined : "Enter the author's name"),
      }))?.trim();
      if (!author) return;
      if (author !== remembered) await context.globalState.update(AUTHOR_KEY, author);
      await addToHistory(uri, {
        ...draft,
        version: version.trim(),
        author,
        // The GitHub account of the profile belongs to the profile's name only
        github: author === draft.author ? draft.github : null,
        changes: picked.map((p) => p.label),
      });
    })),

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
