// Object dictionary of a CANopen bus and its devices (CiA 301): the objects written in the map (`objects` of the bus
// and of a device), read and written by SDO. Objects of the bus are in the dictionary of each device; a device's own
// objects are in the manufacturer area, one with an index of the bus's takes its place (src/mapcan/od.py). PDO signals and SDO exchanges address objects by
// index and subindex: shown next to the object, they do not make one.

import { hex } from "./bits";
import { N_ } from "./i18n";
import { displayName, frameSub, getAt, pathKey, type Data } from "./model";
import { parseInteger } from "@mapcan/forms";
import type { Op, Path, ResolvedFrame } from "./types";

/** Index areas of the dictionary (CiA 301, 7.4.1); the data type area holds no objects of a device. */
export interface Area { first: number; last: number; title: string }
export const AREAS: Area[] = [
  { first: 0x0000, last: 0x0fff, title: N_("Data types") },
  { first: 0x1000, last: 0x1fff, title: N_("Communication profile") },
  { first: 0x2000, last: 0x5fff, title: N_("Manufacturer area") },
  { first: 0x6000, last: 0x9fff, title: N_("Standardized device profiles") },
  { first: 0xa000, last: 0xffff, title: N_("Interface profiles and reserved") },
];
/** The area of the objects of a device: the others are the bus's (objects every device has). */
export const DEVICE_AREA = AREAS[2];
export const areaOf = (index: number): Area => AREAS.find((a) => index >= a.first && index <= a.last) ?? AREAS[0];

/** Basic data types: name in the map, code (an index of the data type area), length in bits (0: any). */
export const DATA_TYPES: [name: string, code: number, bits: number][] = [
  ["boolean", 0x01, 1], ["integer8", 0x02, 8], ["integer16", 0x03, 16], ["integer32", 0x04, 32],
  ["unsigned8", 0x05, 8], ["unsigned16", 0x06, 16], ["unsigned32", 0x07, 32], ["real32", 0x08, 32],
  ["visible_string", 0x09, 0], ["octet_string", 0x0a, 0], ["unicode_string", 0x0b, 0], ["time_of_day", 0x0c, 48],
  ["time_difference", 0x0d, 48], ["domain", 0x0f, 0], ["integer24", 0x10, 24], ["real64", 0x11, 64],
  ["integer40", 0x12, 40], ["integer48", 0x13, 48], ["integer56", 0x14, 56], ["integer64", 0x15, 64],
  ["unsigned24", 0x16, 24], ["unsigned40", 0x18, 40], ["unsigned48", 0x19, 48], ["unsigned56", 0x1a, 56],
  ["unsigned64", 0x1b, 64],
];
export const STRING_TYPES = new Set(["visible_string", "octet_string", "unicode_string", "domain"]);
export const ACCESS = ["ro", "wo", "rw", "const"];
export const SOURCES = ["map_version.major", "map_version.minor", "map_version.patch", "layout_crc32"];

/** var, array or record. */
export const kindOf = (o: Data): "var" | "array" | "record" =>
  (Array.isArray(o?.entries) && o.entries.length ? (o.array ? "array" : "record") : "var");

/**
 * Edits that give the object at `path` the type `v`: a data type makes it a variable, "record" or "array" an object of
 * entries. A variable becomes an object of one entry of its type, an object of entries a variable of the type of its
 * first entry.
 */
export function objectTypeOps(path: Path, o: Data, v: string): Op[] {
  const kind = kindOf(o);
  if (v === "record" || v === "array") {
    const ops: Op[] = kind === "var"
      ? [{ op: "set", path: [...path, "entries"], value: [{ subindex: 1, name: "value", data_type: o?.data_type ?? "unsigned8" }] },
        ...["data_type", "default", "source", "unit"].map((k): Op => ({ op: "set", path: [...path, k], value: null }))]
      : [];
    return [...ops, { op: "set", path: [...path, "array"], value: v === "array" ? true : null }];
  }
  const ops: Op[] = [{ op: "set", path: [...path, "data_type"], value: v || (kind === "var" ? null : o.entries[0]?.data_type ?? "unsigned8") }];
  if (kind !== "var") ops.push({ op: "set", path: [...path, "entries"], value: null }, { op: "set", path: [...path, "array"], value: null });
  return ops;
}

/** The value typed for a variable or an entry: a number unless its data type is a string. */
export function objectValue(raw: unknown, dataType: unknown): unknown {
  if (typeof raw !== "string" || STRING_TYPES.has(String(dataType))) return raw;
  try {
    return parseInteger(raw);
  } catch {
    const v = Number(raw.replace(",", "."));
    return Number.isFinite(v) ? v : raw;
  }
}

