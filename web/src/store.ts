// Global state of the editor.

import { computed, reactive } from "vue";
import { api, ApiError, connectEvents } from "./api";
import { t } from "./i18n";
import { buildTree, diagIndex, framePathOf, getAt, HISTORY_PATH, includedFile, localPath, nodeKind, ownerPath, pathKey,
  samePath, viewOf } from "./model";
import type { Diagnostic, Meta, Op, Path, GitStatus, PdfTemplate, ResolvedFrame, SessionResult, State, UpdateInfo } from "./types";

interface Toast {
  id: number;
  kind: "error" | "info";
  text: string;
}

export type DialogKind = "open" | "new" | "saveas" | "example" | "profile" | "git-commit" | "git-tag" | "git-release" | "git-log" | "gh-publish" | null;

function savedTemplate(): string {
  try {
    return localStorage.getItem("mapcan-pdf-template") ?? "mapcan";
  } catch {
    return "mapcan";
  }
}

export const store = reactive({
  meta: null as Meta | null,
  pdfTemplates: [] as PdfTemplate[],
  pdfTemplate: savedTemplate(),                // chosen PDF template (remembered in the browser)
  docLang: "",                                 // language of exported documents; empty: the map's language
  state: null as State | null,
  dialog: null as DialogKind,
  example: null as string | null,              // the example whose copy the "example" dialog saves
  selected: ["document"] as Path,
  tab: "editor" as "editor" | "yaml",
  busy: false,
  online: true,
  fileChangedBanner: false,
  toasts: [] as Toast[],
  muxView: {} as Record<string, number | null>, // chosen selector value per frame
  revealLine: null as number | null,           // line to go to in the YAML tab
  // File the YAML tab shows: an included file (relative to the map, a key of state.parts) or null, the map.
  // The draft below is the text of this file.
  yamlFile: null as string | null,
  // Text of the YAML tab: null shows the server's text; otherwise a draft applied while typing.
  // applied is the last applied draft (the server may have added references to it on a rename),
  // diags the validation of the unapplied draft (null: not validated yet).
  yaml: { draft: null as string | null, applied: null as string | null, diags: null as Diagnostic[] | null },
  focusPath: null as Path | null,              // form field to go to (a click on a validation message)
  // The frame is selected through a "receives" link under a device: that device's name (Delete removes it from the receivers)
  selectedVia: null as string | null,
  // The frame is selected through a link under its sender (it is described at its receiver): the sender's name.
  // Delete does nothing there: the frame is deleted at the device it is described at
  selectedSender: null as string | null,
  renameRequest: null as Path | null,          // node whose title edit opens right away in the tree
  update: null as UpdateInfo | null,           // available new version (the banner at the top)
  git: null as GitStatus | null,               // git state of the map file (the Git menu)
  gitFetching: false,                          // git fetch is running (checking what is new on the server)
  gitFetchError: "",                           // error of the last fetch
  ask: null as Ask | null,                     // the open question of askUser() (ConfirmDialog.vue)
});

export interface AskButton {
  label: string;
  value: string;
  kind?: "primary" | "danger";
}

interface Ask {
  title: string;
  message: string;
  buttons: AskButton[];
  /** A text the user edits (askText); the dialog shows a field for it. */
  input?: string;
}

let askResolve: ((v: string | null) => void) | null = null;

/** Ask the user with explicit buttons; the value of the chosen one, or null for Cancel, Esc and the close button. */
export function askUser(title: string, message: string, buttons: AskButton[]): Promise<string | null> {
  answerAsk(null);     // a question still open is cancelled
  store.ask = { title, message, buttons };
  return new Promise((resolve) => {
    askResolve = resolve;
  });
}

export function answerAsk(value: string | null): void {
  const r = askResolve;
  askResolve = null;
  store.ask = null;
  r?.(value);
}

const cancel = (): AskButton => ({ label: t("Cancel"), value: "cancel" });

/** Ask for a text, starting from `value`; the entered text, or null for Cancel, Esc and the close button. */
export async function askText(title: string, message: string, value: string, ok: string): Promise<string | null> {
  const ask: Ask = { title, message, buttons: [cancel(), { label: ok, value: "ok", kind: "primary" }], input: value };
  answerAsk(null);
  store.ask = ask;
  const answer = await new Promise<string | null>((resolve) => {
    askResolve = resolve;
  });
  return answer === "ok" ? ask.input ?? "" : null;
}

