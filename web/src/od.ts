// Object dictionary of a CANopen bus and its devices (CiA 301): the objects written in the map (`objects` of the bus
// and of a device), read and written by SDO. Objects of the bus are in the dictionary of each device; a device's own
// objects are in the manufacturer area, one with an index of the bus's takes its place (src/mapcan/od.py). PDO signals and SDO exchanges address objects by
// index and subindex: shown next to the object, they do not make one.

import { hex } from "./bits";
import { N_ } from "./i18n";
import { allFrameNames, displayName, frameSub, getAt, isCanopen, pathKey, uniqueName, type Data } from "./model";
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
/** An entry of a record: identifier, titles, data type and other fields (access, unit, default; `subindex` in place of
 * the next one). */
type Entry = [name: string, title: Titles, data_type: string, more?: Data];
const entriesOf = (lang: string, entries: Entry[]) =>
  entries.map(([n, tt, dt, more], i) => ({ subindex: i + 1, name: n, title: pick(lang, tt), data_type: dt, ...more }));
function record(index: number, name: string, title: Titles, entries: Entry[], extra: Data = {}): Standard {
  return {
    index, title: (lang) => pick(lang, title), make: (lang) => ({
      index, name, title: pick(lang, title), ...extra, entries: entriesOf(lang, entries),
    }),
  };
}
/** An ARRAY of `count` entries of one data type: `item` names the entry `n` (from 1). */
function array(index: number, name: string, title: Titles, data_type: string, access: string, count: number,
  item: (n: number) => [string, Titles], extra: Data = {}): Standard {
  const entries = Array.from({ length: count }, (_, i): Entry => [...item(i + 1), data_type, { access, ...extra }]);
  return {
    index, title: (lang) => pick(lang, title),
    make: (lang) => ({ index, name, title: pick(lang, title), array: true, entries: entriesOf(lang, entries) }),
  };
}

/** Objects of CiA 301 (the communication profile, one index each) and the version of the map a device was built from
 * (an object of the manufacturer area: its values come from the map). Objects of the ranges are in STANDARD_RANGES. */
