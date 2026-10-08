// Navigation in the plain tree of the map, the tree for the side bar, templates of new nodes.

import { hex, rangeLabel } from "./bits";
import type { Diagnostic, Included, Level, Path, ResolvedFrame, ResolvedSignal } from "./types";
import { t } from "./i18n";

export type NodeKind = "document" | "history" | "revision" | "bus" | "device" | "frame" | "signal" | "flag" | "sdo" | "unknown";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Data = any;

export const pathKey = (p: Path): string => p.join("/");

/** Path of the Revision history node: shown in the tree even if there are no entries yet. */
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

/** Kind of a node by the shape of its path. */
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

/** The nearest tree node a diagnostic's path belongs to. */
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

// ------------------------------------------------------------------ text

export function txt(v: unknown, lang = "ru"): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "string") return v;
  if (typeof v === "object") {
    const o = v as Record<string, string>;
    return o[lang] ?? Object.values(o).find((x) => x) ?? "";
  }
  return String(v);
}

// ------------------------------------------------------------------ tree

export interface TreeNode {
  key: string;
  path: Path;
  kind: NodeKind;
  label: string;
  sub: string;
  children: TreeNode[];
  search: string;
  dir?: string | null;   // for frames: tx / rx / null (broadcast)
  /** A link to a frame of another device that the device receives (path is the original's path); the value is the sender. */
  from?: string;
  /** For a link, the name of the receiving device it is under. */
  receiver?: string;
  /** The node is described in an included file (include): its path relative to the map. */
  file?: string;
  /** The node is added by an included file as a whole (its descendants have file too). */
  fileRoot?: boolean;
}

/** Included file the node is described in; null for a node of the main file. */
export function includedFile(included: Included[] | undefined, path: Path): string | null {
  for (const r of included ?? []) if (startsWith(path, r.path)) return r.file;
  return null;
}

/** Data of the map together with the included files, for the tree and for viewing their nodes. */
export function viewOf(s: { data: Data; included_buses?: Data[] | null } | null | undefined): Data {
  if (!s?.data) return null;
  return s.included_buses ? { ...s.data, buses: s.included_buses } : s.data;
}

