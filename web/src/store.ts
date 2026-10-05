// Глобальное состояние редактора.

import { computed, reactive } from "vue";
import { api, ApiError, connectEvents } from "./api";
import { buildTree, diagIndex, framePathOf, getAt, pathKey } from "./model";
import type { Meta, Op, Path, PdfTemplate, ResolvedFrame, SessionResult, State, UpdateInfo } from "./types";

interface Toast {
  id: number;
  kind: "error" | "info";
  text: string;
}

export type DialogKind = "open" | "new" | "saveas" | "profile" | null;

function savedTemplate(): string {
  try {
    return localStorage.getItem("canmap-pdf-template") ?? "canmap";
  } catch {
    return "canmap";
  }
}

export const store = reactive({
  meta: null as Meta | null,
  pdfTemplates: [] as PdfTemplate[],
  pdfTemplate: savedTemplate(),                // выбранный шаблон PDF (запоминается в браузере)
  state: null as State | null,
  dialog: null as DialogKind,
  selected: ["document"] as Path,
  tab: "editor" as "editor" | "yaml",
  busy: false,
  online: true,
  fileChangedBanner: false,
  toasts: [] as Toast[],
  muxView: {} as Record<string, number | null>, // выбранное значение селектора по кадру
  revealLine: null as number | null,           // строка для перехода во вкладке YAML
  update: null as UpdateInfo | null,           // доступная новая версия (плашка вверху)
});

let toastId = 0;
export function toast(text: string, kind: Toast["kind"] = "error"): void {
  const t = { id: ++toastId, kind, text };
  store.toasts.push(t);
  setTimeout(() => {
    const i = store.toasts.indexOf(t);
    if (i >= 0) store.toasts.splice(i, 1);
  }, kind === "error" ? 7000 : 3000);
}

function accept(s: State): void {
  store.state = s;
  if (s.disk_changed) store.fileChangedBanner = true;
  // Выбранный узел мог исчезнуть (удаление, undo) — поднимаемся к существующему предку.
  if (s.data) {
    let p = store.selected;
    while (p.length > 1 && getAt(s.data, p) === undefined) p = p.slice(0, -1);
    if (p.length === 1 && p[0] !== "document" && getAt(s.data, p) === undefined) p = ["document"];
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
  store.muxView = {};
  store.tab = "editor";
  store.state = null;
  if (r.state) {
    accept(r.state);
    if (!r.state.data) store.tab = "yaml";
  }
}

/** Операция со сменой файла; при несохранённых правках спрашивает, что с ними делать. */
async function switchFile(fn: (force: boolean) => Promise<SessionResult>, okText?: string): Promise<boolean> {
  store.busy = true;
  try {
    try {
      acceptSession(await fn(false));
    } catch (e) {
      if (!(e instanceof ApiError && e.code === "unsaved")) throw e;
      if (confirm(`${e.message}.

Сохранить их перед продолжением?`)) {
        accept(await api.save());
      } else if (!confirm("Продолжить без сохранения? Несохранённые изменения будут потеряны.")) {
        return false;
      }
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
  newFile: (path: string, template: string, title: string, overwrite = false) =>
    switchFile((force) => api.newFile({ path, template, title, force, overwrite }), "Создана новая карта"),
  saveAs: async (path: string, overwrite = false): Promise<boolean> => {
    try {
      acceptSession(await api.saveAs(path, overwrite));
      toast("Сохранено", "info");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "exists" && confirm(`${e.message}

Перезаписать?`)) {
        return actions.saveAs(path, true);
      }
      if (!(e instanceof ApiError && e.code === "exists")) toast(e instanceof Error ? e.message : String(e));
      return false;
    }
  },
  closeFile: () => switchFile((force) => api.close(force)),
  apply: (ops: Op[]) => {
    if (store.state?.readonly) {
      toast("Режим только для чтения");
      return Promise.resolve(false);
    }
    return run(() => api.ops(ops));
  },
  setText: (text: string) => run(() => api.text(text)),
  undo: () => run(api.undo),
  redo: () => run(api.redo),
  reload: async () => {
    store.fileChangedBanner = false;
    return run(api.reload, "Файл перечитан с диска");
  },
  save: async (force = false): Promise<void> => {
    store.busy = true;
    try {
      accept(await api.save(force));
      store.fileChangedBanner = false;
      toast("Сохранено", "info");
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        if (confirm("Файл изменён на диске другой программой.\nПерезаписать его вашей версией?")) {
          return actions.save(true);
        }
      } else {
        toast(e instanceof Error ? e.message : String(e));
      }
    } finally {
      store.busy = false;
    }
  },
  select: (p: Path) => {
    store.selected = p;
  },
  setPdfTemplate: (name: string) => {
    store.pdfTemplate = name;
    try {
      localStorage.setItem("canmap-pdf-template", name);
    } catch {
      /* хранилище недоступно */
    }
  },
};

// ------------------------------------------------------------------ производные

export const lang = computed(() => store.state?.resolved?.language ?? store.state?.data?.document?.language ?? "ru");

export const resolvedFrames = computed(() => {
  const m = new Map<string, ResolvedFrame>();
  for (const f of store.state?.resolved?.frames ?? []) m.set(pathKey(f.path), f);
  return m;
});

export const tree = computed(() => (store.state?.data ? buildTree(store.state.data, resolvedFrames.value, lang.value) : []));

export const diagsByNode = computed(() => diagIndex(store.state?.diagnostics ?? []));

export const selectedFramePath = computed(() => framePathOf(store.selected));

export const selectedResolvedFrame = computed(() => {
  const fp = selectedFramePath.value;
  return fp ? resolvedFrames.value.get(pathKey(fp)) : undefined;
});

// ------------------------------------------------------------------ события

export function startEvents(): void {
  connectEvents(
    (m) => {
      if (m.type === "file-changed") store.fileChangedBanner = true;
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
    // e.code — физическая клавиша: сочетания работают и в русской раскладке.
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
    if (store.state?.dirty) e.preventDefault();
  });
}