export const STANDARD: Standard[] = [
  variable(0x1000, "device_type", ["Device type", "Тип устройства"], "unsigned32", "ro"),
  variable(0x1001, "error_register", ["Error register", "Регистр ошибок"], "unsigned8", "ro"),
  variable(0x1002, "manufacturer_status_register", ["Manufacturer status register", "Регистр состояния производителя"],
    "unsigned32", "ro"),
  array(0x1003, "pre_defined_error_field", ["Pre-defined error field", "Поле предопределённых ошибок"], "unsigned32",
    "ro", 8, (n) => [`standard_error_${n}`, [`Standard error field ${n}`, `Ошибка ${n}`]]),
  variable(0x1005, "cob_id_sync", ["COB-ID SYNC", "COB-ID SYNC"], "unsigned32", "rw", { default: 0x80 }),
  variable(0x1006, "communication_cycle_period", ["Communication cycle period", "Период цикла связи"], "unsigned32",
    "rw", { unit: "µs" }),
  variable(0x1007, "synchronous_window_length", ["Synchronous window length", "Длина синхронного окна"], "unsigned32",
    "rw", { unit: "µs" }),
  variable(0x1008, "device_name", ["Manufacturer device name", "Название устройства"], "visible_string", "const"),
  variable(0x1009, "hardware_version", ["Manufacturer hardware version", "Версия аппаратуры"], "visible_string", "const"),
  variable(0x100a, "software_version", ["Manufacturer software version", "Версия ПО"], "visible_string", "const"),
  variable(0x100c, "guard_time", ["Guard time", "Время охраны узла"], "unsigned16", "rw", { unit: "ms" }),
  variable(0x100d, "life_time_factor", ["Life time factor", "Коэффициент времени жизни"], "unsigned8", "rw"),
  record(0x1010, "store_parameters", ["Store parameters", "Сохранение параметров"], [
    ["save_all", ["Save all parameters", "Сохранить все параметры"], "unsigned32", { access: "rw" }],
    ["save_communication", ["Save communication parameters", "Сохранить параметры связи"], "unsigned32", { access: "rw" }],
    ["save_application", ["Save application parameters", "Сохранить параметры приложения"], "unsigned32", { access: "rw" }],
  ]),
  record(0x1011, "restore_default_parameters", ["Restore default parameters", "Восстановление параметров по умолчанию"], [
    ["restore_all", ["Restore all default parameters", "Восстановить все параметры"], "unsigned32", { access: "rw" }],
    ["restore_communication", ["Restore communication default parameters", "Восстановить параметры связи"],
      "unsigned32", { access: "rw" }],
    ["restore_application", ["Restore application default parameters", "Восстановить параметры приложения"],
      "unsigned32", { access: "rw" }],
  ]),
  variable(0x1012, "cob_id_time", ["COB-ID time stamp", "COB-ID метки времени"], "unsigned32", "rw", { default: 0x100 }),
  variable(0x1013, "high_resolution_time_stamp", ["High resolution time stamp", "Метка времени высокого разрешения"],
    "unsigned32", "rw", { unit: "µs" }),
  variable(0x1014, "cob_id_emcy", ["COB-ID EMCY", "COB-ID EMCY"], "unsigned32", "rw",
    { description: { en: "0x80 + node-ID by default", ru: "По умолчанию 0x80 + node-ID" } }),
  variable(0x1015, "inhibit_time_emcy", ["Inhibit time EMCY", "Время запрета EMCY"], "unsigned16", "rw",
    { unit: "100 µs" }),
  array(0x1016, "consumer_heartbeat_time", ["Consumer heartbeat time", "Время контроля heartbeat"], "unsigned32", "rw",
    4, (n) => [`consumer_heartbeat_time_${n}`, [`Consumer heartbeat time ${n}`, `Контроль heartbeat ${n}`]],
    { description: { en: "Bits 16..23: node-ID, bits 0..15: time in ms", ru: "Биты 16..23: node-ID, биты 0..15: время в мс" } }),
  variable(0x1017, "producer_heartbeat_time", ["Producer heartbeat time", "Период heartbeat"], "unsigned16", "rw",
    { unit: "ms" }),
  record(0x1018, "identity", ["Identity object", "Идентификация"], [
    ["vendor_id", ["Vendor-ID", "Код производителя"], "unsigned32"],
    ["product_code", ["Product code", "Код изделия"], "unsigned32"],
    ["revision_number", ["Revision number", "Номер ревизии"], "unsigned32"],
    ["serial_number", ["Serial number", "Серийный номер"], "unsigned32"],
  ]),
  variable(0x1019, "synchronous_counter_overflow_value", ["Synchronous counter overflow value",
    "Значение переполнения счётчика SYNC"], "unsigned8", "rw"),
  record(0x1020, "verify_configuration", ["Verify configuration", "Проверка конфигурации"], [
    ["configuration_date", ["Configuration date", "Дата конфигурации"], "unsigned32", { access: "rw" }],
    ["configuration_time", ["Configuration time", "Время конфигурации"], "unsigned32", { access: "rw" }],
  ]),
  variable(0x1021, "store_eds", ["Store EDS", "Хранимый EDS"], "domain", "ro"),
  variable(0x1022, "store_format", ["Store format", "Формат хранения"], "unsigned8", "ro"),
  record(0x1023, "os_command", ["OS command", "Команда ОС"], [
    ["command", ["Command", "Команда"], "octet_string", { access: "rw" }],
    ["status", ["Status", "Состояние"], "unsigned8"],
    ["reply", ["Reply", "Ответ"], "octet_string"],
  ]),
  variable(0x1024, "os_command_mode", ["OS command mode", "Режим команд ОС"], "unsigned8", "wo"),
  record(0x1025, "os_debugger_interface", ["OS debugger interface", "Интерфейс отладчика ОС"], [
    ["command", ["Command", "Команда"], "octet_string", { access: "rw" }],
    ["status", ["Status", "Состояние"], "unsigned8"],
    ["reply", ["Reply", "Ответ"], "octet_string"],
  ]),
  record(0x1026, "os_prompt", ["OS prompt", "Консоль ОС"], [
    ["stdin", ["StdIn", "Стандартный ввод"], "unsigned8", { access: "wo" }],
    ["stdout", ["StdOut", "Стандартный вывод"], "unsigned8"],
    ["stderr", ["StdErr", "Вывод ошибок"], "unsigned8"],
  ]),
  array(0x1027, "module_list", ["Module list", "Список модулей"], "unsigned16", "ro", 4,
    (n) => [`module_${n}`, [`Module ${n}`, `Модуль ${n}`]]),
  array(0x1028, "emergency_consumer", ["Emergency consumer object", "Получатель EMCY"], "unsigned32", "rw", 4,
    (n) => [`emcy_consumer_${n}`, [`Emergency consumer ${n}`, `Получатель EMCY ${n}`]]),
  record(0x1029, "error_behavior", ["Error behavior", "Реакция на ошибки"], [
    ["communication_error", ["Communication error", "Ошибка связи"], "unsigned8", { access: "rw" }],
  ]),
];