function markIncluded(nodes: TreeNode[], included: Included[]): void {
  for (const n of nodes) {
    const file = n.from === undefined ? includedFile(included, n.path) : null;
    if (file) {
      n.file = file;
      n.fileRoot = included.some((r) => samePath(r.path, n.path));
    }
    markIncluded(n.children, included);
  }
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

// The data may not pass the schema (the YAML draft is applied while typing): an empty item "- " is null,
// a number instead of a list. The tree is built from what there is; an item without a name shows as "—".
const list = (v: unknown): Data[] => (Array.isArray(v) ? v.map(obj) : []);
const obj = (v: unknown): Data => (v && typeof v === "object" && !Array.isArray(v) ? v : {});
const nameOf = (v: Data): string => (v.name == null ? "—" : String(v.name));

/**
 * Label of a node in the tree: the title for people, the identifier only if there is no title.
 * A device has its abbreviation before the full name, if it is set.
 */
export function displayName(v: Data, lang: string): string {
  const title = txt(v?.title, lang) || nameOf(obj(v));
  return v?.short ? `${v.short} · ${title}` : title;
}

/** Short label of a device in references to it (sender, receivers): the abbreviation, else the full name. */
export function deviceLabel(v: Data, lang: string): string {
  return v?.short ? String(v.short) : txt(v?.title, lang) || nameOf(obj(v));
}

export function buildTree(data: Data, frames: Map<string, ResolvedFrame>, lang: string, included: Included[] = []): TreeNode[] {
  const doc: TreeNode = {
    key: "document", path: ["document"], kind: "document", label: txt(data?.document?.title, lang) || t("Document"),
    sub: data?.document?.version ?? "", children: [], search: "",
  };
  const history = list(data?.document?.history);
  doc.children.push({
    key: pathKey(HISTORY_PATH), path: HISTORY_PATH, kind: "history", label: t("Revision history"),
    sub: history.length ? String(history.length) : "", search: `${t("Revision history").toLowerCase()} история изменений history`,
    children: history.map((h: Data, i: number) => ({
      key: pathKey([...HISTORY_PATH, i]), path: [...HISTORY_PATH, i], kind: "revision" as NodeKind,
      label: String(h?.version ?? "—"), sub: h?.date ? String(h.date) : "", children: [],
      search: [h?.version, h?.author, h?.github, ...(Array.isArray(h?.changes) ? h.changes : []).map((c: unknown) => txt(c, lang))]
        .filter(Boolean).join(" ").toLowerCase(),
    })),
  });
  const out: TreeNode[] = [doc];
  list(data?.buses).forEach((bus: Data, bi: number) => {
    const bp: Path = ["buses", bi];
    const bnode: TreeNode = {
      key: pathKey(bp), path: bp, kind: "bus", label: displayName(bus, lang), sub: "",
      children: [], search: `${bus.name} ${txt(bus.title, lang)}`.toLowerCase(),
    };
    const frameNode = (f: Data, fp: Path): TreeNode => {
      const rf = frames.get(pathKey(fp));
      const fnode: TreeNode = {
        key: pathKey(fp), path: fp, kind: "frame", label: displayName(f, lang),
        sub: f.pgn != null ? `PGN ${hex(f.pgn, 4)}` : frameSub(rf), children: [],
        dir: rf?.device ? rf.direction : null,
        search: [f.name, txt(f.title, lang), txt(f.description, lang), rf?.can_id != null ? hex(rf.can_id) : "",
          rf?.can_id != null ? String(rf.can_id) : "", f.pgn != null ? hex(f.pgn, 4) : ""].join(" ").toLowerCase(),
      };
      list(f.signals).forEach((s: Data, si: number) => {
        const sp = [...fp, "signals", si];
        const rs = rf?.signals.find((x) => x.index === si);
        const snode: TreeNode = {
          key: pathKey(sp), path: sp, kind: "signal", label: displayName(s, lang), sub: signalSub(rs), children: [],
          search: [s.name, txt(s.title, lang), txt(s.description, lang)].join(" ").toLowerCase(),
        };
        list(s.flags).forEach((fl: Data, fi: number) => {
          const flp = [...sp, "flags", fi];
          snode.children.push({
            key: pathKey(flp), path: flp, kind: "flag", label: nameOf(fl),
            sub: t("bit {bit}", { bit: fl.bit }), children: [], search: [fl.name, txt(fl.description, lang)].join(" ").toLowerCase(),
          });
        });
        fnode.children.push(snode);
      });
      list(f.sdo).forEach((e: Data, ei: number) => {
        const ep = [...fp, "sdo", ei];
        fnode.children.push({
          key: pathKey(ep), path: ep, kind: "sdo", label: nameOf(e),
          sub: `${hex(e.index, 4)}:${e.subindex ?? 0}`, children: [],
          search: [e.name, txt(e.description, lang)].join(" ").toLowerCase(),
        });
      });
      return fnode;
    };
    list(bus.frames).forEach((f: Data, fi: number) => bnode.children.push(frameNode(f, [...bp, "frames", fi])));
    list(bus.devices).forEach((d: Data, di: number) => {
      const dp: Path = [...bp, "devices", di];
      const dnode: TreeNode = {
        key: pathKey(dp), path: dp, kind: "device", label: displayName(d, lang),
        sub: d.node_id != null ? hex(d.node_id, 2) : d.address != null ? `SA ${hex(d.address, 2)}` : "", children: [],
        search: [d.name, d.short ?? "", txt(d.title, lang)].join(" ").toLowerCase(),
      };
      list(d.frames).forEach((f: Data, fi: number) => dnode.children.push(frameNode(f, [...dp, "frames", fi])));
      // Frames of others that list the device among their receivers: links after its own frames
      for (const rf of frames.values()) {
        if (rf.path[1] !== bi || rf.device === d.name || !rf.receivers.includes(d.name)) continue;
        // The frame's title may not tell whose it is: the link's label names the sender
        const sender = list(bus.devices).find((x: Data) => x.name === rf.sender);
        const senderLabel = sender ? deviceLabel(sender, lang) : "";
        const frame = obj(getAt(data, rf.path));
        dnode.children.push({
          key: `${pathKey(dp)}/received:${pathKey(rf.path)}`, path: rf.path, kind: "frame",
          label: senderLabel ? `${senderLabel} · ${displayName(frame, lang)}` : displayName(frame, lang),
          sub: frameSub(rf), children: [], dir: "rx", from: senderLabel || rf.sender || "", receiver: d.name,
          search: [rf.name, txt(frame.title, lang), rf.sender ?? "", sender?.short ?? "", txt(sender?.title, lang),
            rf.can_id != null ? hex(rf.can_id) : ""].join(" ").toLowerCase(),
        });
      }
      bnode.children.push(dnode);
    });
    out.push(bnode);
  });
  if (included.length) markIncluded(out, included);
  return out;
}

// ------------------------------------------------------------------ diagnostics by node

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

// ------------------------------------------------------------------ new nodes

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

/** First free byte of the frame (for a new signal). */
/** First entirely free byte of the frame, or null if there is none. */
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