/** "Overwrite" / "Cancel": whether to overwrite. */
async function askOverwrite(message: string): Promise<boolean> {
  return (await askUser(t("Overwrite?"), message, [cancel(), { label: t("Overwrite"), value: "overwrite", kind: "danger" }]))
    === "overwrite";
}

let toastId = 0;
export function toast(text: string, kind: Toast["kind"] = "error"): void {
  const t = { id: ++toastId, kind, text };
  store.toasts.push(t);
  setTimeout(() => {
    const i = store.toasts.indexOf(t);
    if (i >= 0) store.toasts.splice(i, 1);
  }, kind === "error" ? 7000 : 3000);
}

let ownVersion = -1;   // version of the state received in answer to applying the YAML draft
let lastFetch = 0;     // time of the last git fetch (actions.fetchGit)

function accept(s: State): void {
  // Someone else's edit (undo, reload, another browser tab): a draft without unapplied input
  // gives way to the server's new text; one with unapplied input stays, as before.
  const y = store.yaml;
  if (y.draft !== null && y.draft === y.applied && s.version !== ownVersion) store.yaml = { draft: null, applied: null, diags: null };
  const before = store.state;
  store.state = s;
  // The included file of the YAML tab is gone (its device deleted, undo): the tab shows the map
  if (store.yamlFile !== null && !(s.parts && store.yamlFile in s.parts)) {
    store.yamlFile = null;
    store.yaml = { draft: null, applied: null, diags: null };
  }
  if (s.disk_changed) store.fileChangedBanner = true;
  if (s.opened_part && (before?.path !== s.path || before?.opened_part !== s.opened_part)) {
    toast(t("{file} is a part of the map {map}: the map is open, and the nodes of {file} are edited in that file",
      { file: s.opened_part, map: s.file }), "info");
  }
  // The selected node may have disappeared (deleted, undo): go up to an existing ancestor.
  if (s.data) {
    let p = store.selected;
    const view = viewOf(s);   // the selected node may also be a node of an included file
    const exists = (x: Path) => getAt(view, x) !== undefined || (samePath(x, HISTORY_PATH) && !!s.data.document);
    while (p.length > 1 && !exists(p)) p = p.slice(0, -1);
    if (p.length === 1 && p[0] !== "document" && getAt(view, p) === undefined) p = ["document"];
    // A path like […, "signals"] is a list, not a tree node: select its owner (a frame etc.)
    p = nodeKind(p) === "unknown" ? ownerPath(p) : p;
    // The link the frame was selected through is gone (the device no longer receives it): the frame itself is selected
    const receivers = getAt(view, [...p, "receivers"]);
    if (!samePath(p, store.selected) || !(Array.isArray(receivers) && receivers.includes(store.selectedVia))) {
      store.selectedVia = null;
    }
    if (!samePath(p, store.selected) || getAt(view, [...p, "sender"]) !== store.selectedSender) store.selectedSender = null;
    store.selected = p;
  }
}

async function run(fn: () => Promise<State>, okText?: string): Promise<boolean> {
  store.busy = true;
  try {
    accept(await fn());
    if (okText) toast(okText, "info");
    return true;
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e));
    return false;
  } finally {
    store.busy = false;
  }
}

function acceptSession(r: SessionResult): void {
  store.meta = r.meta;
  store.fileChangedBanner = false;
  store.selected = ["document"];
  store.selectedVia = null;
  store.selectedSender = null;
  store.muxView = {};
  store.tab = "editor";
  store.yaml = { draft: null, applied: null, diags: null };
  store.yamlFile = null;
  store.state = null;
  if (r.state) {
    accept(r.state);
    if (!r.state.data) store.tab = "yaml";
  }
}

