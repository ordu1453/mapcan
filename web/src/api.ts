import type { DiffResult, GitRevs, Op, State } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
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
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* тело не JSON */
    }
    throw new ApiError(r.status, msg);
  }
  return (await r.json()) as T;
}

export const api = {
  state: () => call<State>("GET", "/api/state"),
  ops: (ops: Op[]) => call<State>("POST", "/api/ops", { ops }),
  text: (text: string) => call<State>("POST", "/api/text", { text }),
  undo: () => call<State>("POST", "/api/undo"),
  redo: () => call<State>("POST", "/api/redo"),
  save: (force = false) => call<State>("POST", "/api/save", { force }),
  reload: () => call<State>("POST", "/api/reload"),
  gitRevs: () => call<GitRevs>("GET", "/api/git/revs"),
  diffGit: (rev: string) => call<DiffResult>("POST", "/api/diff/git", { rev }),
  diffUpload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return call<DiffResult>("POST", "/api/diff/upload", fd);
  },
  exportUrl: (fmt: string, download = false) => `/api/export/${fmt}${download ? "?download=true" : ""}`,
  exportText: async (fmt: string) => {
    const r = await fetch(`/api/export/${fmt}`);
    if (!r.ok) {
      const j = await r.json().catch(() => ({ detail: r.statusText }));
      throw new ApiError(r.status, j.detail);
    }
    return r.text();
  },
};

export type WsMessage = { type: "hello" | "state"; version: number } | { type: "file-changed" };

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
