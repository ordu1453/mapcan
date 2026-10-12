// Form of every node kind, shared by the web editor (components/NodeEditor.vue) and the VS Code form
// (vscode/webview/form.js): which fields a node has, in which sections, when they apply and what they offer.
//
// What a field means comes from the format itself: its help is the field's description in the pydantic model
// (src/mapcan/model.py → schema/mapcan.schema.json). Labels and option texts are English and go through
// t() when shown (N_ marks them for the Russian translation in locale/ru.json).
//
// Adding a field to the format: describe it in the model, then add it here or to NOT_IN_FORM with the
// reason; test/form.test.ts fails until every field of the schema is in one of them.

import { N_, t } from "../i18n";

export type FieldType =
  | "text" | "int" | "hex" | "float" | "bool" | "select" | "date" | "intlist" | "strlist"
  /** Text with translations (title, description): edited in the document language. */
  | "loc"
  /** Unit: free text with the standard units of the document language offered. */
  | "unit"
  /** Set of the bus devices: a toggle per option. */
  | "devices";

/** Option of a select: value, label and whether it is disabled (the current value stays selectable). */
export type Option = [value: string, label: string, disabled?: boolean];

/** What the conditions of the fields know about the node; both hosts fill it from their data. */
export interface FormContext {
  /** The node's fields as in the YAML, the SDO value's under "value.<field>"; text with translations as its text. */
  values: Record<string, unknown>;
  /** Protocol of the node's bus ("" outside a bus). */
  protocol: string;
  /** The bus is CAN FD. */
  fd: boolean;
  /** BRS of the frames as set on the bus (null: not set, on). */
  busBrs: boolean | null;
  /** Device the frame belongs to (null for a frame of the bus). */
  owner: string | null;
  /** Devices of the bus with their labels for people. */
  devices: { name: string; label: string }[];
  /** Direction of the frame computed from the map (also when the field is not set). */
  frameDirection: string | null;
  /** Encoding of the signal computed from the map. */
  signalEncoding: string | null;
  /** Length of the signal computed from the map, bits. */
  bitLength: number | null;
  /** Another signal of the frame is the multiplexer selector. */
  hasSelector: boolean;
  /** CANopen frame types for the Type field, `taken` names the frame that already has that CAN ID. */
  frameTypes?: { type: string; label: string; taken: string | null }[];
  /** Frames of the device as in the YAML, when the host has them (a node address is required if an ID needs it). */
  frames?: { id?: unknown; type?: unknown }[];
}

export interface FieldDef {
  /** Key in the node; nested with a dot: "value.unit". */
  key: string;
  label: string;
  type: FieldType;
  options?: (c: FormContext) => Option[];
  /** The field applies (a field with a value in the YAML or a diagnostic is shown anyway). */
  when?: (c: FormContext) => boolean;
  /** Without a value the map does not pass validation (marked with *). */
  required?: boolean | ((c: FormContext) => boolean);
  /** Example or default shown in the empty field. */
  placeholder?: string | ((c: FormContext) => string);
  /** Help when the field has no description in the model, or for a field outside the model. */
  help?: string;
  /** Short note under the field (web editor only: forms of the document requisites). */
  hint?: string;
  /** Option values are numbers. */
  numeric?: boolean;
  /** Takes half the width in the narrow VS Code panel. */
  half?: boolean;
  /** Takes the whole row in the web editor's grid. */
  wide?: boolean;
  /** Monospaced (identifiers). */
  mono?: boolean;
  /** Edited in a multi-line box in the VS Code panel. */
  multiline?: boolean;
  /** Shown by the web editor in its own position and transmission controls rather than as a form field. */
  layout?: boolean;
}

export interface Section {
  title?: string;
  fields: FieldDef[];
}

export type FormKind = "document" | "revision" | "bus" | "device" | "frame" | "signal" | "flag" | "sdo";

// ------------------------------------------------------------------------------------------------ helpers

