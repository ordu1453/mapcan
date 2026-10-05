import type { DiffResult, FsList, GitRevs, Meta, Op, PdfTemplate, SessionResult, State, UpdateInfo, UserProfile } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "") {
    super(message);
  }
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = r.statusText;
    let code = "";
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      code = j.code ?? "";
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(r.status, msg, code);
  }
  return (await r.json()) as T;
}

export const api = {
  meta: () => call<Meta>("GET", "/api/meta"),
  update: () => call<UpdateInfo>("GET", "/api/update"),
  setUser: (u: { name: string; github: string | null }) => call<UserProfile>("PUT", "/api/user", u),
  setLanguage: (language: string) => call<Meta>("PUT", "/api/language", { language }),
  list: (dir = "") => call<FsList>("GET", `/api/fs/list?dir=${encodeURIComponent(dir)}`),
  open: (path: string, force = false) => call<SessionResult>("POST", "/api/file/open", { path, force }),
  newFile: (b: { path: string; template: string; title: string; force?: boolean; overwrite?: boolean }) =>
    call<SessionResult>("POST", "/api/file/new", b),
  saveAs: (path: string, overwrite = false) => call<SessionResult>("POST", "/api/file/save_as", { path, overwrite }),
  close: (force = false) => call<SessionResult>("POST", "/api/file/close", { force }),
  state: () => call<State>("GET", "/api/state"),
  ops: (ops: Op[]) => call<State>("POST", "/api/ops", { ops }),
  text: (text: string) => call<State>("POST", "/api/text", { text }),
  undo: () => call<State>("POST", "/api/undo"),
  redo: () => call<State>("POST", "/api/redo"),
  save: (force = false) => call<State>("POST", "/api/save", { force }),
  reload: () => call<State>("POST", "/api/reload"),
  gitRevs: () => call<GitRevs>("GET", "/api/git/revs"),
  templates: () => call<{ pdf: PdfTemplate[]; default: string }>("GET", "/api/templates"),
  uploadLogo: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<State>("POST", "/api/logo", fd);
  },
  logoUrl: (version: number) => `/api/logo?v=${version}`,
  diffGit: (rev: string) => call<DiffResult>("POST", "/api/diff/git", { rev }),
  diffUpload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<DiffResult>("POST", "/api/diff/upload", fd);
  },
  exportUrl: (fmt: string, download = false, template?: string) => {
    const q = new URLSearchParams();
    if (download) q.set("download", "true");
    if (template) q.set("template", template);
    const s = q.toString();
    return `/api/export/${fmt}${s ? "?" + s : ""}`;
  },
  exportText: async (fmt: string) => {
    const r = await fetch(`/api/export/${fmt}`);
    if (!r.ok) {
      const j = await r.json().catch(() => ({ detail: r.statusText }));
      throw new ApiError(r.status, j.detail);
    }
    return r.text();
  },
};

export type WsMessage =
  | { type: "hello" | "state"; version: number; session_id: number; app?: string }
  | { type: "session"; session_id: number }
  | { type: "file-changed" }
  | { type: "open-request"; path: string };

/** WebSocket с автоматическим переподключением. */
export function connectEvents(onMessage: (m: WsMessage) => void, onStatus: (online: boolean) => void): void {
  let delay = 500;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      delay = 500;
      onStatus(true);
    };
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onclose = () => {
      onStatus(false);
      setTimeout(open, delay);
      delay = Math.min(delay * 2, 8000);
    };
  };
  open();
}
