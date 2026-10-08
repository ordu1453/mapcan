// Глобальное состояние редактора.

import { computed, reactive } from "vue";
import { api, ApiError, connectEvents } from "./api";
import { t } from "./i18n";
import { buildTree, diagIndex, framePathOf, getAt, HISTORY_PATH, includedFile, nodeKind, ownerPath, pathKey, samePath,
  viewOf } from "./model";
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
  pdfTemplate: savedTemplate(),                // выбранный шаблон PDF (запоминается в браузере)
  docLang: "",                                 // язык экспортируемых документов; пусто — язык карты
  state: null as State | null,
  dialog: null as DialogKind,
  example: null as string | null,              // пример, копию которого сохраняет диалог "example"
  selected: ["document"] as Path,
  tab: "editor" as "editor" | "yaml",
  busy: false,
  online: true,
  fileChangedBanner: false,
  toasts: [] as Toast[],
  muxView: {} as Record<string, number | null>, // выбранное значение селектора по кадру
  revealLine: null as number | null,           // строка для перехода во вкладке YAML
  // Текст вкладки YAML: null — показываем текст сервера; иначе черновик, который применяется по ходу ввода.
  // applied — последний применённый черновик (сервер мог дописать в нём ссылки при переименовании),
  // diags — проверка неприменённого черновика (null — ещё не проверен).
  yaml: { draft: null as string | null, applied: null as string | null, diags: null as Diagnostic[] | null },
  focusPath: null as Path | null,              // поле формы, к которому перейти (клик по сообщению проверки)
  // Кадр выбран через ссылку «принимает» под устройством: имя этого устройства (Delete убирает его из получателей)
  selectedVia: null as string | null,
  renameRequest: null as Path | null,          // узел, у которого в дереве сразу открыть правку названия
  update: null as UpdateInfo | null,           // доступная новая версия (плашка вверху)
  git: null as GitStatus | null,               // состояние git для файла карты (меню Git)
  gitFetching: false,                          // идёт git fetch (проверка, что нового на сервере)
  gitFetchError: "",                           // ошибка последнего fetch
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

let ownVersion = -1;   // версия состояния, полученного в ответ на применение черновика YAML
let lastFetch = 0;     // время последнего git fetch (actions.fetchGit)

