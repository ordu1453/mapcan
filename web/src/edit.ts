// Структурные правки: добавить / удалить / дублировать / переместить узел.

import { actions, resolvedFrames, store, toast } from "./store";
import { allFrameNames, freeByte, getAt, HISTORY_PATH, nodeKind, pathKey, uniqueName, type Data, type NodeKind } from "./model";
import type { Op, Path } from "./types";
import { t } from "./i18n";

const data = (): Data => store.state?.data;

export interface ChildAction {
  label: string;
  run: () => Promise<boolean>;
}

function busOf(path: Path): Data {
  return getAt(data(), path.slice(0, 2));
}

async function insertAndSelect(listPath: Path, value: unknown, extra: Op[] = [], select = true): Promise<boolean> {
  const list = getAt(data(), listPath) as unknown[] | undefined;
  const index = list ? list.length : 0;
  const ok = await actions.apply([{ op: "insert", path: listPath, value }, ...extra.map((o) => fixIndex(o, index))]);
  if (ok && select) actions.select([...listPath, index]);
  return ok;
}

function fixIndex(o: Op, index: number): Op {
  return { ...o, path: o.path.map((x) => (x === "$new" ? index : x)) } as Op;
}

export function addBus(): Promise<boolean> {
  const names = (data()?.buses ?? []).map((b: Data) => b.name);
  const name = uniqueName("bus", names);
  return insertAndSelect(["buses"], { name, title: name, protocol: "can", devices: [] });
}

export function addDevice(busPath: Path): Promise<boolean> {
  const bus = getAt(data(), busPath);
  const devices: Data[] = bus.devices ?? [];
  const value: Record<string, unknown> = { name: uniqueName("device", devices.map((d) => d.name)) };
  if (bus.protocol === "j1939") {
    const used = new Set(devices.map((d) => d.address));
    let a = 0x10;
    while (used.has(a)) a++;
    value.address = a;
  } else if (bus.protocol !== "can") {
    const used = new Set(devices.map((d) => d.node_id));
    let id = 1;
    while (used.has(id)) id++;
    value.node_id = id;
  }
  value.frames = [];
  return insertAndSelect([...busPath, "devices"], value);
}

/** Новый кадр не выделяется: остаёмся на шине/устройстве, кадр появляется в списке «Кадры». */
export function addFrame(ownerPath: Path): Promise<boolean> {
  const owner = getAt(data(), ownerPath);
  const bus = busOf(ownerPath);
  const isDevice = ownerPath.length === 4;
  const base = isDevice ? `${owner.name}_frame` : "frame";
  const value: Record<string, unknown> = { name: uniqueName(base, allFrameNames(bus)) };
  if (bus.protocol === "j1939") {
    const used = new Set<number>();
    for (const f of [...(bus.frames ?? []), ...(bus.devices ?? []).flatMap((d: Data) => d.frames ?? [])]) {
      if (f.pgn != null) used.add(f.pgn);
    }
    let pgn = 0xff00;                                   // проприетарный диапазон PDU2
    while (used.has(pgn) && pgn < 0xffff) pgn++;
    value.pgn = pgn;
    value.priority = 6;
    value.dlc = 8;
    value.cycle_ms = 100;
    value.signals = [];
    return insertAndSelect([...ownerPath, "frames"], value, [], false);
  }
  if (bus.protocol === "canopen" && isDevice) {
    const usedTypes = new Set((owner.frames ?? []).map((f: Data) => f.type));
    value.type = ["pdo_tx1", "pdo_tx2", "pdo_tx3", "pdo_tx4", "pdo_rx1", "pdo_rx2", "pdo_rx3", "pdo_rx4"]
      .find((t) => !usedTypes.has(t)) ?? "raw";
  }
  if (!value.type || value.type === "raw") {
    const used = new Set<number>();
    for (const f of store.state?.resolved?.frames ?? []) if (f.can_id != null) used.add(f.can_id);
    let id = 0x100;
    while (used.has(id)) id++;
    value.id = id;
  }
  value.dlc = 8;
  value.cycle_ms = 100;
  value.signals = [];
  return insertAndSelect([...ownerPath, "frames"], value, [], false);
}