/** A range of objects of one kind (the SDO and PDO parameters, CiA 301 7.5.2): the object at `index` is the
 * (index − first + 1)-th. */
export interface StandardRange {
  first: number;
  last: number;
  make: (index: number) => Standard;
}

function range(first: number, last: number, name: string, title: Titles, entries: (n: number) => Entry[]): StandardRange {
  return {
    first, last, make: (index) => {
      const n = index - first + 1;
      const tt: Titles = [`${title[0]} ${n}`, `${title[1]} ${n}`];
      return record(index, `${name}_${n}`, tt, entries(n));
    },
  };
}

const sdoParameter = (other: Titles): Entry[] => [
  ["cob_id_client_to_server", ["COB-ID client → server", "COB-ID клиент → сервер"], "unsigned32", { access: "rw" }],
  ["cob_id_server_to_client", ["COB-ID server → client", "COB-ID сервер → клиент"], "unsigned32", { access: "rw" }],
  ["node_id", other, "unsigned8", { access: "rw" }],
];
const pdoCommunication = (tx: boolean): Entry[] => [
  ["cob_id", ["COB-ID", "COB-ID"], "unsigned32", { access: "rw" }],
  ["transmission_type", ["Transmission type", "Тип передачи"], "unsigned8", { access: "rw" }],
  ["inhibit_time", ["Inhibit time", "Время запрета"], "unsigned16", { access: "rw", unit: "100 µs" }],
  ["event_timer", tx ? ["Event timer", "Таймер события"] : ["Event timer (deadline)", "Таймер события (контроль)"],
    "unsigned16", { access: "rw", unit: "ms", subindex: 5 }],
  ...(tx ? [["sync_start_value", ["SYNC start value", "Начальное значение SYNC"], "unsigned8",
    { access: "rw", subindex: 6 }] as Entry] : []),
];
const pdoMapping = (): Entry[] => Array.from({ length: 8 }, (_, i): Entry =>
  [`mapped_object_${i + 1}`, [`Mapped object ${i + 1}`, `Отображаемый объект ${i + 1}`], "unsigned32", { access: "rw" }]);

export const STANDARD_RANGES: StandardRange[] = [
  range(0x1200, 0x127f, "sdo_server", ["SDO server parameter", "Параметры сервера SDO"],
    () => sdoParameter(["Node-ID of the SDO client", "Node-ID клиента SDO"])),
  range(0x1280, 0x12ff, "sdo_client", ["SDO client parameter", "Параметры клиента SDO"],
    () => sdoParameter(["Node-ID of the SDO server", "Node-ID сервера SDO"])),
  range(0x1400, 0x15ff, "rpdo_communication", ["RPDO communication parameter", "Параметры связи RPDO"],
    () => pdoCommunication(false)),
  range(0x1600, 0x17ff, "rpdo_mapping", ["RPDO mapping parameter", "Отображение RPDO"], pdoMapping),
  range(0x1800, 0x19ff, "tpdo_communication", ["TPDO communication parameter", "Параметры связи TPDO"],
    () => pdoCommunication(true)),
  range(0x1a00, 0x1bff, "tpdo_mapping", ["TPDO mapping parameter", "Отображение TPDO"], pdoMapping),
];