/** An operation that changes the file; with unsaved edits it asks what to do with them. */
async function switchFile(fn: (force: boolean) => Promise<SessionResult>, okText?: string): Promise<boolean> {
  // A draft typed in the YAML tab goes to the server first, so it counts as an unsaved edit
  if (!(await actions.flushYaml())) return false;
  store.busy = true;
  try {
    try {
      acceptSession(await fn(false));
    } catch (e) {
      if (!(e instanceof ApiError && e.code === "unsaved")) throw e;
      store.busy = false;
      const answer = await askUser(t("Unsaved changes"), `${e.message}.\n\n${t("Save them before continuing?")}`, [
        cancel(),
        { label: t("Don't save"), value: "discard", kind: "danger" },
        { label: t("Save"), value: "save", kind: "primary" },
      ]);
      if (answer !== "save" && answer !== "discard") return false;
      store.busy = true;
      if (answer === "save") accept(await api.save());
      acceptSession(await fn(true));
    }
    if (okText) toast(okText, "info");
    return true;
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e));
    return false;
  } finally {
    store.busy = false;
  }
}

export const actions = {
  load: async () => {
    try {
      store.meta = await api.meta();
      if (!store.pdfTemplates.length) {
        const t = await api.templates();
        store.pdfTemplates = t.pdf;
        if (!t.pdf.some((x) => x.name === store.pdfTemplate)) store.pdfTemplate = t.default;
      }
      store.state = null;
      if (store.meta.open) accept(await api.state());
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e));
    }
  },
  refreshMeta: async () => {
    store.meta = await api.meta();
  },
  openFile: (path: string) => switchFile((force) => api.open(path, force)),
  newFile: (path: string, template: string, title: string, language: string, overwrite = false) =>
    switchFile((force) => api.newFile({ path, template, title, language, force, overwrite }), t("New map created")),
  newFromExample: (name: string, path: string, overwrite = false) =>
    switchFile(async (force) => {
      try {
        return await api.fromExample({ name, path, force, overwrite });
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "exists" && (await askOverwrite(e.message)))) throw e;
        return api.fromExample({ name, path, force, overwrite: true });
      }
    }),
  saveAs: async (path: string, overwrite = false): Promise<boolean> => {
    try {
      acceptSession(await api.saveAs(path, overwrite));
      toast(t("Saved"), "info");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "exists" && (await askOverwrite(e.message))) {
        return actions.saveAs(path, true);
      }
      if (!(e instanceof ApiError && e.code === "exists")) toast(e instanceof Error ? e.message : String(e));
      return false;
    }
  },
  closeFile: () => switchFile((force) => api.close(force)),
  apply: (ops: Op[]) => {
    if (store.state?.readonly) {
      toast(t("Read-only mode"));
      return Promise.resolve(false);
    }
    return run(() => api.ops(ops));
  },
  /** A new device of a bus in a file of its own, which the map includes (one undo step; Save writes both). */
  addDeviceFile: (bus: Path, device: Record<string, unknown>, file: string) => {
    if (store.state?.readonly) {
      toast(t("Read-only mode"));
      return Promise.resolve(false);
    }
    return run(() => api.deviceFile(bus, device, file));
  },
  /**
   * Apply the text of the YAML tab. `live`: while typing, the steps merge into one undo step and the draft
   * stays in the field as is. A normal application ends the series, and the field shows the server's text.
   */
  setText: (text: string, live = false) =>
    run(async () => {
      const s = await api.text(text, live, store.yamlFile);
      ownVersion = s.version;
      if (live && store.yaml.draft !== null) store.yaml.applied = text;
      else if (store.yaml.draft === text) store.yaml = { draft: null, applied: null, diags: null };
      return s;
    }),
  /** Apply the YAML draft before leaving the tab or saving; false if it has a syntax error. */
  flushYaml: async (): Promise<boolean> => {
    const draft = store.yaml.draft;
    if (draft === null || store.state?.readonly) return true;
    if (draft !== store.yaml.applied) {
      const err = (await api.check(draft, store.yamlFile)).diagnostics.find((d) => d.code === "yaml");
      if (err) {
        const line = yamlLine(err);
        store.tab = "yaml";
        store.revealLine = line;
        toast(t("YAML syntax error (line {line}): {message}", { line: line ?? "?", message: err.message }));
        return false;
      }
    }
    return actions.setText(draft);
  },
  setTab: async (tab: "editor" | "yaml") => {
    if (tab === store.tab) return;
    if (tab === "editor" && !(await actions.flushYaml())) return;
    // The YAML tab opens on the file the selected node is written in
    if (tab === "yaml" && store.state?.data) store.yamlFile = fileOf(store.selected);
    store.tab = tab;
  },
  /** Show the text of a file of the map in the YAML tab (null: the map), at a line; the draft of the file shown
   * before is applied first. */
  openYaml: async (file: string | null, line: number | null = null): Promise<boolean> => {
    if (file !== store.yamlFile) {
      if (!(await actions.flushYaml())) return false;
      store.yamlFile = file;
    }
    store.tab = "yaml";
    if (line !== null) store.revealLine = line;
    return true;
  },
  undo: () => run(api.undo),
  redo: () => run(api.redo),
  /** Reload the file from disk; `ask`: ask if there are unsaved edits (they and the undo history are lost). */
  reload: async (ask = true) => {
    const unsaved = !!store.state?.dirty || yamlLocal.value;
    if (ask && unsaved && (await askUser(t("Reload from disk"),
      t("Reload the file from disk? Unsaved changes will be lost."),
      [cancel(), { label: t("Reload"), value: "reload", kind: "danger" }])) !== "reload") return false;
    store.fileChangedBanner = false;
    store.yaml = { draft: null, applied: null, diags: null };
    return run(api.reload, t("Reloaded from disk"));
  },
  save: async (force = false): Promise<void> => {
    if (!force && !(await actions.flushYaml())) return;
    store.busy = true;
    try {
      accept(await api.save(force));
      store.fileChangedBanner = false;
      toast(t("Saved"), "info");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        store.busy = false;
        if (await askOverwrite(t("The file was modified on disk by another program.\nOverwrite it with your version?"))) {
          return actions.save(true);
        }
      } else {
        toast(e instanceof Error ? e.message : String(e));
      }
    } finally {
      store.busy = false;
    }
  },
  /** via: the receiving device if the frame is selected through the link to it in the tree; sender: the sending
   * device if through the link under it (the frame is described at its receiver). */
  select: (p: Path, via: string | null = null, sender: string | null = null) => {
    store.selected = p;
    store.selectedVia = via;
    store.selectedSender = sender;
    // In the YAML tab a node of another file opens that file
    if (store.tab === "yaml" && store.state?.data && fileOf(p) !== store.yamlFile) void actions.openYaml(fileOf(p));
  },
  refreshGit: async () => {
    if (!store.state || store.meta?.readonly) {
      store.git = null;
      return;
    }
    try {
      store.git = await api.gitStatus();
    } catch {
      store.git = null;
    }
  },
  /**
   * Find out from the server what is new (git fetch), for the "not pulled" counter. Without `force`, not more often than once a minute;
   * errors do not pop up but show in the Git menu.
   */
  fetchGit: async (force = false) => {
    const g = store.git;
    if (!g?.available || !g.upstream || store.gitFetching) return;
    if (!force && Date.now() - lastFetch < 60_000) return;
    lastFetch = Date.now();
    store.gitFetching = true;
    try {
      store.git = await api.gitFetch();
      store.gitFetchError = "";
    } catch (e) {
      store.gitFetchError = e instanceof Error ? e.message : String(e);
    } finally {
      store.gitFetching = false;
    }
  },
  /** Load a version of the map from git into the editor as an unsaved edit (Ctrl+Z returns the previous text). */
  restoreRevision: (rev: string) =>
    run(async () => {
      const s = await api.gitRestore(rev);
      ownVersion = s.version;
      store.yaml = { draft: null, applied: null, diags: null };
      return s;
    }, t("Version {rev} is open in the editor. Save the map to keep it, or undo (Ctrl+Z).", { rev })),
  /** A git operation (commit, tag, push, pull): updates the git state, errors show as a toast. */
  git: async (fn: () => Promise<GitStatus>, okText: string): Promise<boolean> => {
    store.busy = true;
    try {
      store.git = await fn();
      toast(okText, "info");
      return true;
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      store.busy = false;
    }
  },
  setPdfTemplate: (name: string) => {
    store.pdfTemplate = name;
    try {
      localStorage.setItem("mapcan-pdf-template", name);
    } catch {
      /* storage is not available */
    }
  },
};