export function addSignal(framePath: Path, layout?: { start_bit: number; bit_length: number }, name?: string): Promise<boolean> {
  const frame = getAt(data(), framePath);
  const names = new Set<string>();
  for (const s of frame.signals ?? []) {
    names.add(s.name);
    for (const f of s.flags ?? []) names.add(f.name);
  }
  const value = { name: uniqueName(name || "signal", names) };
  const extra: Op[] = [];
  let pos = layout;
  if (!pos) {
    const placed = placeNewSignal(framePath);
    if (!placed) {
      toast(t("В кадре нет свободных бит: освободите место или увеличьте DLC"));
      return Promise.resolve(false);
    }
    pos = placed.pos;
    if (placed.dlc != null) extra.push({ op: "set", path: [...framePath, "dlc"], value: placed.dlc });
  }
  return insertAndSelect([...framePath, "signals"], value, [
    ...extra,
    { op: "set_layout", path: [...framePath, "signals", "$new"], ...pos },
  ]);
}

const FD_DLC = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64];

/** Место для нового сигнала: свободный байт; если его нет — расширить DLC на байт
 *  (для CAN FD — до следующего допустимого значения); если и это нельзя — свободные биты. */
function placeNewSignal(framePath: Path): { pos: { start_bit: number; bit_length: number }; dlc?: number } | null {
  const frame = getAt(data(), framePath);
  const rf = resolvedFrames.value.get(pathKey(framePath));
  const dlc: number = rf?.dlc ?? frame.dlc ?? 8;
  const used = new Set<number>((rf?.signals ?? []).flatMap((s) => s.occupied));
  const byte = freeByte(rf, dlc);
  if (byte !== null) return { pos: { start_bit: byte * 8, bit_length: 8 } };

  const fd = !!busOf(framePath)?.fd;
  const next = fd ? FD_DLC.find((d) => d > dlc) : dlc < 8 ? dlc + 1 : undefined;
  if (next !== undefined) return { pos: { start_bit: dlc * 8, bit_length: 8 }, dlc: next };

  // Кадр максимальной длины: берём первый свободный участок (не длиннее байта)
  for (let b = 0; b < dlc * 8; b++) {
    if (used.has(b)) continue;
    let n = 1;
    while (n < 8 && b + n < dlc * 8 && !used.has(b + n) && (b + n) % 8 !== 0) n++;
    return { pos: { start_bit: b, bit_length: n } };
  }
  return null;
}

export function addFlag(signalPath: Path): Promise<boolean> {
  const sig = getAt(data(), signalPath);
  const flags: Data[] = sig.flags ?? [];
  const used = new Set<number>();
  for (const f of flags) for (let b = f.bit; b < f.bit + (f.bit_length ?? 1); b++) used.add(b);
  let bit = 0;
  while (used.has(bit)) bit++;
  const frameSigs = getAt(data(), signalPath.slice(0, -2)) as Data[];
  const names = new Set<string>(frameSigs.flatMap((s: Data) => [s.name, ...(s.flags ?? []).map((f: Data) => f.name)]));
  return insertAndSelect([...signalPath, "flags"], { bit, name: uniqueName("flag", names) });
}

export function addSdo(framePath: Path): Promise<boolean> {
  const frame = getAt(data(), framePath);
  const list: Data[] = frame.sdo ?? [];
  const last = list[list.length - 1];
  return insertAndSelect([...framePath, "sdo"], {
    name: uniqueName("exchange", list.map((e) => e.name)),
    command: last?.command ?? 0x2b,
    index: last?.index ?? 0x2000,
    subindex: (last?.subindex ?? 0) + 1,
  });
}

function bumpVersion(v: string): string {
  const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v ?? "");
  return m ? `${m[1]}.${m[2]}.${Number(m[3]) + 1}` : v || "0.1.0";
}

/** Новая запись истории — первой (история идёт от новых версий к старым). */
export async function addRevision(): Promise<boolean> {
  const doc = data()?.document ?? {};
  const latest = (doc.history ?? [])[0]?.version;
  const entry: Record<string, unknown> = {
    version: latest && latest === doc.version ? bumpVersion(latest) : doc.version ?? "0.1.0",
    date: new Date().toISOString().slice(0, 10),
  };
  const user = store.meta?.user;
  if (user?.name) entry.author = user.name;
  if (user?.github) entry.github = user.github;
  entry.changes = [];
  const ok = await actions.apply([{ op: "insert", path: HISTORY_PATH, index: 0, value: entry }]);
  if (ok) actions.select([...HISTORY_PATH, 0]);
  return ok;
}

