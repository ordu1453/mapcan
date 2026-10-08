// Поля форм по типам узлов. Значения пишутся операцией set по пути узел + key.

import { HELP } from "./help";
import { N_, t } from "./i18n";
import type { NodeKind } from "./model";

export type FieldType = "text" | "loc" | "int" | "hex" | "float" | "bool" | "select" | "date" | "intlist" | "strlist"
  /** Набор устройств шины: переключатели из options. */
  | "devices";

/**
 * Контекст поля: протокол шины узла; для сигнала — его вычисленный тип, длина и наличие селектора mux в кадре;
 * для кадра — устройства шины, владелец кадра (null у кадров шины), вычисленные направление и отправитель.
 */
export interface FieldCtx {
  protocol: string;
  encoding?: string;
  bitLength?: number;
  hasSelector?: boolean;
  devices?: string[];
  /** Подписи устройств шины для людей (сокращение или полное название) по идентификатору. */
  deviceLabels?: Record<string, string>;
  owner?: string | null;
  direction?: string | null;
  /** Вычисленное направление кадра, когда поле direction не задано (иначе null). */
  defaultDirection?: string | null;
  sender?: string | null;
  /** The bus is CAN FD. */
  fd?: boolean;
  /** BRS of the frames as set on the bus (null: not set, on). */
  busBrs?: boolean | null;
}

export interface FieldDef {
  key: string;            // может быть вложенным: "value.unit"
  label: string;
  type: FieldType;
  options?: Array<[string, string]>;
  /** Варианты, зависящие от контекста (протокола шины); NodeEditor подставляет их в options. */
  optionsFor?: (ctx: FieldCtx) => Array<[string, string]>;
  hint?: string;
  /** Справка «?» к полю (заполняется из HELP). */
  help?: string;
  wide?: boolean;
  /** Показывать поле только если условие истинно (node — данные узла). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  when?: (node: any, ctx: FieldCtx) => boolean;
  /** Обязательное поле: без значения карта не проходит проверку (звёздочка и подсветка пустого поля). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  required?: boolean | ((node: any, ctx: FieldCtx) => boolean);
  /** Подсказки при вводе (свой текст тоже допускается): units — справочник единиц с сервера. */
  suggest?: "units";
}

// Поля сигнала, применимые к его типу (заполненные поля показываются всегда — см. NodeEditor)
const encodingIn = (...encodings: string[]) => (_n: unknown, c: FieldCtx) => encodings.includes(c.encoding ?? "");
const numeric = encodingIn("scaled", "raw", "float");

/** Устройству нужен адрес, если ID какого-то его кадра вычисляется из адреса (кадр без явного id). */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const needsAddress = (dev: any, computed: (f: any) => boolean): boolean =>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (dev?.frames ?? []).some((f: any) => f?.id == null && computed(f));

const FRAME_TYPES: Array<[string, string]> = [
  ["raw", N_("raw — explicit ID")], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
  ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
  ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
  ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
];

// Вне CANopen тип кадра не используется: ID задаётся явно (CAN) или из PGN + SA (J1939)
const frameTypes = (c: FieldCtx) => (c.protocol === "canopen" ? FRAME_TYPES : FRAME_TYPES.slice(0, 1));

// Направление по типу кадра CANopen (как в canopen.py); у SYNC и TIME своего направления нет
const TYPE_DIRECTION: Record<string, string> = {
  nmt: "rx", emcy: "tx", sdo_tx: "tx", sdo_rx: "rx", heartbeat: "tx",
  pdo_tx1: "tx", pdo_tx2: "tx", pdo_tx3: "tx", pdo_tx4: "tx", pdo_rx1: "rx", pdo_rx2: "rx", pdo_rx3: "rx", pdo_rx4: "rx",
};
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const frameType = (n: any): string => n?.type ?? "raw";

/** Допустимые DLC служебных кадров CANopen по CiA 301 (как в canopen.py); без dlc берётся наименьший. */
export const CANOPEN_DLC: Record<string, number[]> = {
  nmt: [2], sync: [0, 1], time: [6], heartbeat: [1], sdo_tx: [8], sdo_rx: [8],
};

// Пустое направление: вычисленное из типа кадра CANopen или из sender — показывается в скобках
const directions = (c: FieldCtx): Array<[string, string]> => {
  const base = t(c.protocol === "canopen" ? N_("by type") : N_("by default"));
  const d = c.defaultDirection;
  return [["", d ? `${base} (${d.toUpperCase()})` : base], ["tx", "TX"], ["rx", "RX"]];
};

// Отправитель и получатели — устройства шины, кроме владельца кадра (он отправитель TX-кадра и получатель RX-кадра);
// получателем не предлагается и отправитель кадра
const others = (c: FieldCtx): Array<[string, string]> =>
  (c.devices ?? []).filter((d) => d !== c.owner).map((d) => [d, c.deviceLabels?.[d] ?? d]);