// ------------------------------------------------------------------ derived

export const lang = computed(() => store.state?.resolved?.language ?? store.state?.data?.document?.language ?? "ru");

/** Document language on export: a GOST template is always Russian, otherwise the chosen one or the map's language. */
export function exportLang(fmt: string): string {
  const fixed = fmt === "pdf" ? store.pdfTemplates.find((x) => x.name === store.pdfTemplate)?.lang : null;
  return fixed ?? (store.docLang || lang.value);
}

export const resolvedFrames = computed(() => {
  const m = new Map<string, ResolvedFrame>();
  for (const f of store.state?.resolved?.frames ?? []) m.set(pathKey(f.path), f);
  return m;
});

/** Data of the map together with the included files (include): for the tree and for viewing their nodes. */
export const viewData = computed(() => viewOf(store.state));

/** Included file the node is described in (it can only be viewed); null for a node of the main file. */
export function includedPath(path: Path): string | null {
  return includedFile(store.state?.included, path);
}

/** File the node is written in, as the YAML tab shows it: an included file, or null for the map. */
function fileOf(path: Path): string | null {
  return localPath(store.state?.included, path).file;
}

/** Line of a message in the file of the YAML tab (a message about an included file is on its include line in the
 * map); null: the message is not about this file. */
export function yamlLine(d: Diagnostic): number | null {
  if (store.yamlFile === null) return d.line;
  return d.part?.file === store.yamlFile ? d.part.line : null;
}

