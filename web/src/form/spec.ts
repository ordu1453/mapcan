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
  /** Raw values: numbers and ranges "lo..hi"; values by meaning ({not_available, error}) are edited in the YAML. */
  | "rawlist"
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
  /** Encoding of the signal computed from the map. */
  signalEncoding: string | null;
  /** Length of the signal computed from the map, bits. */
  bitLength: number | null;
  /** Another signal of the frame is the multiplexer selector. */
  hasSelector: boolean;
  /** CANopen frame types for the Type field, `taken` names the frame that already has that CAN ID. */
  frameTypes?: { type: string; label: string; taken: string | null }[];
  /** Frames of the device as in the YAML, when the host has them (a node address is required if an ID needs it). */
  frames?: { id?: unknown; canopen?: unknown }[];
  /** The document has a revision history (its version and date come from the latest entry). */
  hasHistory?: boolean;
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
  ["", N_("none — explicit ID")], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
  ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
  ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
  ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
];

const ENCODINGS: Option[] = [
  ["enum", N_("enum — enumeration")], ["flag", N_("flag — single flag")], ["bitfield", N_("bitfield — bit field")],
  ["scaled", N_("scaled — scaled value")], ["raw", N_("raw — integer")], ["float", N_("float — IEEE 754 (32/64 bit)")],
  ["bytes", N_("bytes — raw bytes")], ["string", N_("string — text")],
];
const SDO_ENCODINGS: Option[] = ENCODINGS.filter(([v]) => ["enum", "scaled", "raw"].includes(v));

const value = (c: FormContext, key: string): unknown => c.values[key];
/** CANopen function of the frame; "raw" for a frame without one. */
const frameType = (c: FormContext): string => String(value(c, "canopen") ?? "raw");
/** Encoding of the signal: as set in the form, else as computed from the map. */
export const signalEncoding = (c: FormContext): string => String(value(c, "encoding") ?? c.signalEncoding ?? "raw");
const encoding = signalEncoding;
const encodingIn = (...encodings: string[]) => (c: FormContext) => encodings.includes(encoding(c));
const numeric = encodingIn("scaled", "raw", "float");
// A raw integer is the value as is: factor and offset apply to a physical quantity only
const scaledLike = encodingIn("scaled", "float");
/** An empty choice ("not set") is offered only while the field has no value. */
const notSet = (c: FormContext, key: string): Option[] => (value(c, key) == null ? [["", N_("not set")]] : []);

/** Direction of a frame of a device, as the map reads it: from the CANopen function, else received (rx) when another
 * device sends it, else sent (tx). A direction written in the map (deprecated) still counts. */
export const frameDirection = (c: FormContext): string | null => {
  const written = value(c, "direction") as string | undefined;
  if (written) return written;
  const byType = c.protocol === "canopen" ? TYPE_DIRECTION[frameType(c)] : undefined;
  if (byType) return byType;
  const sender = value(c, "sender") as string | undefined;
  return sender && sender !== c.owner ? "rx" : "tx";
};

// Receivers are devices of the bus other than the frame's owner (it sends a TX frame and receives an RX one); the
// frame's sender (written in the YAML) is not offered as a receiver
const others = (c: FormContext): Option[] => c.devices.filter((d) => d.name !== c.owner).map((d) => [d.name, d.label]);
const receivers = (c: FormContext): Option[] => others(c).filter(([d]) => d !== value(c, "sender"));

// The sender of a frame of a device: by default the device itself, or outside the map for a CANopen RX function (from
// the master); naming another device of the bus makes the frame received by its device. A CANopen function that the
// device sends (pdo_tx*, heartbeat…), a broadcast one, or a bus with no other device has no choice.
const rxFunction = (c: FormContext) => c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)] === "rx";
const senderChoice = (c: FormContext) => !!c.owner && (frameType(c) === "raw" || rxFunction(c)) && others(c).length > 0;
const senders = (c: FormContext): Option[] =>
  [["", rxFunction(c) ? N_("outside the map") : N_("the device itself")], ...others(c)];