// BRS: empty means the default (the bus value for a frame, on for a bus), shown in brackets
const brsLabel = (on: boolean) => t(on ? N_("on") : N_("off"));
const brsOptions = (base: string, on: boolean): Array<[string, string]> =>
  [["", `${t(base)} (${brsLabel(on)})`], ["true", N_("on")], ["false", N_("off")]];

const senders = (c: FieldCtx): Array<[string, string]> => [["", N_("outside the map")], ...others(c)];
const receivers = (c: FieldCtx): Array<[string, string]> => others(c).filter(([d]) => d !== c.sender);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const hasValue = (n: any): boolean => n?.value != null;

const SDO_ENCODINGS: Array<[string, string]> = [
  ["enum", N_("enum — enumeration")], ["scaled", N_("scaled — scaled value")], ["raw", N_("raw — integer")],
];

const ENCODINGS: Array<[string, string]> = [
  ["enum", N_("enum — enumeration")], ["flag", N_("flag — single flag")], ["bitfield", N_("bitfield — bit field")],
  ["scaled", N_("scaled — scaled value")], ["raw", N_("raw — integer")], ["float", N_("float — IEEE 754 (32/64 bit)")],
  ["bytes", N_("bytes — raw bytes")],
];

export const FIELDS: Record<NodeKind, FieldDef[]> = {
  document: [
    { key: "title", label: N_("Title"), type: "loc", wide: true, required: true },
    { key: "subtitle", label: N_("Subtitle"), type: "loc", wide: true },
    { key: "version", label: N_("Version"), type: "text" },
    { key: "date", label: N_("Date"), type: "date" },
    { key: "author", label: N_("Document author"), type: "text" },
    { key: "language", label: N_("Document language"), type: "select", options: [["ru", N_("Russian")], ["en", N_("English")]] },
  ],
  history: [],
  revision: [
    { key: "version", label: N_("Version"), type: "text", required: true },
    { key: "date", label: N_("Date"), type: "date" },
    { key: "author", label: N_("Author"), type: "text" },
    { key: "github", label: "GitHub", type: "text", hint: N_("username, without @") },
  ],
  bus: [
    { key: "name", label: N_("Identifier"), type: "text", required: true, hint: N_("Latin letters, digits and _; used in DBC/C file names") },
    { key: "title", label: N_("Title"), type: "loc", required: true, hint: N_("e.g. Bus 1") },
    { key: "protocol", label: N_("Protocol"), type: "select",
      options: [["canopen", "CANopen"], ["j1939", "SAE J1939"], ["can", N_("CAN (explicit IDs)")]] },
    { key: "bitrate", label: N_("Bitrate, bit/s"), type: "int" },
    { key: "interface", label: N_("Interface"), type: "text" },
    { key: "fd", label: "CAN FD", type: "bool" },
    { key: "brs", label: N_("Bit rate switch (BRS)"), type: "select",
      optionsFor: () => brsOptions(N_("by default"), true), when: (n) => !!n?.fd },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
  ],
  device: [
    { key: "name", label: N_("Identifier"), type: "text", required: true, hint: N_("Latin letters, digits and _; used in C code, frame senders and receivers") },
    { key: "title", label: N_("Full name"), type: "loc", required: true, hint: N_("shown in the map tree and document headings") },
    { key: "short", label: N_("Abbreviation"), type: "text", hint: N_("e.g. BMS; shown before the full name in the tree") },
    { key: "node_id", label: N_("Node address (node_id)"), type: "hex", hint: N_("CANopen address 1..127"),
      when: (_n, c) => c.protocol === "canopen",
      required: (n, c) => c.protocol === "canopen" && needsAddress(n, (f) => (f.type ?? "raw") !== "raw") },
    { key: "address", label: N_("Address (SA)"), type: "hex", hint: N_("J1939 address 0..253"),
      when: (_n, c) => c.protocol === "j1939",
      required: (n, c) => c.protocol === "j1939" && needsAddress(n, () => true) },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
  ],
  frame: [
    { key: "name", label: N_("Identifier"), type: "text", required: true },
    { key: "title", label: N_("Title"), type: "loc", hint: N_("e.g. Status; if empty, the tree shows the identifier") },
    // Вне CANopen тип не используется (ID явный или из PGN); записанный в YAML тип виден, чтобы его исправить
    { key: "type", label: N_("Type"), type: "select", optionsFor: frameTypes, when: (_n, c) => c.protocol === "canopen" },
    { key: "id", label: "CAN ID", type: "hex", hint: N_("leave empty to compute (CANopen: type + node_id, J1939: PGN + SA)"),
      required: (n, c) => c.protocol === "can" || (c.protocol === "canopen" && (n?.type ?? "raw") === "raw") },
    { key: "pgn", label: "PGN", type: "hex", hint: N_("J1939, e.g. 0xF004"), when: (_n, c) => c.protocol === "j1939",
      required: (n, c) => c.protocol === "j1939" && n?.id == null },
    { key: "priority", label: N_("Priority"), type: "int", hint: N_("0..7, default 6"), when: (_n, c) => c.protocol === "j1939" },
    { key: "destination", label: N_("Destination (DA)"), type: "hex", hint: N_("PDU1; leave empty for 0xFF (global)"),
      when: (n, c) => c.protocol === "j1939" && n?.pgn != null && ((n.pgn >> 8) & 0xff) < 240 },
    // Длину служебного кадра CANopen задаёт его тип; у SYNC — 0 или 1
    { key: "dlc", label: "DLC", type: "int",
      required: (n, c) => !(c.protocol === "canopen" && CANOPEN_DLC[frameType(n)]),
      when: (n, c) => !(c.protocol === "canopen" && CANOPEN_DLC[frameType(n)]?.length === 1) },
    // Направление есть только у кадра устройства; у типа CANopen оно задано типом
    { key: "direction", label: N_("Direction"), type: "select", optionsFor: directions,
      when: (n, c) => !!c.owner && !(c.protocol === "canopen" && TYPE_DIRECTION[frameType(n)]) },
    // Отправитель — у RX-кадра и кадра шины (TX-кадр передаёт само устройство), если на шине есть кого выбрать
    { key: "sender", label: N_("Sender"), type: "select", optionsFor: senders,
      hint: N_("empty — the sender is not in the map"),
      when: (_n, c) => (!c.owner || c.direction === "rx") && others(c).length > 0 },
    // У RX-кадра получатель — само устройство
    { key: "receivers", label: N_("Receivers"), type: "devices", optionsFor: receivers, wide: true,
      hint: N_("bus devices that receive the frame"),
      when: (_n, c) => !(c.owner && c.direction === "rx") && receivers(c).length > 0 },
    // CANopen вычисляет 11-битные ID; 29-битный бывает только у кадра с явным ID
    { key: "extended", label: N_("29-bit ID"), type: "bool",
      when: (n, c) => c.protocol === "can" || (c.protocol === "canopen" && frameType(n) === "raw") },
    { key: "brs", label: N_("Bit rate switch (BRS)"), type: "select",
      optionsFor: (c) => brsOptions(N_("as on the bus"), c.busBrs ?? true), when: (_n, c) => !!c.fd },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
    { key: "comment", label: N_("Note"), type: "loc", wide: true },
  ],
  signal: [
    { key: "name", label: N_("Identifier"), type: "text", required: true },
    { key: "title", label: N_("Title"), type: "loc", hint: N_("e.g. Battery voltage; if empty, the tree shows the identifier") },
    { key: "encoding", label: N_("Encoding"), type: "select", options: ENCODINGS },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
    // Порядок байт важен для значения длиннее байта; формат допускает big-endian в любом протоколе
    // (CANopen-сигнал big-endian — в examples/minimal.yaml)
    { key: "byte_order", label: N_("Byte order"), type: "select",
      options: [["", "little-endian"], ["big_endian", "big-endian"]],
      when: (_n, c) => (c.bitLength ?? 0) > 8 && c.encoding !== "bytes" },
    { key: "signed", label: N_("Signed"), type: "bool", when: encodingIn("raw", "scaled") },
    { key: "signed_code", label: N_("Sign encoding"), type: "select",
      options: [["", N_("two's complement")], ["ones_complement", N_("ones' complement")], ["sign_magnitude", N_("sign-magnitude")]],
      when: (n) => !!n?.signed || n?.signed_code != null },
    { key: "factor", label: N_("Factor (scale)"), type: "float", when: numeric },
    { key: "offset", label: N_("Offset"), type: "float", when: numeric },
    { key: "unit", label: N_("Unit"), type: "text", suggest: "units", when: numeric },
    { key: "min", label: N_("Minimum (min)"), type: "float", when: numeric },
    { key: "max", label: N_("Maximum (max)"), type: "float", when: numeric },
    { key: "multiplexer", label: N_("mux selector"), type: "bool",
      when: (_n, c) => ["raw", "enum"].includes(c.encoding ?? "") && !c.hasSelector },
    { key: "mux", label: N_("mux (selector values)"), type: "intlist", hint: N_("e.g. 0 or 1, 2"),
      when: (_n, c) => !!c.hasSelector },
    { key: "initial", label: N_("Initial value"), type: "float", hint: N_("physical value"),
      when: (_n, c) => !["bitfield", "bytes"].includes(c.encoding ?? "") },
    { key: "invalid", label: N_("Invalid (raw)"), type: "intlist", hint: N_("e.g. 0xFF or 0xFE, 0xFF"),
      when: encodingIn("raw", "scaled", "enum") },
    { key: "index", label: N_("Dictionary object: index"), type: "hex", hint: N_("e.g. 0x6041; CANopen object in the PDO"),
      when: (_n, c) => c.protocol === "canopen" },
    { key: "subindex", label: N_("Dictionary object: subindex"), type: "hex", when: (_n, c) => c.protocol === "canopen" },
    { key: "spn", label: "SPN", type: "int", hint: N_("J1939 parameter number"),
      when: (_n, c) => c.protocol === "j1939" },
    { key: "value_format", label: N_("Value format in documents"), type: "select", options: [["", N_("decimal")], ["hex", "hex"]],
      when: (n) => n?.values != null },
    { key: "comment", label: N_("Note"), type: "loc", wide: true },
  ],
  flag: [
    { key: "name", label: N_("Identifier"), type: "text", required: true },
    { key: "bit", label: N_("Bit in field"), type: "int", required: true },
    { key: "bit_length", label: N_("Length, bits"), type: "int" },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
  ],
  sdo: [
    { key: "name", label: N_("Identifier"), type: "text", required: true },
    { key: "command", label: N_("Command"), type: "hex", hint: N_("0x2B — write 2 bytes"), required: true },
    { key: "index", label: N_("Index"), type: "hex", required: true },
    { key: "subindex", label: N_("Subindex"), type: "hex" },
    { key: "description", label: N_("Description"), type: "loc", wide: true },
    // Остальные поля значения появляются, когда задан его идентификатор
    { key: "value.name", label: N_("Value: identifier"), type: "text", required: hasValue },
    { key: "value.encoding", label: N_("Value: encoding"), type: "select", options: SDO_ENCODINGS, when: hasValue },
    { key: "value.bit_length", label: N_("Value: bit length"), type: "select",
      options: [["8", "8"], ["16", "16"], ["24", "24"], ["32", "32"]], when: hasValue },
    { key: "value.unit", label: N_("Value: unit"), type: "text", suggest: "units", when: hasValue },
    { key: "value.factor", label: N_("Value: factor"), type: "float", when: hasValue },
  ],
  unknown: [],
};

