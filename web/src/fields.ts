// Поля форм по типам узлов. Значения пишутся операцией set по пути узел + key.

import type { NodeKind } from "./model";

export type FieldType = "text" | "loc" | "int" | "hex" | "float" | "bool" | "select" | "date" | "intlist" | "strlist";

/** Контекст поля: протокол шины, к которой относится узел. */
export interface FieldCtx {
  protocol: string;
}

export interface FieldDef {
  key: string;            // может быть вложенным: "value.unit"
  label: string;
  type: FieldType;
  options?: Array<[string, string]>;
  hint?: string;
  wide?: boolean;
  /** Показывать поле только если условие истинно (node — данные узла). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  when?: (node: any, ctx: FieldCtx) => boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const numeric = (n: any) =>
  !n?.kind ? !n?.flags && !n?.values : ["metric", "raw"].includes(n.kind) ||
  n.factor != null || n.offset != null || n.unit != null || n.min != null || n.max != null;

const FRAME_TYPES: Array<[string, string]> = [
  ["raw", "raw — явный ID"], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
  ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
  ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
  ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
];

const KINDS: Array<[string, string]> = [
  ["", "авто"], ["enum", "enum — перечисление"], ["flag", "flag — флаг"], ["bitfield", "bitfield — битовое поле"],
  ["metric", "metric — величина"], ["raw", "raw — целое"], ["float", "float — IEEE 754 (32/64 бит)"],
  ["bytes", "bytes — байты"],
];

export const FIELDS: Record<NodeKind, FieldDef[]> = {
  document: [
    { key: "title", label: "Название", type: "loc", wide: true },
    { key: "subtitle", label: "Подзаголовок", type: "loc", wide: true },
    { key: "version", label: "Версия", type: "text" },
    { key: "date", label: "Дата", type: "date" },
    { key: "author", label: "Автор документа", type: "text" },
    { key: "language", label: "Язык документов", type: "select", options: [["ru", "русский"], ["en", "английский"]] },
  ],
  history: [],
  revision: [
    { key: "version", label: "Версия", type: "text" },
    { key: "date", label: "Дата", type: "date" },
    { key: "author", label: "Автор", type: "text" },
    { key: "github", label: "GitHub", type: "text", hint: "имя пользователя, без @" },
  ],
  bus: [
    { key: "name", label: "Имя", type: "text", hint: "идентификатор: имена файлов DBC/C" },
    { key: "title", label: "Название", type: "loc" },
    { key: "protocol", label: "Протокол", type: "select",
      options: [["canopen", "CANopen"], ["j1939", "SAE J1939"], ["can", "CAN (явные ID)"]] },
    { key: "bitrate", label: "Скорость, бит/с", type: "int" },
    { key: "interface", label: "Интерфейс", type: "text" },
    { key: "fd", label: "CAN FD", type: "bool" },
    { key: "description", label: "Описание", type: "loc", wide: true },
  ],
  device: [
    { key: "name", label: "Имя", type: "text" },
    { key: "short", label: "Обозначение", type: "text", hint: "напр. BMS" },
    { key: "title", label: "Название", type: "loc" },
    { key: "node_id", label: "node_id", type: "hex", hint: "адрес CANopen 1..127",
      when: (_n, c) => c.protocol === "canopen" },
    { key: "address", label: "Адрес (SA)", type: "hex", hint: "адрес J1939 0..253",
      when: (_n, c) => c.protocol === "j1939" },
    { key: "description", label: "Описание", type: "loc", wide: true },
  ],
  frame: [
    { key: "name", label: "Имя", type: "text" },
    { key: "title", label: "Заголовок", type: "loc", hint: "напр. СОСТОЯНИЯ" },
    { key: "type", label: "Тип", type: "select", options: FRAME_TYPES, when: (_n, c) => c.protocol === "canopen" },
    { key: "id", label: "CAN ID", type: "hex", hint: "пусто — вычислить (CANopen: тип + node_id, J1939: PGN + SA)" },
    { key: "pgn", label: "PGN", type: "hex", hint: "J1939, напр. 0xF004", when: (_n, c) => c.protocol === "j1939" },
    { key: "priority", label: "Приоритет", type: "int", hint: "0..7, по умолчанию 6", when: (_n, c) => c.protocol === "j1939" },
    { key: "destination", label: "Получатель (DA)", type: "hex", hint: "PDU1; пусто — 0xFF (всем)",
      when: (n, c) => c.protocol === "j1939" && n?.pgn != null && ((n.pgn >> 8) & 0xff) < 240 },
    { key: "receivers", label: "Получатели", type: "strlist", hint: "имена устройств через запятую", wide: true },
    { key: "dlc", label: "DLC", type: "int" },
    { key: "direction", label: "Направление", type: "select", options: [["", "по типу"], ["tx", "TX"], ["rx", "RX"]] },
    { key: "extended", label: "29-битный ID", type: "bool", when: (_n, c) => c.protocol !== "j1939" },
    { key: "description", label: "Описание", type: "loc", wide: true },
    { key: "comment", label: "Примечание", type: "loc", wide: true },
  ],
  signal: [
    { key: "name", label: "Имя", type: "text" },
    { key: "kind", label: "Тип", type: "select", options: KINDS },
    { key: "description", label: "Описание", type: "loc", wide: true },
    { key: "byte_order", label: "Порядок байт", type: "select",
      options: [["", "little-endian"], ["big_endian", "big-endian"]] },
    { key: "signed", label: "Знаковое", type: "bool" },
    { key: "factor", label: "Масштаб (factor)", type: "float", when: numeric },
    { key: "offset", label: "Смещение (offset)", type: "float", when: numeric },
    { key: "unit", label: "Единица", type: "text", when: numeric },
    { key: "min", label: "min", type: "float", when: numeric },
    { key: "max", label: "max", type: "float", when: numeric },
    { key: "multiplexer", label: "Селектор mux", type: "bool" },
    { key: "mux", label: "mux (значения селектора)", type: "intlist", hint: "напр. 0 или 1, 2" },
    { key: "initial", label: "По умолчанию", type: "float", hint: "физическое значение" },
    { key: "invalid", label: "Нет данных (raw)", type: "intlist", hint: "напр. 0xFF или 0xFE, 0xFF" },
    { key: "value_format", label: "Значения в документах", type: "select", options: [["", "десятичные"], ["hex", "hex"]],
      when: (n) => n?.values != null },
    { key: "comment", label: "Примечание", type: "loc", wide: true },
  ],
  flag: [
    { key: "name", label: "Имя", type: "text" },
    { key: "bit", label: "Бит в поле", type: "int" },
    { key: "bit_length", label: "Длина, бит", type: "int" },
    { key: "description", label: "Описание", type: "loc", wide: true },
  ],
  sdo: [
    { key: "name", label: "Имя", type: "text" },
    { key: "command", label: "Команда", type: "hex", hint: "0x2B — запись 2 байт" },
    { key: "index", label: "Индекс", type: "hex" },
    { key: "subindex", label: "Субиндекс", type: "hex" },
    { key: "description", label: "Описание", type: "loc", wide: true },
    { key: "value.name", label: "Значение: имя", type: "text" },
    { key: "value.bit_length", label: "Значение: бит", type: "select",
      options: [["8", "8"], ["16", "16"], ["24", "24"], ["32", "32"]] },
    { key: "value.unit", label: "Значение: единица", type: "text" },
    { key: "value.factor", label: "Значение: масштаб", type: "float" },
  ],
  unknown: [],
};

export class ParseError extends Error {}

/** Строка из поля ввода → значение для YAML (null — удалить ключ). */
export function parseInput(type: FieldType, raw: string): unknown {
  const s = raw.trim();
  if (s === "") return null;
  switch (type) {
    case "int": {
      const v = /^[-+]?0x/i.test(s) ? parseInt(s, 16) : Number(s);
      if (!Number.isInteger(v)) throw new ParseError(`«${raw}» — не целое число`);
      return v;
    }
    case "hex": {
      const v = /^0x/i.test(s) ? parseInt(s.slice(2), 16) : /^[0-9]+$/.test(s) ? Number(s) : NaN;
      if (!Number.isInteger(v)) throw new ParseError(`«${raw}» — ожидается число (0x1A или 26)`);
      return v;
    }
    case "float": {
      const v = Number(s.replace(",", "."));
      if (!Number.isFinite(v)) throw new ParseError(`«${raw}» — не число`);
      return v;
    }
    case "strlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean);
      return parts.length ? parts : null;
    }
    case "intlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean).map((x) => (/^0x/i.test(x) ? parseInt(x, 16) : Number(x)));
      if (parts.some((x) => !Number.isInteger(x))) throw new ParseError(`«${raw}» — список целых чисел`);
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