/** An object of a dictionary as the page shows it: of the bus (`inherited` on a device's page) or the device's own. */
export interface DictRow {
  index: number;
  obj: Data;
  path: Path;
  inherited: boolean;
  /** The device's own object takes the place of the bus's one with this index. */
  overrides: boolean;
  excluded?: boolean;
}

const objects = (owner: Data): Data[] => (Array.isArray(owner?.objects) ? owner.objects : []);

/** Dictionary of the bus at `busPath`, or of its device at `devicePath`: by index, the device's own in place of the
 * bus's. Objects without a numeric index come last. */
export function dictionary(data: Data, busPath: Path, devicePath: Path | null = null, includeExcluded = false): DictRow[] {
  const rows = new Map<number, DictRow>();
  const loose: DictRow[] = [];
  const bus = getAt(data, busPath);
  const device = devicePath ? getAt(data, devicePath) : null;
  const add = (owner: Path, inherited: boolean) => objects(getAt(data, owner)).forEach((o, i) => {
    if (!inherited && rows.get(o?.index)?.obj?.locked) return;
    const excluded = !!device && !(inherited && o?.locked)
      && (device?.objects_enabled === false || device?.excluded_objects?.includes(o?.index));
    if (excluded && !includeExcluded) return;
    const row: DictRow = { index: o?.index, obj: o, path: [...owner, "objects", i], inherited, overrides: false, excluded };
    if (typeof o?.index !== "number") loose.push(row);
    else rows.set(o.index, { ...row, overrides: !inherited && rows.has(o.index) });
  });
  if (bus?.objects_enabled !== false) add(busPath, devicePath !== null);
  if (devicePath && device?.objects_enabled !== false) add(devicePath, false);
  return [...[...rows.values()].sort((a, b) => a.index - b.index), ...loose];
}

/** A PDO signal or an SDO exchange that addresses an object. */
export interface OdUse {
  via: "pdo" | "sdo";
  path: Path;
  label: string;
  framePath: Path;
  frameLabel: string;
  canId: string;
}

export const useKey = (index: number, subindex: number): string => `${index}:${subindex}`;

/** What addresses the objects of a device's dictionary, by "index:subindex": signals of its PDOs with an index and
 * its SDO exchanges. */
export function uses(device: Data, devicePath: Path, frames: Map<string, ResolvedFrame>, lang: string): Map<string, OdUse[]> {
  const out = new Map<string, OdUse[]>();
  const put = (index: unknown, subindex: unknown, u: OdUse) => {
    if (typeof index !== "number") return;
    const k = useKey(index, typeof subindex === "number" ? subindex : 0);
    out.set(k, [...(out.get(k) ?? []), u]);
  };
  (Array.isArray(device?.frames) ? device.frames : []).forEach((f: Data, fi: number) => {
    const fp = [...devicePath, "frames", fi];
    const frame = { framePath: fp, frameLabel: displayName(f, lang), canId: frameSub(frames.get(pathKey(fp))) };
    if (typeof f?.canopen === "string" && f.canopen.startsWith("pdo_")) {
      (Array.isArray(f.signals) ? f.signals : []).forEach((s: Data, si: number) => put(s?.index, s?.subindex,
        { via: "pdo", path: [...fp, "signals", si], label: displayName(s, lang), ...frame }));
    }
    (Array.isArray(f?.sdo) ? f.sdo : []).forEach((e: Data, ei: number) => put(e?.index, e?.subindex,
      { via: "sdo", path: [...fp, "sdo", ei], label: String(e?.name ?? "—"), ...frame }));
  });
  return out;
}

/** A standard object to add: its title and the YAML of the object, in the document language. */
export interface Standard {
  index: number;
  title: (lang: string) => string;
  make: (lang: string) => Data;
}

type Titles = [en: string, ru: string];
const pick = (lang: string, [en, ru]: Titles) => (lang === "ru" ? ru : en);
function variable(index: number, name: string, title: Titles, data_type: string, access: string, extra: Data = {}): Standard {
  return { index, title: (lang) => pick(lang, title),
    make: (lang) => ({ index, name, title: pick(lang, title), data_type, access, ...extra }) };
}
function record(index: number, name: string, title: Titles, entries: [string, Titles, string, Data?][], extra: Data = {}): Standard {
  return {
    index, title: (lang) => pick(lang, title), make: (lang) => ({
      index, name, title: pick(lang, title), ...extra,
      entries: entries.map(([n, tt, dt, more], i) => ({ subindex: i + 1, name: n, title: pick(lang, tt), data_type: dt, ...more })),
    }),
  };
}