/** Direction of CANopen frame types (as in canopen.py); SYNC and TIME have none. */
export const TYPE_DIRECTION: Record<string, string> = {
  nmt: "rx", emcy: "tx", sdo_tx: "tx", sdo_rx: "rx", heartbeat: "tx",
  pdo_tx1: "tx", pdo_tx2: "tx", pdo_tx3: "tx", pdo_tx4: "tx", pdo_rx1: "rx", pdo_rx2: "rx", pdo_rx3: "rx", pdo_rx4: "rx",
};

/** Data lengths of CANopen service frames by CiA 301 (as in canopen.py); without length the smallest is used. */
export const CANOPEN_DLC: Record<string, number[]> = {
  nmt: [2], sync: [0, 1], time: [6], heartbeat: [1], sdo_tx: [8], sdo_rx: [8],
};

const FRAME_TYPES: Option[] = [
  ["raw", N_("raw — explicit ID")], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
  ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
  ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
  ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
];

const ENCODINGS: Option[] = [
  ["enum", N_("enum — enumeration")], ["flag", N_("flag — single flag")], ["bitfield", N_("bitfield — bit field")],
  ["scaled", N_("scaled — scaled value")], ["raw", N_("raw — integer")], ["float", N_("float — IEEE 754 (32/64 bit)")],
  ["bytes", N_("bytes — raw bytes")],
];
const SDO_ENCODINGS: Option[] = ENCODINGS.filter(([v]) => ["enum", "scaled", "raw"].includes(v));

const value = (c: FormContext, key: string): unknown => c.values[key];
const frameType = (c: FormContext): string => String(value(c, "type") ?? "raw");
/** Encoding of the signal: as set in the form, else as computed from the map. */
export const signalEncoding = (c: FormContext): string => String(value(c, "encoding") ?? c.signalEncoding ?? "raw");
const encoding = signalEncoding;
const encodingIn = (...encodings: string[]) => (c: FormContext) => encodings.includes(encoding(c));
const numeric = encodingIn("scaled", "raw", "float");
/** An empty choice ("not set") is offered only while the field has no value. */
const notSet = (c: FormContext, key: string): Option[] => (value(c, key) == null ? [["", N_("not set")]] : []);

/** Direction of the frame: its own, else from the CANopen type, else as computed from the map. */
export const frameDirection = (c: FormContext): string | null =>
  (value(c, "direction") as string | undefined)
  ?? (c.protocol === "canopen" ? TYPE_DIRECTION[frameType(c)] : undefined) ?? c.frameDirection;

// Empty direction: the one computed from the CANopen type or from sender, shown in brackets
const directions = (c: FormContext): Option[] => {
  const base = t(c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)] ? N_("by type") : N_("by default"));
  const d = value(c, "direction") == null ? c.frameDirection : null;
  return [["", d ? `${base} (${d.toUpperCase()})` : base], ["tx", N_("TX (sent by the device)")],
    ["rx", N_("RX (received by the device)")]];
};

// Sender and receivers are devices of the bus other than the frame's owner (it sends a TX frame and
// receives an RX one); the frame's sender is not offered as a receiver
const others = (c: FormContext): Option[] => c.devices.filter((d) => d.name !== c.owner).map((d) => [d.name, d.label]);
const receivers = (c: FormContext): Option[] => others(c).filter(([d]) => d !== value(c, "sender"));

// BRS: empty means the default (the bus value for a frame, on for a bus), shown in brackets
const brsOptions = (base: string, on: boolean): Option[] =>
  [["", `${t(base)} (${t(on ? N_("on") : N_("off"))})`], ["true", N_("on")], ["false", N_("off")]];

/** A device needs an address if the ID of one of its frames is computed from it (a frame without an explicit id). */
const needsAddress = (c: FormContext, computed: (f: { type?: unknown }) => boolean): boolean =>
  (c.frames ?? []).some((f) => f?.id == null && computed(f));