// BRS: empty means the default (the bus value for a frame, on for a bus), shown in brackets
const brsOptions = (base: string, on: boolean): Option[] =>
  [["", `${t(base)} (${t(on ? N_("on") : N_("off"))})`], ["true", N_("on")], ["false", N_("off")]];

/** A device needs an address if the ID of one of its frames is computed from it (a frame without an explicit id). */
const needsAddress = (c: FormContext, computed: (f: { canopen?: unknown }) => boolean): boolean =>
  (c.frames ?? []).some((f) => f?.id == null && computed(f));

// Signal position: by bytes (byte/bit/byte_length) or by bits (start_bit/bit_length)
const byBytes = (c: FormContext) => value(c, "start_bit") == null;
const bitLength = (c: FormContext): number | null => {
  const bytes = value(c, "byte_length");
  return (value(c, "bit_length") as number | undefined) ?? (typeof bytes === "number" ? bytes * 8 : c.bitLength);
};
// Byte order matters for a number that spans bytes. CANopen (CiA 301) and J1939 carry little-endian data only:
// there the field shows only when it is set (to see and fix it; the validation warns, byte-order-protocol).
const spansBytes = (c: FormContext): boolean => {
  const len = bitLength(c) ?? 0;
  const start = (value(c, "start_bit") as number | undefined)
    ?? (typeof value(c, "byte") === "number" ? (value(c, "byte") as number) * 8 + ((value(c, "bit") as number | undefined) ?? 0) : 0);
  return len > 8 || (len > 1 && (start % 8) + len > 8);
};
const LITTLE_ENDIAN_ONLY = ["canopen", "j1939"];
const multiByte = (c: FormContext) => !["flag", "bytes", "string"].includes(encoding(c))
  && (value(c, "byte_order") != null || (spansBytes(c) && !LITTLE_ENDIAN_ONLY.includes(c.protocol)));
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
      // With a revision history the version and date are those of its latest entry
      { key: "version", label: N_("Version"), type: "text", half: true, placeholder: "0.1.0",
        when: (c) => !c.hasHistory },
      { key: "date", label: N_("Date"), type: "date", half: true, when: (c) => !c.hasHistory },
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
      { key: "connector", label: N_("Connector"), type: "text", half: true, placeholder: "X3" },
      { key: "fd", label: "CAN FD", type: "bool", half: true },
      { key: "brs", label: N_("Bit rate switch (BRS)"), type: "select", half: true,
        options: () => brsOptions(N_("by default"), true), when: (c) => !!value(c, "fd") },
      { key: "data_bitrate", label: N_("Data phase bitrate, bit/s"), type: "int", half: true, placeholder: "2000000",
        when: (c) => !!value(c, "fd") },
      { key: "sample_point", label: N_("Sample point, %"), type: "float", half: true, placeholder: "87.5" },
      { key: "data_sample_point", label: N_("Data phase sample point, %"), type: "float", half: true, placeholder: "75",
        when: (c) => !!value(c, "fd") },
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
        required: (c) => c.protocol === "canopen" && needsAddress(c, (f) => f.canopen != null) },
      { key: "address", label: N_("Address (SA)"), type: "hex", half: true, placeholder: "0x00",
        when: (c) => c.protocol === "j1939",
        required: (c) => c.protocol === "j1939" && needsAddress(c, () => true) },
    ] },
    NOTES,
  ],
  // A frame and a signal are named by their identifier: it comes first, and the optional title defaults to it
  frame: [
    { fields: [
      NAME,
      { key: "title", label: N_("Title"), type: "loc", placeholder: N_("same as the identifier") },
    ] },
    { title: N_("Identification"), fields: [
      // Outside CANopen the type is not used (explicit ID or one from the PGN); a type written in the YAML is shown
      // so that it can be fixed. The VS Code form gets the types from the server, with the frames that took their IDs.
      { key: "canopen", label: N_("CANopen function"), type: "select", when: (c) => c.protocol === "canopen",
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
      // A frame with a period may also be sent on an event (not on request)
      { key: "cycle_ms", label: N_("Period, ms"), type: "int", half: true, layout: true, placeholder: N_("not cyclic"),
        when: (c) => value(c, "trigger") !== "on_request" },
      { key: "trigger", label: N_("Trigger"), type: "select", half: true, layout: true,
        options: (c) => [["", N_("not set")], ["event", N_("on event")],
          ...(value(c, "cycle_ms") == null ? [["on_request", N_("on request")] as Option] : [])] },
      { key: "inhibit_ms", label: N_("Minimum interval, ms"), type: "float", half: true, placeholder: N_("none") },
      { key: "timeout_ms", label: N_("Receive timeout, ms"), type: "int", half: true,
        placeholder: (c) => (typeof value(c, "cycle_ms") === "number" ? String(3 * (value(c, "cycle_ms") as number)) : "") },
    ] },
    { title: N_("Routing"), fields: [
      // Who sends a frame follows from where it is written (its device, or outside the map for a frame of the bus),
      // unless another device is named as its sender: then the frame is described at its receiver. There is no field
      // for the direction: it follows from the CANopen function and the sender.
      { key: "sender", label: N_("Sender"), type: "select", half: true, options: senders, when: senderChoice },
      // The receiver of an RX frame is its device
      { key: "receivers", label: N_("Receivers"), type: "devices", wide: true, options: receivers,
        when: (c) => !(c.owner && frameDirection(c) === "rx") && receivers(c).length > 0 },
    ] },
    NOTES_COMMENT,
  ],
  signal: [
    { fields: [
      NAME,
      { key: "title", label: N_("Title"), type: "loc", placeholder: N_("same as the identifier") },
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
        when: encodingIn("raw", "scaled", "enum") },
      { key: "factor", label: N_("Factor (scale)"), type: "float", half: true, placeholder: "1", when: scaledLike },
      { key: "offset", label: N_("Offset"), type: "float", half: true, placeholder: "0", when: scaledLike },
      { key: "min", label: N_("Minimum (min)"), type: "float", half: true, when: numeric },
      { key: "max", label: N_("Maximum (max)"), type: "float", half: true, when: numeric },
      { key: "initial", label: N_("Initial value"), type: "float", half: true,
        when: (c) => !["bitfield", "bytes", "string"].includes(encoding(c)) && !value(c, "source") },
      { key: "source", label: N_("Value from the map"), type: "select", half: true, when: encodingIn("raw"),
        options: () => [["", N_("none")], ["map_version.major", N_("map version: major")],
          ["map_version.minor", N_("map version: minor")], ["map_version.patch", N_("map version: patch")],
          ["layout_crc32", N_("layout CRC32")]] },
      { key: "charset", label: N_("Charset"), type: "select", half: true, when: encodingIn("string"),
        options: () => [["", "ASCII"], ["utf-8", "UTF-8"], ["latin-1", "Latin-1"]] },
      { key: "terminator", label: N_("Terminator"), type: "text", half: true, placeholder: "0x00, *",
        when: encodingIn("string") },
      { key: "invalid_raw", label: N_("Not available (raw)"), type: "rawlist", half: true, mono: true,
        placeholder: "0xFF, 0xFF00..0xFFFF",
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
    ["organization", "bit_numbering", "print"]
      .map((k) => [k, "document requisites (web: DocumentRequisites.vue)"])
      .concat([["history", "revision history nodes of the tree"]])),
  revision: { changes: "list of changes (web: HistoryEditor.vue)" },
  bus: { frames: "child nodes of the tree", devices: "child nodes of the tree" },
  device: { frames: "child nodes of the tree" },
  frame: {
    signals: "child nodes and the bit layout", sdo: "child nodes of the tree",
    direction: "deprecated: it follows from the CANopen function and the sender",
  },
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