/** The standard object at `index`: one of STANDARD or of a range. */
export function standardAt(index: unknown): Standard | undefined {
  if (typeof index !== "number") return undefined;
  const r = STANDARD_RANGES.find((x) => index >= x.first && index <= x.last);
  return r ? r.make(index) : STANDARD.find((s) => s.index === index);
}

/** Standard objects to offer next to those of `taken`: the objects of STANDARD not taken, and of each range the
 * first index not taken. */
export function standardOffers(taken: Set<number>): Standard[] {
  const out = STANDARD.filter((s) => !taken.has(s.index));
  for (const r of STANDARD_RANGES) {
    for (let i = r.first; i <= r.last; i++) {
      if (!taken.has(i)) {
        out.push(r.make(i));
        break;
      }
    }
  }
  return out;
}

/** Indices unavailable to a new object: standard entries and every dictionary it can overlap. */
export function occupiedIndices(data: Data, ownerPath: Path): Set<number> {
  const bus = getAt(data, ownerPath.slice(0, 2));
  const owners = ownerPath.length === 4 ? [bus, getAt(data, ownerPath)]
    : [bus, ...(Array.isArray(bus?.devices) ? bus.devices : [])];
  const ranges = STANDARD_RANGES.flatMap((r) => Array.from({ length: r.last - r.first + 1 }, (_, i) => r.first + i));
  return new Set([...STANDARD.map((s) => s.index), ...ranges,
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
export const SDO_FUNCTIONS = ["sdo_rx", "sdo_tx"];

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

/** SDO of a device is on unless it is turned off in the device window (`sdo_enabled: false`). */
export const sdoEnabled = (device: Data): boolean => device?.sdo_enabled !== false;

/** A device has SDO frames when SDO is on and its dictionary has objects. */
export const wantsSdo = (data: Data, busPath: Path, devicePath: Path): boolean =>
  isCanopen(getAt(data, busPath)) && sdoEnabled(getAt(data, devicePath)) && dictionary(data, busPath, devicePath).length > 0;

/** New SDO frames (RX and TX) of a device: mapcan lays them out from the dictionary of the device. */
export function newSdoFrames(deviceName: string, taken: Iterable<string>, functions = SDO_FUNCTIONS): Data[] {
  const names = new Set(taken);
  return functions.map((fn) => {
    const name = uniqueName(`${deviceName}_${fn}`, names);
    names.add(name);
    return { name, canopen: fn };
  });
}

/** Edits that add the SDO frames of the bus's devices that have objects in the dictionary after `ops` and remove those
 * of the devices without objects or with SDO turned off. */
export function sdoFrameOps(data: Data, busPath: Path, ops: Op[]): Op[] {
  const after = applied(data, ops);
  const bus = getAt(after, busPath);
  if (!isCanopen(bus)) return [];
  const out: Op[] = [];
  const taken = allFrameNames(bus);
  (Array.isArray(bus?.devices) ? bus.devices : []).forEach((d: Data, di: number) => {
    const dp = [...busPath, "devices", di];
    const frames: Data[] = Array.isArray(d?.frames) ? d.frames : [];
    const present = frames.map((f, fi) => [f?.canopen, fi] as const).filter(([fn]) => SDO_FUNCTIONS.includes(fn));
    if (wantsSdo(after, busPath, dp)) {
      const missing = SDO_FUNCTIONS.filter((fn) => !present.some(([p]) => p === fn));
      for (const f of newSdoFrames(String(d?.name ?? "device"), taken, missing)) {
        taken.push(f.name);
        out.push({ op: "insert", path: [...dp, "frames"], value: f });
      }
    } else {
      for (const [, fi] of [...present].reverse()) out.push({ op: "remove", path: [...dp, "frames", fi] });
    }
  });
  return out;
}

/** The operations on a dictionary with the edits of the SDO frames they call for. */
export const withSdo = (data: Data, busPath: Path, ops: Op[]): Op[] => {
  const synced = [...ops, ...sdoSyncOps(data, busPath, ops)];
  return [...synced, ...sdoFrameOps(data, busPath, synced)];
};