// Signal position: by bytes (byte/bit/byte_length) or by bits (start_bit/bit_length)
const byBytes = (c: FormContext) => value(c, "start_bit") == null;
const bitLength = (c: FormContext): number | null => {
  const bytes = value(c, "byte_length");
  return (value(c, "bit_length") as number | undefined) ?? (typeof bytes === "number" ? bytes * 8 : c.bitLength);
};
// Byte order matters for a value longer than a byte (any protocol: the format allows big-endian everywhere)
const multiByte = (c: FormContext) => !["flag", "bytes"].includes(encoding(c)) && (bitLength(c) ?? 0) > 8;
// The bit in the byte matters only for a value shorter than a byte
const subByte = (c: FormContext) => encoding(c) === "flag" || (bitLength(c) ?? 8) < 8;
// The other fields of the SDO exchange's value appear once it has an identifier
const hasValue = (c: FormContext) => value(c, "value.name") != null;

const NAME: FieldDef = { key: "name", label: N_("Identifier"), type: "text", required: true, mono: true };
const DESCRIPTION: FieldDef = { key: "description", label: N_("Description"), type: "loc", wide: true, multiline: true };
const NOTES: Section = { title: N_("Notes"), fields: [DESCRIPTION] };
/** Frames and signals also have a note (a remark under the description in documents). */
const NOTES_COMMENT: Section = {
  title: N_("Notes"),
  fields: [DESCRIPTION, { key: "comment", label: N_("Note"), type: "loc", wide: true, multiline: true }],
};

// ------------------------------------------------------------------------------------------------ forms