/** Действия «добавить» для узла дерева. */
export function childActions(path: Path): ChildAction[] {
  const kind: NodeKind = nodeKind(path);
  const node = getAt(data(), path);
  switch (kind) {
    case "document":
      return [{ label: t("Шина"), run: addBus }];
    case "history":
      return [{ label: t("Запись"), run: addRevision }];
    case "bus":
      return [{ label: t("Устройство"), run: () => addDevice(path) }, { label: t("Кадр"), run: () => addFrame(path) }];
    case "device":
      return [{ label: t("Кадр"), run: () => addFrame(path) }];
    case "frame":
      return node?.sdo || ["sdo_tx", "sdo_rx"].includes(node?.type)
        ? [{ label: t("SDO-обмен"), run: () => addSdo(path) }, { label: t("Сигнал"), run: () => addSignal(path) }]
        : [{ label: t("Сигнал"), run: () => addSignal(path) }];
    case "signal":
      return node?.flags || node?.kind === "bitfield" ? [{ label: t("Флаг"), run: () => addFlag(path) }] : [];
    default:
      return [];
  }
}

export function canRemove(path: Path): boolean {
  return !["document", "history"].includes(nodeKind(path));
}

/** Удаление без подтверждения — отменяется через Ctrl+Z. */
export async function removeNode(path: Path): Promise<boolean> {
  const revision = nodeKind(path) === "revision";
  const ok = await actions.apply([{ op: "remove", path }]);
  // Переходим к родителю (сигнал → кадр, кадр → устройство/шина…), а не к соседнему элементу
  if (ok) actions.select(revision ? HISTORY_PATH : path.length > 2 ? path.slice(0, -2) : ["document"]);
  return ok;
}

/** Delete — удалить выбранный узел дерева (вне полей ввода и диалогов). */
export function installDeleteShortcut(): void {
  window.addEventListener("keydown", (e) => {
    if (e.key !== "Delete" || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    const t = e.target as HTMLElement;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (document.querySelector(".modal-backdrop") || !store.state?.data || store.state.readonly || store.busy) return;
    if (store.tab !== "editor") return;
    const path = store.selected;
    if (path.length < 2 || typeof path[path.length - 1] !== "number") return;
    e.preventDefault();
    void removeNode(path);
  });
}

export async function duplicateNode(path: Path): Promise<boolean> {
  const node = getAt(data(), path);
  const listPath = path.slice(0, -1);
  const list = getAt(data(), listPath) as Data[];
  const copy = JSON.parse(JSON.stringify(node));
  const index = Number(path[path.length - 1]) + 1;
  if (nodeKind(path) === "revision") {
    const ok = await actions.apply([{ op: "insert", path: listPath, value: copy, index }]);
    if (ok) actions.select([...listPath, index]);
    return ok;
  }
  const names = new Set<string>(list.map((x) => x.name));
  if (nodeKind(path) === "frame") allFrameNames(busOf(path)).forEach((n) => names.add(n));
  copy.name = uniqueName(`${node.name}_copy`, names);
  if (nodeKind(path) === "device" && copy.node_id != null) delete copy.node_id;
  if (nodeKind(path) === "frame" && copy.id != null) delete copy.id;
  const ok = await actions.apply([{ op: "insert", path: listPath, value: copy, index }]);
  if (ok) actions.select([...listPath, index]);
  return ok;
}

export async function moveNode(path: Path, delta: number): Promise<boolean> {
  const list = getAt(data(), path.slice(0, -1)) as unknown[];
  const i = Number(path[path.length - 1]);
  const to = i + delta;
  if (!Array.isArray(list) || to < 0 || to >= list.length) return false;
  const ok = await actions.apply([{ op: "move", path, to }]);
  if (ok) actions.select([...path.slice(0, -1), to]);
  return ok;
}