/** Estimated load of each bus, by its path, for the tree. */
const busLoads = computed(() =>
  new Map((store.state?.resolved?.buses ?? []).map((b) => [pathKey(b.path), b] as const)));

export const tree = computed(() => (store.state?.data
  ? buildTree(viewData.value, resolvedFrames.value, lang.value, store.state.included ?? [], busLoads.value) : []));

/** The YAML field has input not applied on the server yet. */
export const yamlLocal = computed(() => store.yaml.draft !== null && store.yaml.draft !== store.yaml.applied);

/** Validation messages: for an unapplied YAML draft its validation, otherwise the server's state. */
export const diagnostics = computed(() =>
  (yamlLocal.value && store.yaml.diags) || store.state?.diagnostics || []);

export const diagsByNode = computed(() => diagIndex(store.state?.diagnostics ?? []));

export const selectedFramePath = computed(() => framePathOf(store.selected));

export const selectedResolvedFrame = computed(() => {
  const fp = selectedFramePath.value;
  return fp ? resolvedFrames.value.get(pathKey(fp)) : undefined;
});

// ------------------------------------------------------------------ events

export function startEvents(): void {
  connectEvents(
    (m) => {
      // The tab is left from a previous mapcan version and the server is updated: load the new interface
      if (m.type === "hello" && m.app && store.meta && m.app !== store.meta.version) location.reload();
      else if (m.type === "file-changed") store.fileChangedBanner = true;
      else if (m.type === "open-request") void actions.openFile(m.path);
      else if (m.type === "session" && m.session_id !== store.meta?.session_id) void actions.load();
      else if (m.type === "state" && store.state &&
        (m.session_id !== store.state.session_id || m.version !== store.state.version)) void api.state().then(accept);
    },
    (online) => {
      store.online = online;
    },
  );
}

export function installShortcuts(): void {
  window.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (!mod) return;
    const t = e.target as HTMLElement;
    const inField = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
    // e.code is the physical key: the shortcuts work in the Russian layout too.
    const k = e.code.startsWith("Key") ? e.code.slice(3).toLowerCase() : e.key.toLowerCase();
    if (k === "s" && e.shiftKey) {
      e.preventDefault();
      if (store.state) store.dialog = "saveas";
    } else if (k === "s") {
      e.preventDefault();
      if (store.state) void actions.save();
    } else if (k === "o") {
      e.preventDefault();
      store.dialog = "open";
    } else if (!inField && k === "z" && !e.shiftKey) {
      e.preventDefault();
      void actions.undo();
    } else if (!inField && (k === "y" || (k === "z" && e.shiftKey))) {
      e.preventDefault();
      void actions.redo();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    // An edit not saved yet, or a YAML draft not applied yet
    if (store.state?.dirty || yamlLocal.value) e.preventDefault();
  });
}