export const FORMS: Record<FormKind, Section[]> = {
  document: [
    { fields: [
      { key: "title", label: N_("Title"), type: "loc", wide: true, required: true },
      { key: "subtitle", label: N_("Subtitle"), type: "loc", wide: true },
      { key: "version", label: N_("Version"), type: "text", half: true, placeholder: "0.1.0" },
      { key: "date", label: N_("Date"), type: "date", half: true },
      { key: "author", label: N_("Document author"), type: "text" },
      { key: "language", label: N_("Document language"), type: "select",
        options: () => [["ru", N_("Russian")], ["en", N_("English")]] },
    ] },
  ],
  revision: [
    { fields: [
      { key: "version", label: N_("Version"), type: "text", half: true, required: true },
      { key: "date", label: N_("Date"), type: "date", half: true },
      { key: "author", label: N_("Author"), type: "text", half: true },
      { key: "github", label: "GitHub", type: "text", half: true, placeholder: N_("username") },
    ] },
  ],
  bus: [
    { fields: [
      { key: "title", label: N_("Title"), type: "loc", required: true, placeholder: N_("Powertrain CAN") },
      NAME,
    ] },
    { title: N_("Bus"), fields: [
      { key: "protocol", label: N_("Protocol"), type: "select", half: true,
        options: () => [["canopen", "CANopen"], ["j1939", "SAE J1939"], ["can", N_("CAN (explicit IDs)")]] },
      { key: "bitrate", label: N_("Bitrate, bit/s"), type: "int", half: true, placeholder: "500000" },
      { key: "interface", label: N_("Interface"), type: "text", half: true, placeholder: "can0" },
      { key: "fd", label: "CAN FD", type: "bool", half: true },
      { key: "brs", label: N_("Bit rate switch (BRS)"), type: "select", half: true,
        options: () => brsOptions(N_("by default"), true), when: (c) => !!value(c, "fd") },
    ] },
    NOTES,
  ],
  device: [
    { fields: [
      { key: "title", label: N_("Full name"), type: "loc", required: true, placeholder: N_("Battery management system") },
      { key: "short", label: N_("Abbreviation"), type: "text", half: true, placeholder: "BMS" },
      { ...NAME, half: true },
    ] },
    { title: N_("Address"), fields: [
      { key: "node_id", label: N_("Node address (node_id)"), type: "hex", half: true, placeholder: "0x01",
        when: (c) => c.protocol === "canopen",
        required: (c) => c.protocol === "canopen" && needsAddress(c, (f) => (f.type ?? "raw") !== "raw") },
      { key: "address", label: N_("Address (SA)"), type: "hex", half: true, placeholder: "0x00",
        when: (c) => c.protocol === "j1939",
        required: (c) => c.protocol === "j1939" && needsAddress(c, () => true) },
    ] },
    NOTES,
  ],
  frame: [
    { fields: [
      { key: "title", label: N_("Title"), type: "loc", placeholder: N_("same as the identifier") },
      NAME,
    ] },
    { title: N_("Identification"), fields: [
      // Outside CANopen the type is not used (explicit ID or one from the PGN); a type written in the YAML is shown
      // so that it can be fixed. The VS Code form gets the types from the server, with the frames that took their IDs.
      { key: "type", label: N_("Type"), type: "select", when: (c) => c.protocol === "canopen",
        options: (c) => (c.frameTypes
          ? c.frameTypes.map(({ type, label, taken }): Option => [type, taken ? `${label} — ${taken}` : label, !!taken])
          : c.protocol === "canopen" ? FRAME_TYPES : FRAME_TYPES.slice(0, 1)) },
      { key: "id", label: "CAN ID", type: "hex", half: true,
        placeholder: (c) => (c.protocol === "can" ? "0x123" : t(N_("computed"))),
        when: (c) => c.protocol !== "canopen" || frameType(c) === "raw" || value(c, "id") != null,
        required: (c) => c.protocol === "can" || (c.protocol === "canopen" && frameType(c) === "raw") },
      { key: "pgn", label: "PGN", type: "hex", half: true, placeholder: "0xF004", when: (c) => c.protocol === "j1939",
        required: (c) => c.protocol === "j1939" && value(c, "id") == null },
      { key: "priority", label: N_("Priority"), type: "int", half: true, placeholder: "6",
        when: (c) => c.protocol === "j1939" },
      { key: "destination", label: N_("Destination (DA)"), type: "hex", half: true, placeholder: "0xFF",
        when: (c) => c.protocol === "j1939" && typeof value(c, "pgn") === "number"
          && (((value(c, "pgn") as number) >> 8) & 0xff) < 240 },
      // CANopen computes 11-bit IDs; a 29-bit one is only for a frame with an explicit ID
      { key: "extended", label: N_("29-bit ID"), type: "bool",
        when: (c) => c.protocol === "can" || (c.protocol === "canopen" && frameType(c) === "raw") },
      { key: "brs", label: N_("Bit rate switch (BRS)"), type: "select", half: true,
        options: (c) => brsOptions(N_("as on the bus"), c.busBrs ?? true), when: (c) => c.fd },
    ] },
    { title: N_("Timing"), fields: [
      // The type of a CANopen service frame sets its length; SYNC is 0 or 1
      { key: "length", label: N_("Length, bytes"), type: "int", half: true,
        placeholder: (c) => (c.protocol === "canopen" && CANOPEN_DLC[frameType(c)]
          ? t(N_("{n} (CiA 301)"), { n: Math.min(...CANOPEN_DLC[frameType(c)]) }) : ""),
        when: (c) => !(c.protocol === "canopen" && CANOPEN_DLC[frameType(c)]?.length === 1),
        required: (c) => !(c.protocol === "canopen" && CANOPEN_DLC[frameType(c)]) },
      { key: "cycle_ms", label: N_("Period, ms"), type: "int", half: true, layout: true, placeholder: N_("not cyclic"),
        when: (c) => value(c, "trigger") == null },
      { key: "trigger", label: N_("Trigger"), type: "select", half: true, layout: true,
        options: () => [["", N_("not set")], ["event", N_("on event")], ["on_request", N_("on request")]],
        when: (c) => value(c, "cycle_ms") == null },
    ] },
    { title: N_("Routing"), fields: [
      // Only a frame of a device has a direction; a CANopen type sets it
      { key: "direction", label: N_("Direction"), type: "select", options: directions,
        when: (c) => !!c.owner && !(c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)]) },
      // A sender is chosen for an RX frame and a frame of the bus (a TX frame is sent by its device)
      { key: "sender", label: N_("Sender"), type: "select",
        options: (c) => [["", N_("outside the map")], ...others(c)],
        when: (c) => (!c.owner || frameDirection(c) === "rx") && others(c).length > 0 },
      // The receiver of an RX frame is its device
      { key: "receivers", label: N_("Receivers"), type: "devices", wide: true, options: receivers,
        when: (c) => !(c.owner && frameDirection(c) === "rx") && receivers(c).length > 0 },
    ] },
    NOTES_COMMENT,
  ],
  signal: [
    { fields: [
      { key: "title", label: N_("Title"), type: "loc", placeholder: N_("same as the identifier") },
      NAME,
      { key: "encoding", label: N_("Encoding"), type: "select", options: (c) => [...notSet(c, "encoding"), ...ENCODINGS] },
    ] },
    { title: N_("Position"), fields: [
      { key: "byte", label: N_("Byte"), type: "int", half: true, layout: true, placeholder: "0", when: byBytes },
      { key: "bit", label: N_("Bit in byte"), type: "int", half: true, layout: true, placeholder: "0",
        when: (c) => byBytes(c) && subByte(c) },
      { key: "start_bit", label: N_("Start bit (LSB)"), type: "int", half: true, layout: true,
        when: (c) => !byBytes(c) },
      { key: "bit_length", label: N_("Length, bits"), type: "int", half: true, layout: true,
        when: (c) => value(c, "byte_length") == null && encoding(c) !== "flag" },
      { key: "byte_length", label: N_("Length, bytes"), type: "int", half: true, layout: true,
        when: (c) => value(c, "byte_length") != null },
      { key: "byte_order", label: N_("Byte order"), type: "select", when: multiByte,
        options: () => [["", N_("little-endian (Intel)")], ["big_endian", N_("big-endian (Motorola)")]] },
    ] },
    { title: N_("Value"), fields: [
      { key: "unit", label: N_("Unit"), type: "unit", half: true, when: numeric },
      { key: "representation", label: N_("Number representation"), type: "select", half: true,
        options: () => [["", N_("unsigned")], ["twos_complement", N_("two's complement")],
          ["ones_complement", N_("ones' complement")], ["sign_magnitude", N_("sign-magnitude")]],
        when: encodingIn("raw", "scaled") },
      { key: "factor", label: N_("Factor (scale)"), type: "float", half: true, placeholder: "1", when: numeric },
      { key: "offset", label: N_("Offset"), type: "float", half: true, placeholder: "0", when: numeric },
      { key: "min", label: N_("Minimum (min)"), type: "float", half: true, when: numeric },
      { key: "max", label: N_("Maximum (max)"), type: "float", half: true, when: numeric },
      { key: "initial", label: N_("Initial value"), type: "float", half: true,
        when: (c) => !["bitfield", "bytes"].includes(encoding(c)) },
      { key: "invalid", label: N_("Invalid (raw)"), type: "intlist", half: true, mono: true, placeholder: "0xFF",
        when: encodingIn("raw", "scaled", "enum") },
      { key: "index", label: N_("Dictionary object: index"), type: "hex", half: true, placeholder: "0x2000",
        when: (c) => c.protocol === "canopen" },
      { key: "subindex", label: N_("Dictionary object: subindex"), type: "hex", half: true, placeholder: "0x00",
        when: (c) => c.protocol === "canopen" },
      { key: "spn", label: "SPN", type: "int", half: true, when: (c) => c.protocol === "j1939" },
      { key: "value_format", label: N_("Value format in documents"), type: "select", half: true,
        options: () => [["", N_("decimal")], ["hex", "hex"]], when: encodingIn("enum") },
    ] },
    { title: N_("Multiplexing"), fields: [
      { key: "multiplexer", label: N_("mux selector"), type: "bool",
        when: (c) => ["raw", "enum"].includes(encoding(c)) && !c.hasSelector },
      { key: "mux", label: N_("mux (selector values)"), type: "intlist", mono: true, placeholder: N_("0 or 1, 2"),
        when: (c) => c.hasSelector },
    ] },
    NOTES_COMMENT,
  ],
  flag: [
    { fields: [
      NAME,
      { key: "bit", label: N_("Bit in field"), type: "int", half: true, required: true },
      { key: "bit_length", label: N_("Length, bits"), type: "int", half: true, placeholder: "1" },
    ] },
    NOTES,
  ],
  sdo: [
    { fields: [
      NAME,
      { key: "command", label: N_("Command"), type: "hex", required: true, placeholder: "0x2B" },
      { key: "index", label: N_("Index"), type: "hex", half: true, required: true, placeholder: "0x6040" },
      { key: "subindex", label: N_("Subindex"), type: "hex", half: true, placeholder: "0x00" },
    ] },
    { title: N_("Value"), fields: [
      { key: "value.name", label: N_("Identifier"), type: "text", mono: true, required: hasValue,
        placeholder: N_("no value") },
      { key: "value.encoding", label: N_("Encoding"), type: "select", when: hasValue,
        options: (c) => [...notSet(c, "value.encoding"), ...SDO_ENCODINGS] },
      { key: "value.bit_length", label: N_("Length, bits"), type: "select", half: true, numeric: true, when: hasValue,
        options: (c) => [...notSet(c, "value.bit_length"), ["8", "8"], ["16", "16"], ["24", "24"], ["32", "32"]] },
      { key: "value.unit", label: N_("Unit"), type: "unit", half: true, when: hasValue },
      { key: "value.factor", label: N_("Factor (scale)"), type: "float", half: true, placeholder: "1", when: hasValue },
      { key: "value.offset", label: N_("Offset"), type: "float", half: true, placeholder: "0", when: hasValue },
    ] },
    NOTES,
  ],
};

