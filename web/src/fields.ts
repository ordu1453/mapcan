// Поля форм по типам узлов. Значения пишутся операцией set по пути узел + key.

import { N_, t } from "./i18n";
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
  ["raw", N_("raw — явный ID")], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
  ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
  ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
  ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
];

const KINDS: Array<[string, string]> = [
  ["", N_("авто")], ["enum", N_("enum — перечисление")], ["flag", N_("flag — флаг")], ["bitfield", N_("bitfield — битовое поле")],
  ["metric", N_("metric — величина")], ["raw", N_("raw — целое")], ["float", N_("float — IEEE 754 (32/64 бит)")],
  ["bytes", N_("bytes — байты")],
];

export const FIELDS: Record<NodeKind, FieldDef[]> = {
  document: [
    { key: "title", label: N_("Название"), type: "loc", wide: true },
    { key: "subtitle", label: N_("Подзаголовок"), type: "loc", wide: true },
    { key: "version", label: N_("Версия"), type: "text" },
    { key: "date", label: N_("Дата"), type: "date" },
    { key: "author", label: N_("Автор документа"), type: "text" },
    { key: "language", label: N_("Язык документов"), type: "select", options: [["ru", N_("русский")], ["en", N_("английский")]] },
  ],
  history: [],
  revision: [
    { key: "version", label: N_("Версия"), type: "text" },
    { key: "date", label: N_("Дата"), type: "date" },
    { key: "author", label: N_("Автор"), type: "text" },
    { key: "github", label: "GitHub", type: "text", hint: N_("имя пользователя, без @") },
  ],
  bus: [
    { key: "name", label: N_("Имя"), type: "text", hint: N_("идентификатор: имена файлов DBC/C") },
    { key: "title", label: N_("Название"), type: "loc" },
    { key: "protocol", label: N_("Протокол"), type: "select",
      options: [["canopen", "CANopen"], ["j1939", "SAE J1939"], ["can", N_("CAN (явные ID)")]] },
    { key: "bitrate", label: N_("Скорость, бит/с"), type: "int" },
    { key: "interface", label: N_("Интерфейс"), type: "text" },
    { key: "fd", label: "CAN FD", type: "bool" },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
  ],
  device: [
    { key: "name", label: N_("Имя"), type: "text" },
    { key: "short", label: N_("Обозначение"), type: "text", hint: N_("напр. BMS") },
    { key: "title", label: N_("Название"), type: "loc" },
    { key: "node_id", label: N_("Адрес узла (node_id)"), type: "hex", hint: N_("адрес CANopen 1..127"),
      when: (_n, c) => c.protocol === "canopen" },
    { key: "address", label: N_("Адрес (SA)"), type: "hex", hint: N_("адрес J1939 0..253"),
      when: (_n, c) => c.protocol === "j1939" },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
  ],
  frame: [
    { key: "name", label: N_("Имя"), type: "text" },
    { key: "title", label: N_("Заголовок"), type: "loc", hint: N_("напр. СОСТОЯНИЯ") },
    { key: "type", label: N_("Тип"), type: "select", options: FRAME_TYPES, when: (_n, c) => c.protocol === "canopen" },
    { key: "id", label: "CAN ID", type: "hex", hint: N_("пусто — вычислить (CANopen: тип + node_id, J1939: PGN + SA)") },
    { key: "pgn", label: "PGN", type: "hex", hint: N_("J1939, напр. 0xF004"), when: (_n, c) => c.protocol === "j1939" },
    { key: "priority", label: N_("Приоритет"), type: "int", hint: N_("0..7, по умолчанию 6"), when: (_n, c) => c.protocol === "j1939" },
    { key: "destination", label: N_("Получатель (DA)"), type: "hex", hint: N_("PDU1; пусто — 0xFF (всем)"),
      when: (n, c) => c.protocol === "j1939" && n?.pgn != null && ((n.pgn >> 8) & 0xff) < 240 },
    { key: "receivers", label: N_("Получатели"), type: "strlist", hint: N_("имена устройств через запятую"), wide: true },
    { key: "dlc", label: "DLC", type: "int" },
    { key: "direction", label: N_("Направление"), type: "select", options: [["", N_("по типу")], ["tx", "TX"], ["rx", "RX"]] },
    { key: "extended", label: N_("29-битный ID"), type: "bool", when: (_n, c) => c.protocol !== "j1939" },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
    { key: "comment", label: N_("Примечание"), type: "loc", wide: true },
  ],
  signal: [
    { key: "name", label: N_("Имя"), type: "text" },
    { key: "kind", label: N_("Тип"), type: "select", options: KINDS },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
    { key: "byte_order", label: N_("Порядок байт"), type: "select",
      options: [["", "little-endian"], ["big_endian", "big-endian"]] },
    { key: "signed", label: N_("Знаковое"), type: "bool" },
    { key: "factor", label: N_("Масштаб (factor)"), type: "float", when: numeric },
    { key: "offset", label: N_("Смещение (offset)"), type: "float", when: numeric },
    { key: "unit", label: N_("Единица"), type: "text", when: numeric },
    { key: "min", label: N_("Минимум (min)"), type: "float", when: numeric },
    { key: "max", label: N_("Максимум (max)"), type: "float", when: numeric },
    { key: "multiplexer", label: N_("Селектор mux"), type: "bool" },
    { key: "mux", label: N_("mux (значения селектора)"), type: "intlist", hint: N_("напр. 0 или 1, 2") },
    { key: "initial", label: N_("По умолчанию"), type: "float", hint: N_("физическое значение") },
    { key: "invalid", label: N_("Нет данных (raw)"), type: "intlist", hint: N_("напр. 0xFF или 0xFE, 0xFF") },
    { key: "value_format", label: N_("Значения в документах"), type: "select", options: [["", N_("десятичные")], ["hex", "hex"]],
      when: (n) => n?.values != null },
    { key: "comment", label: N_("Примечание"), type: "loc", wide: true },
  ],
  flag: [
    { key: "name", label: N_("Имя"), type: "text" },
    { key: "bit", label: N_("Бит в поле"), type: "int" },
    { key: "bit_length", label: N_("Длина, бит"), type: "int" },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
  ],
  sdo: [
    { key: "name", label: N_("Имя"), type: "text" },
    { key: "command", label: N_("Команда"), type: "hex", hint: N_("0x2B — запись 2 байт") },
    { key: "index", label: N_("Индекс"), type: "hex" },
    { key: "subindex", label: N_("Субиндекс"), type: "hex" },
    { key: "description", label: N_("Описание"), type: "loc", wide: true },
    { key: "value.name", label: N_("Значение: имя"), type: "text" },
    { key: "value.bit_length", label: N_("Значение: бит"), type: "select",
      options: [["8", "8"], ["16", "16"], ["24", "24"], ["32", "32"]] },
    { key: "value.unit", label: N_("Значение: единица"), type: "text" },
    { key: "value.factor", label: N_("Значение: масштаб"), type: "float" },
  ],
  unknown: [],
};

