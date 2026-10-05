// Глобальное состояние редактора.

import { computed, reactive } from "vue";
import { api, ApiError, connectEvents } from "./api";
import { buildTree, diagIndex, framePathOf, getAt, pathKey } from "./model";
import type { Op, Path, ResolvedFrame, State } from "./types";

interface Toast {
  id: number;
  kind: "error" | "info";
  text: string;
}

export const store = reactive({
  state: null as State | null,
  selected: ["document"] as Path,
  tab: "editor" as "editor" | "yaml",
  busy: false,
  online: true,
  fileChangedBanner: false,
  toasts: [] as Toast[],
  muxView: {} as Record<string, number | null>, // выбранное значение селектора по кадру
  revealLine: null as number | null,           // строка для перехода во вкладке YAML
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

export const actions = {
  load: () => run(api.state),
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
      else if (m.type === "state" && store.state && m.version !== store.state.version) void api.state().then(accept);
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
    const k = e.key.toLowerCase();
    if (k === "s") {
      e.preventDefault();
      void actions.save();
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