function accept(s: State): void {
  // Чужая правка (undo, перечитывание, другая вкладка браузера): черновик без неприменённого ввода
  // уступает новому тексту сервера; с неприменённым — остаётся, как и раньше.
  const y = store.yaml;
  if (y.draft !== null && y.draft === y.applied && s.version !== ownVersion) store.yaml = { draft: null, applied: null, diags: null };
  store.state = s;
  if (s.disk_changed) store.fileChangedBanner = true;
  // Выбранный узел мог исчезнуть (удаление, undo) — поднимаемся к существующему предку.
  if (s.data) {
    let p = store.selected;
    const view = viewOf(s);   // выбранным может быть и узел подключённого файла
    const exists = (x: Path) => getAt(view, x) !== undefined || (samePath(x, HISTORY_PATH) && !!s.data.document);
    while (p.length > 1 && !exists(p)) p = p.slice(0, -1);
    if (p.length === 1 && p[0] !== "document" && getAt(view, p) === undefined) p = ["document"];
    // Путь вида […, "signals"] — список, а не узел дерева: выбираем его владельца (кадр и т. п.)
    p = nodeKind(p) === "unknown" ? ownerPath(p) : p;
    // Ссылка, через которую выбран кадр, исчезла (устройство больше не получатель) — выбран сам кадр
    const receivers = getAt(view, [...p, "receivers"]);
    if (!samePath(p, store.selected) || !(Array.isArray(receivers) && receivers.includes(store.selectedVia))) {
      store.selectedVia = null;
    }
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
  store.muxView = {};
  store.tab = "editor";
  store.yaml = { draft: null, applied: null, diags: null };
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
      if (confirm(`${e.message}.\n\n${t("Save them before continuing?")}`)) {
        accept(await api.save());
      } else if (!confirm(t("Continue without saving? Unsaved changes will be lost."))) {
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
  newFile: (path: string, template: string, title: string, language: string, overwrite = false) =>
    switchFile((force) => api.newFile({ path, template, title, language, force, overwrite }), t("New map created")),
  newFromExample: (name: string, path: string, overwrite = false) =>
    switchFile(async (force) => {
      try {
        return await api.fromExample({ name, path, force, overwrite });
      } catch (e) {
        if (!(e instanceof ApiError && e.code === "exists" && confirm(`${e.message}\n\n${t("Overwrite?")}`))) throw e;
        return api.fromExample({ name, path, force, overwrite: true });
      }
    }),
  saveAs: async (path: string, overwrite = false): Promise<boolean> => {
    try {
      acceptSession(await api.saveAs(path, overwrite));
      toast(t("Saved"), "info");
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.code === "exists" && confirm(`${e.message}\n\n${t("Overwrite?")}`)) {
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
  /**
   * Применить текст вкладки YAML. `live` — по ходу ввода: шаги сливаются в один шаг отмены, черновик
   * остаётся в поле как есть. Обычное применение завершает серию, и поле показывает текст сервера.
   */
  setText: (text: string, live = false) =>
    run(async () => {
      const s = await api.text(text, live);
      ownVersion = s.version;
      if (live && store.yaml.draft !== null) store.yaml.applied = text;
      else if (store.yaml.draft === text) store.yaml = { draft: null, applied: null, diags: null };
      return s;
    }),
  /** Применить черновик YAML перед уходом с вкладки или сохранением; false — в нём синтаксическая ошибка. */
  flushYaml: async (): Promise<boolean> => {
    const draft = store.yaml.draft;
    if (draft === null || store.state?.readonly) return true;
    if (draft !== store.yaml.applied) {
      const err = (await api.check(draft)).diagnostics.find((d) => d.code === "yaml");
      if (err) {
        store.tab = "yaml";
        store.revealLine = err.line;
        toast(t("YAML syntax error (line {line}): {message}", { line: err.line ?? "?", message: err.message }));
        return false;
      }
    }
    return actions.setText(draft);
  },
  setTab: async (tab: "editor" | "yaml") => {
    if (tab === store.tab) return;
    if (tab === "editor" && !(await actions.flushYaml())) return;
    store.tab = tab;
  },
  undo: () => run(api.undo),
  redo: () => run(api.redo),
  /** Перечитать файл с диска; `ask` — спросить, если есть несохранённые правки (они и история отмены теряются). */
  reload: async (ask = true) => {
    const unsaved = !!store.state?.dirty || yamlLocal.value;
    if (ask && unsaved && !confirm(t("Reload the file from disk? Unsaved changes will be lost."))) return false;
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
        if (confirm(t("The file was modified on disk by another program.\nOverwrite it with your version?"))) {
          return actions.save(true);
        }
      } else {
        toast(e instanceof Error ? e.message : String(e));
      }
    } finally {
      store.busy = false;
    }
  },
  /** via — устройство-получатель, если кадр выбран через ссылку на него в дереве. */
  select: (p: Path, via: string | null = null) => {
    store.selected = p;
    store.selectedVia = via;
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
   * Узнать у сервера, что нового (git fetch), для счётчика «не получено». Без `force` — не чаще раза в минуту;
   * ошибки не всплывают, а показываются в меню Git.
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
  /** Загрузить версию карты из git в редактор как несохранённую правку (Ctrl+Z возвращает прежний текст). */
  restoreRevision: (rev: string) =>
    run(async () => {
      const s = await api.gitRestore(rev);
      ownVersion = s.version;
      store.yaml = { draft: null, applied: null, diags: null };
      return s;
    }, t("Version {rev} is open in the editor. Save the map to keep it, or undo (Ctrl+Z).", { rev })),
  /** Операция git (коммит, тег, push, pull): обновляет состояние git, ошибки — во всплывающем сообщении. */
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
      /* хранилище недоступно */
    }
  },
};

// ------------------------------------------------------------------ производные

export const lang = computed(() => store.state?.resolved?.language ?? store.state?.data?.document?.language ?? "ru");

/** Язык документа при экспорте: шаблон ГОСТ — всегда русский, иначе выбранный или язык карты. */
export function exportLang(fmt: string): string {
  const fixed = fmt === "pdf" ? store.pdfTemplates.find((x) => x.name === store.pdfTemplate)?.lang : null;
  return fixed ?? (store.docLang || lang.value);
}

export const resolvedFrames = computed(() => {
  const m = new Map<string, ResolvedFrame>();
  for (const f of store.state?.resolved?.frames ?? []) m.set(pathKey(f.path), f);
  return m;
});

/** Данные карты вместе с подключёнными файлами (include): для дерева и просмотра их узлов. */
export const viewData = computed(() => viewOf(store.state));

/** Подключённый файл, в котором описан узел (его можно только смотреть); null — узел основного файла. */
export function includedPath(path: Path): string | null {
  return includedFile(store.state?.included, path);
}

export const tree = computed(() => (store.state?.data
  ? buildTree(viewData.value, resolvedFrames.value, lang.value, store.state.included ?? []) : []));

/** В поле YAML есть ввод, ещё не применённый на сервере. */
export const yamlLocal = computed(() => store.yaml.draft !== null && store.yaml.draft !== store.yaml.applied);

/** Сообщения проверки: для неприменённого черновика YAML — его проверка, иначе — состояния сервера. */
export const diagnostics = computed(() =>
  (yamlLocal.value && store.yaml.diags) || store.state?.diagnostics || []);

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
      // Вкладка осталась от прошлой версии mapcan, а сервер уже обновлён — подгружаем новый интерфейс
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