for (const [kind, defs] of Object.entries(FIELDS)) {
  for (const d of defs) d.help ??= HELP[`${kind}.${d.key}`];
}

export class ParseError extends Error {}

/** Строка из поля ввода → значение для YAML (null — удалить ключ). */
// Целое: десятичное или 0x…; «1.5», «1e3» и числа за пределами точности JS не принимаются
const INT_RE = /^[-+]?(0x[0-9a-f]+|[0-9]+)$/i;

/** Разобрать целое число; ParseError, если строка — не целое или слишком большое число. */
export function parseInteger(raw: string): number {
  const s = raw.trim();
  const m = INT_RE.exec(s);
  const v = m ? (/0x/i.test(s) ? (s.startsWith("-") ? -1 : 1) * parseInt(m[1].slice(2), 16) : Number(s.replace(/^\+/, ""))) : NaN;
  if (!Number.isSafeInteger(v)) throw new ParseError(t("“{raw}” is not an integer", { raw }));
  return v;
}

export function parseInput(type: FieldType, raw: string): unknown {
  const s = raw.trim();
  if (s === "") return null;
  switch (type) {
    case "int": {
      return parseInteger(s);
    }
    case "hex": {
      // Строго, как целое: «0x12 34» или «0x1G» — ошибка, а не 0x12 или 1 (ID не должен меняться молча)
      const v = /^(0x[0-9a-f]+|[0-9]+)$/i.test(s) ? parseInteger(s) : NaN;
      if (!Number.isSafeInteger(v)) throw new ParseError(t("“{raw}”: expected a number, such as 0x1A or 26", { raw }));
      return v;
    }
    case "float": {
      const v = Number(s.replace(",", "."));
      if (!Number.isFinite(v)) throw new ParseError(t("“{raw}” is not a number", { raw }));
      return v;
    }
    case "strlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean);
      return parts.length ? parts : null;
    }
    case "intlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean).map((x) => (INT_RE.test(x) ? Number(x.replace(/^\+/, "")) : NaN));
      if (parts.some((x) => !Number.isSafeInteger(x))) throw new ParseError(t("“{raw}”: expected a list of integers", { raw }));
      return parts.length === 1 ? parts[0] : parts;
    }
    default:
      return s;
  }
}

export function formatValue(type: FieldType, v: unknown): string {
  if (v === null || v === undefined) return "";
  if (type === "hex" && typeof v === "number") return "0x" + v.toString(16).toUpperCase().padStart(2, "0");
  if ((type === "intlist" || type === "strlist") && Array.isArray(v)) return v.join(", ");
  return String(v);
}