export class ParseError extends Error {}

/** Строка из поля ввода → значение для YAML (null — удалить ключ). */
// Целое: десятичное или 0x…; «1.5», «1e3» и числа за пределами точности JS не принимаются
const INT_RE = /^[-+]?(0x[0-9a-f]+|[0-9]+)$/i;

/** Разобрать целое число; ParseError, если строка — не целое или слишком большое число. */
export function parseInteger(raw: string): number {
  const s = raw.trim();
  const m = INT_RE.exec(s);
  const v = m ? (/0x/i.test(s) ? (s.startsWith("-") ? -1 : 1) * parseInt(m[1].slice(2), 16) : Number(s.replace(/^\+/, ""))) : NaN;
  if (!Number.isSafeInteger(v)) throw new ParseError(t("«{raw}» — не целое число", { raw }));
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
      const v = /^0x/i.test(s) ? parseInt(s.slice(2), 16) : /^[0-9]+$/.test(s) ? Number(s) : NaN;
      if (!Number.isInteger(v)) throw new ParseError(t("«{raw}» — ожидается число (0x1A или 26)", { raw }));
      return v;
    }
    case "float": {
      const v = Number(s.replace(",", "."));
      if (!Number.isFinite(v)) throw new ParseError(t("«{raw}» — не число", { raw }));
      return v;
    }
    case "strlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean);
      return parts.length ? parts : null;
    }
    case "intlist": {
      const parts = s.split(/[\s,;]+/).filter(Boolean).map((x) => (INT_RE.test(x) ? Number(x.replace(/^\+/, "")) : NaN));
      if (parts.some((x) => !Number.isSafeInteger(x))) throw new ParseError(t("«{raw}» — список целых чисел", { raw }));
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
