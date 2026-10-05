// Навигация по plain-дереву карты, дерево для боковой панели, шаблоны новых узлов.

import { hex, rangeLabel } from "./bits";
import type { Diagnostic, Level, Path, ResolvedFrame, ResolvedSignal } from "./types";

export type NodeKind = "document" | "history" | "revision" | "bus" | "device" | "frame" | "signal" | "flag" | "sdo" | "unknown";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Data = any;

export const pathKey = (p: Path): string => p.join("/");

/** Путь узла «История изменений»: показывается в дереве, даже если записей ещё нет. */
export const HISTORY_PATH: Path = ["document", "history"];

export function samePath(a: Path, b: Path): boolean {
  return a.length === b.length && a.every((x, i) => String(x) === String(b[i]));
}

export function startsWith(p: Path, prefix: Path): boolean {
  return prefix.length <= p.length && prefix.every((x, i) => String(x) === String(p[i]));
}

export function getAt(data: Data, path: Path): Data {
  let node = data;
  for (const el of path) {
    if (node === null || node === undefined) return undefined;
    node = node[el as any];
  }
  return node;
}

/** Тип узла по форме пути. */
export function nodeKind(path: Path): NodeKind {
  const n = path.length;
  if (n === 0 || (n === 1 && path[0] === "document")) return "document";
  if (path[0] === "document" && path[1] === "history") {
    if (n === 2) return "history";
    if (n === 3 && typeof path[2] === "number") return "revision";
    return "unknown";
  }
  if (n === 2 && path[0] === "buses") return "bus";
  if (n === 4 && path[2] === "devices") return "device";
  const tail = path[n - 2];
  if (tail === "frames") return "frame";
  if (tail === "signals") return "signal";
  if (tail === "flags") return "flag";
  if (tail === "sdo") return "sdo";
  return "unknown";
}

/** Ближайший узел дерева, к которому относится путь диагностики. */
export function ownerPath(path: Path): Path {
  for (let n = path.length; n > 0; n--) {
    const p = path.slice(0, n);
    const k = nodeKind(p);
    if (k !== "unknown" && !(k === "document" && n > 1)) return p;
  }
  return ["document"];
}

export function framePathOf(path: Path): Path | null {
  for (let n = path.length; n >= 2; n--) {
    if (path[n - 2] === "frames") return path.slice(0, n);
  }
  return null;
}

// ------------------------------------------------------------------ текст

export function txt(v: unknown, lang = "ru"): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    const o = v as Record<string, string>;
    return o[lang] ?? Object.values(o).find((x) => x) ?? "";
  }
  return String(v);
}

// ------------------------------------------------------------------ дерево

export interface TreeNode {
  key: string;
  path: Path;
  kind: NodeKind;
  label: string;
  sub: string;
  children: TreeNode[];
  search: string;
  dir?: string | null;   // для кадров: tx / rx / null (широковещательный)
}

function frameSub(rf: ResolvedFrame | undefined): string {
  return rf ? hex(rf.can_id, rf.extended ? 8 : 3) : "";
}

function signalSub(rs: ResolvedSignal | undefined): string {
  if (!rs) return "";
  const lo = Math.min(...rs.occupied);
  const hi = Math.max(...rs.occupied);
  return rangeLabel(lo, hi);
}