/** Objects of CiA 301 a master usually reads by SDO, and the version of the map a device was built from (an object of
 * the manufacturer area: its values come from the map). */
export const STANDARD: Standard[] = [
  variable(0x1000, "device_type", ["Device type", "Тип устройства"], "unsigned32", "ro"),
  variable(0x1001, "error_register", ["Error register", "Регистр ошибок"], "unsigned8", "ro"),
  variable(0x1005, "cob_id_sync", ["COB-ID SYNC", "COB-ID SYNC"], "unsigned32", "rw", { default: 0x80 }),
  variable(0x1006, "communication_cycle_period", ["Communication cycle period", "Период цикла связи"], "unsigned32",
    "rw", { unit: "µs" }),
  variable(0x1008, "device_name", ["Manufacturer device name", "Название устройства"], "visible_string", "const"),
  variable(0x1009, "hardware_version", ["Manufacturer hardware version", "Версия аппаратуры"], "visible_string", "const"),
  variable(0x100a, "software_version", ["Manufacturer software version", "Версия ПО"], "visible_string", "const"),
  variable(0x1017, "producer_heartbeat_time", ["Producer heartbeat time", "Период heartbeat"], "unsigned16", "rw",
    { unit: "ms" }),
  record(0x1018, "identity", ["Identity object", "Идентификация"], [
    ["vendor_id", ["Vendor-ID", "Код производителя"], "unsigned32"],
    ["product_code", ["Product code", "Код изделия"], "unsigned32"],
    ["revision_number", ["Revision number", "Номер ревизии"], "unsigned32"],
    ["serial_number", ["Serial number", "Серийный номер"], "unsigned32"],
  ]),

];

/** Indices unavailable to a new object: standard entries and every dictionary it can overlap. */
export function occupiedIndices(data: Data, ownerPath: Path): Set<number> {
  const bus = getAt(data, ownerPath.slice(0, 2));
  const owners = ownerPath.length === 4 ? [bus, getAt(data, ownerPath)]
    : [bus, ...(Array.isArray(bus?.devices) ? bus.devices : [])];
  return new Set([...STANDARD.map((s) => s.index),
    ...owners.flatMap(objects).map((o) => o?.index).filter((i) => typeof i === "number")]);
}

/** The first index of the area not taken in `taken`. */
export function freeIndex(area: Area, taken: Set<number>): number | null {
  for (let i = Math.max(area.first, 0x1000); i <= Math.min(area.last, 0xbfff); i++) if (!taken.has(i)) return i;
  return null;
}

export const indexLabel = (index: number): string => hex(index, 4);

// ------------------------------------------------------------------ SDO frames

/** The signal of an SDO frame in bytes 1..3: the object (index and subindex), an enum of the dictionary's objects. */
export const SDO_OBJECT = "sdo_object";
const SDO_FUNCTIONS = ["sdo_rx", "sdo_tx"];

/** Raw value of bytes 1..3 of an SDO frame: the index (little-endian) and the subindex. */
export const sdoObjectKey = (index: number, subindex: number) => index | (subindex << 16);
const keyText = (k: number) => hex(k, 6);

/** Values of the object of an SDO frame by the dictionary: a variable at subindex 0 by its name, an entry of an array
 * or a record as OBJECT_ENTRY. */
export function sdoObjectValues(rows: DictRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) {
    if (typeof r.index !== "number" || typeof r.obj?.name !== "string") continue;
    const entries: Data[] = Array.isArray(r.obj.entries) ? r.obj.entries : [];
    if (kindOf(r.obj) === "var") out[keyText(sdoObjectKey(r.index, 0))] = r.obj.name.toUpperCase();
    for (const e of entries) {
      if (typeof e?.subindex === "number" && typeof e?.name === "string") {
        out[keyText(sdoObjectKey(r.index, e.subindex))] = `${r.obj.name}_${e.name}`.toUpperCase();
      }
    }
  }
  return out;
}

export const SDO_COMMANDS: Record<string, Record<string, string>> = {
  sdo_rx: { "0x23": "WRITE_4_BYTES", "0x27": "WRITE_3_BYTES", "0x2B": "WRITE_2_BYTES", "0x2F": "WRITE_1_BYTE", "0x40": "READ" },
  sdo_tx: { "0x43": "READ_4_BYTES", "0x47": "READ_3_BYTES", "0x4B": "READ_2_BYTES", "0x4F": "READ_1_BYTE", "0x60": "WRITE_OK",
    "0x80": "ABORT" },
};