/** Fields of the format that the forms do not show, with where they are edited instead. */
export const NOT_IN_FORM: Record<FormKind, Record<string, string>> = {
  document: Object.fromEntries(
    ["organization", "bit_numbering", "logo", "designation", "litera", "city", "signatures", "approve", "agree"]
      .map((k) => [k, "document requisites (web: DocumentRequisites.vue)"])
      .concat([["history", "revision history nodes of the tree"]])),
  revision: { changes: "list of changes (web: HistoryEditor.vue)" },
  bus: { frames: "child nodes of the tree", devices: "child nodes of the tree" },
  device: { frames: "child nodes of the tree" },
  frame: { signals: "child nodes and the bit layout", sdo: "child nodes of the tree" },
  signal: { values: "value table", flags: "flags table" },
  flag: { values: "value table" },
  sdo: {
    "value.description": "YAML", "value.representation": "YAML", "value.min": "YAML", "value.max": "YAML",
    "value.values": "value table",
  },
};

/** Fields of a form, in order. */
export const formFields = (kind: string): FieldDef[] =>
  (FORMS[kind as FormKind] ?? []).flatMap((s) => s.fields);

/** The field applies to the node (fields with a value are shown by the hosts anyway). */
export const applies = (f: FieldDef, c: FormContext): boolean => !f.when || f.when(c);

export const isRequired = (f: FieldDef, c: FormContext): boolean =>
  typeof f.required === "function" ? f.required(c) : !!f.required;

export const placeholderOf = (f: FieldDef, c: FormContext): string =>
  t((typeof f.placeholder === "function" ? f.placeholder(c) : f.placeholder) ?? "");

export const optionsOf = (f: FieldDef, c: FormContext): Option[] =>
  (f.options?.(c) ?? []).map(([v, label, disabled]) => [v, t(label), disabled]);