export function buildTree(data: Data, frames: Map<string, ResolvedFrame>, lang: string): TreeNode[] {
  const doc: TreeNode = {
    key: "document", path: ["document"], kind: "document", label: txt(data?.document?.title, lang) || "Документ",
    sub: data?.document?.version ?? "", children: [], search: "",
  };
  const history: Data[] = data?.document?.history ?? [];
  doc.children.push({
    key: pathKey(HISTORY_PATH), path: HISTORY_PATH, kind: "history", label: "История изменений",
    sub: history.length ? String(history.length) : "", search: "история изменений history",
    children: history.map((h: Data, i: number) => ({
      key: pathKey([...HISTORY_PATH, i]), path: [...HISTORY_PATH, i], kind: "revision" as NodeKind,
      label: String(h?.version ?? "—"), sub: h?.date ? String(h.date) : "", children: [],
      search: [h?.version, h?.author, h?.github, ...(h?.changes ?? []).map((c: unknown) => txt(c, lang))]
        .filter(Boolean).join(" ").toLowerCase(),
    })),
  });
  const out: TreeNode[] = [doc];
  (data?.buses ?? []).forEach((bus: Data, bi: number) => {
    const bp: Path = ["buses", bi];
    const bnode: TreeNode = {
      key: pathKey(bp), path: bp, kind: "bus", label: txt(bus.title, lang) || bus.name, sub: bus.name,
      children: [], search: `${bus.name} ${txt(bus.title, lang)}`.toLowerCase(),
    };
    const frameNode = (f: Data, fp: Path): TreeNode => {
      const rf = frames.get(pathKey(fp));
      const fnode: TreeNode = {
        key: pathKey(fp), path: fp, kind: "frame", label: f.name,
        sub: f.pgn != null ? `PGN ${hex(f.pgn, 4)}` : frameSub(rf), children: [],
        dir: rf?.device ? rf.direction : null,
        search: [f.name, txt(f.title, lang), txt(f.description, lang), rf?.can_id != null ? hex(rf.can_id) : "",
          rf?.can_id != null ? String(rf.can_id) : "", f.pgn != null ? hex(f.pgn, 4) : ""].join(" ").toLowerCase(),
      };
      (f.signals ?? []).forEach((s: Data, si: number) => {
        const sp = [...fp, "signals", si];
        const rs = rf?.signals.find((x) => x.index === si);
        const snode: TreeNode = {
          key: pathKey(sp), path: sp, kind: "signal", label: s.name, sub: signalSub(rs), children: [],
          search: [s.name, txt(s.description, lang)].join(" ").toLowerCase(),
        };
        (s.flags ?? []).forEach((fl: Data, fi: number) => {
          const flp = [...sp, "flags", fi];
          snode.children.push({
            key: pathKey(flp), path: flp, kind: "flag", label: fl.name,
            sub: `бит ${fl.bit}`, children: [], search: [fl.name, txt(fl.description, lang)].join(" ").toLowerCase(),
          });
        });
        fnode.children.push(snode);
      });
      (f.sdo ?? []).forEach((e: Data, ei: number) => {
        const ep = [...fp, "sdo", ei];
        fnode.children.push({
          key: pathKey(ep), path: ep, kind: "sdo", label: e.name,
          sub: `${hex(e.index, 4)}:${e.subindex ?? 0}`, children: [],
          search: [e.name, txt(e.description, lang)].join(" ").toLowerCase(),
        });
      });
      return fnode;
    };
    (bus.frames ?? []).forEach((f: Data, fi: number) => bnode.children.push(frameNode(f, [...bp, "frames", fi])));
    (bus.devices ?? []).forEach((d: Data, di: number) => {
      const dp: Path = [...bp, "devices", di];
      const dnode: TreeNode = {
        key: pathKey(dp), path: dp, kind: "device", label: d.short ? `${d.short} · ${d.name}` : d.name,
        sub: d.node_id != null ? hex(d.node_id, 2) : d.address != null ? `SA ${hex(d.address, 2)}` : "", children: [],
        search: [d.name, d.short ?? "", txt(d.title, lang)].join(" ").toLowerCase(),
      };
      (d.frames ?? []).forEach((f: Data, fi: number) => dnode.children.push(frameNode(f, [...dp, "frames", fi])));
      bnode.children.push(dnode);
    });
    out.push(bnode);
  });
  return out;
}

// ------------------------------------------------------------------ диагностика по узлам

export function diagIndex(diags: Diagnostic[]): Map<string, Diagnostic[]> {
  const m = new Map<string, Diagnostic[]>();
  for (const d of diags) {
    const k = pathKey(ownerPath(d.node.length ? d.node : ["document"]));
    if (!m.has(k)) m.set(k, []);
    m.get(k)!.push(d);
  }
  return m;
}

const RANK: Record<Level, number> = { error: 0, warning: 1, info: 2 };

export function worst(ds: Diagnostic[] | undefined): Level | null {
  if (!ds || !ds.length) return null;
  return ds.reduce((a, d) => (RANK[d.level] < RANK[a] ? d.level : a), "info" as Level);
}

// ------------------------------------------------------------------ новые узлы

export function uniqueName(base: string, taken: Iterable<string>): string {
  const set = new Set(taken);
  if (!set.has(base)) return base;
  for (let i = 2; ; i++) if (!set.has(`${base}_${i}`)) return `${base}_${i}`;
}

export function allFrameNames(bus: Data): string[] {
  const names: string[] = (bus.frames ?? []).map((f: Data) => f.name);
  for (const d of bus.devices ?? []) for (const f of d.frames ?? []) names.push(f.name);
  return names;
}

/** Первый свободный байт кадра (для нового сигнала). */
/** Первый полностью свободный байт кадра или null, если такого нет. */
export function freeByte(rf: ResolvedFrame | undefined, dlc: number): number | null {
  const used = new Set<number>();
  for (const s of rf?.signals ?? []) for (const b of s.occupied) used.add(Math.floor(b / 8));
  for (let b = 0; b < dlc; b++) if (!used.has(b)) return b;
  return null;
}

export function nextFreeKey(values: Record<string, unknown> | undefined): number {
  const keys = Object.keys(values ?? {}).map(Number).filter((x) => !Number.isNaN(x));
  return keys.length ? Math.max(...keys) + 1 : 0;
}