/** Signals of a new SDO frame of a device, as of any frame: the command (byte 0), the object (bytes 1..3, an enum of
 * the device's dictionary) and the data (bytes 4..7). */
export function sdoSignals(data: Data, framePath: Path, fn: string): Data[] {
  const dev = framePath[2] === "devices" ? framePath.slice(0, 4) : null;
  return [
    { name: "sdo_command", description: { ru: "Команда SDO", en: "SDO command specifier" }, byte: 0, byte_length: 1,
      encoding: "enum", value_format: "hex", values: SDO_COMMANDS[fn] ?? SDO_COMMANDS.sdo_rx },
    { name: SDO_OBJECT, description: { ru: "Объект словаря: индекс (байты 1–2) и субиндекс (байт 3)",
      en: "Dictionary object: index (bytes 1–2) and subindex (byte 3)" }, byte: 1, byte_length: 3, encoding: "enum",
      value_format: "hex", values: sdoObjectValues(dictionary(data, framePath.slice(0, 2), dev)) },
    { name: "sdo_data", description: { ru: "Данные", en: "Data" }, byte: 4, byte_length: 4, encoding: "number" },
  ];
}

/** The data with the operations applied (set, insert, remove), on a copy: what the dictionary will be. */
function applied(data: Data, ops: Op[]): Data {
  const out = JSON.parse(JSON.stringify(data ?? {}));
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  for (const o of ops as any[]) {
    const p: Path = o.path;
    if (!Array.isArray(p) || !p.length) continue;
    const parent = getAt(out, p.slice(0, -1));
    const last = p[p.length - 1];
    if (o.op === "set") {
      if (parent && typeof parent === "object") {
        if (o.value === null && !Array.isArray(parent)) delete parent[last];
        else parent[last] = o.value;
      }
    } else if (o.op === "remove") {
      if (Array.isArray(parent)) parent.splice(Number(last), 1);
      else if (parent && typeof parent === "object") delete parent[last];
    } else if (o.op === "insert") {
      let list = getAt(out, p);
      if (!Array.isArray(list)) {
        if (!parent || typeof parent !== "object") continue;
        list = parent[last] = [];
      }
      list.splice(typeof o.index === "number" ? o.index : list.length, 0, o.value);
    }
  }
  return out;
}

/** Edits that bring the object of every SDO frame of the bus's devices in line with their dictionaries after `ops`:
 * values of the objects of the dictionary are added, renamed and removed; other values (of indices the dictionary
 * has neither before nor after) stay. */
export function sdoSyncOps(data: Data, busPath: Path, ops: Op[]): Op[] {
  const after = applied(data, ops);
  const bus = getAt(after, busPath);
  const out: Op[] = [];
  (Array.isArray(bus?.devices) ? bus.devices : []).forEach((d: Data, di: number) => {
    const dp = [...busPath, "devices", di];
    const was = dictionary(data, busPath, dp);
    const now = dictionary(after, busPath, dp);
    const managed = new Set([...was, ...now].map((r) => r.index));
    const wanted = sdoObjectValues(now);
    (Array.isArray(d?.frames) ? d.frames : []).forEach((f: Data, fi: number) => {
      if (!SDO_FUNCTIONS.includes(f?.canopen) || !Array.isArray(f?.signals)) return;
      const si = f.signals.findIndex((s: Data) => s?.name === SDO_OBJECT);
      if (si < 0) return;
      const table = f.signals[si]?.values;
      // The values by number (JSON gives the keys as strings); a value with a description keeps it when renamed
      const old = new Map<number, unknown>(table && typeof table === "object"
        ? Object.entries(table).filter(([k]) => Number.isFinite(Number(k))).map(([k, v]) => [Number(k), v]) : []);
      const next = new Map([...old].filter(([k]) => !managed.has(k & 0xffff)));
      for (const [k, name] of Object.entries(wanted)) {
        const v = old.get(Number(k));
        next.set(Number(k), v && typeof v === "object" ? { ...v, name } : name);
      }
      const text = (m: Map<number, unknown>) => JSON.stringify([...m].sort(([a], [b]) => a - b));
      if (text(old) === text(next)) return;
      out.push({ op: "set", path: [...dp, "frames", fi, "signals", si, "values"],
        value: Object.fromEntries([...next].sort(([a], [b]) => a - b).map(([k, v]) => [keyText(k), v])) });
    });
  });
  return out;
}

/** The operations on a dictionary with the edits of the SDO frames they call for. */
export const withSdo = (data: Data, busPath: Path, ops: Op[]): Op[] => [...ops, ...sdoSyncOps(data, busPath, ops)];
