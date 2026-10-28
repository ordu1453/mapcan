// Forms of the nodes (src/form): which fields apply, and that they cover the format's schema.

import { describe as group, expect, it } from "vitest";
// The format's description: the table of encodings says which value fields each one has
import formatDoc from "../../docs/format.md?raw";
import { describe, fieldHelp, schemaFields } from "../src/form/help";
import { formatValue, parseInput, parseInteger, ParseError, selectValue } from "../src/form/input";
import { applies, encodingChangeOps, FORMS, formFields, isRequired, NOT_IN_FORM, optionsOf, type FormContext,
  type FormKind } from "../src/form/spec";

const ctx = (extra: Partial<FormContext> = {}): FormContext => ({
  values: {}, protocol: "canopen", fd: false, busBrs: null, owner: "pump",
  devices: [{ name: "pump", label: "pump" }], signalEncoding: null, bitLength: null,
  hasSelector: false, ...extra,
});

const devices = (...names: string[]) => names.map((name) => ({ name, label: name }));

/** Keys of the fields that apply (the hosts also show fields with a value or a diagnostic). */
const visible = (kind: FormKind, c: FormContext): string[] =>
  formFields(kind).filter((f) => applies(f, c)).map((f) => f.key);

const field = (kind: FormKind, key: string) => formFields(kind).find((f) => f.key === key)!;

group("frame", () => {
  it("CANopen RX frame on a bus with one device: no direction, sender or receivers", () => {
    const keys = visible("frame", ctx({ values: { canopen: "pdo_rx1" } }));
    expect(keys).not.toContain("direction");
    expect(keys).not.toContain("sender");
    expect(keys).not.toContain("receivers");
    expect(keys).not.toContain("extended");
    expect(keys).toContain("length");
  });

  it("no field for the direction: it follows from the CANopen function and the sender", () => {
    expect(formFields("frame").map((f) => f.key)).not.toEqual(expect.arrayContaining(["direction"]));
  });

  it("the sender: the device itself or another device; outside the map for a CANopen RX function", () => {
    const own = ctx({ protocol: "can", devices: devices("pump", "master") });
    expect(visible("frame", own)).toContain("sender");
    expect(optionsOf(field("frame", "sender"), own).map(([v]) => v)).toEqual(["", "master"]);
    const rx = ctx({ values: { canopen: "pdo_rx1" }, devices: devices("pump", "master") });
    expect(visible("frame", rx)).toContain("sender");
    expect(optionsOf(field("frame", "sender"), rx)[0][1]).toBe("outside the map");
    // A CANopen function the device sends, and a frame of the bus: no choice
    expect(visible("frame", ctx({ values: { canopen: "pdo_tx1" }, devices: devices("pump", "master") }))).not.toContain("sender");
    expect(visible("frame", ctx({ owner: null, protocol: "can", devices: devices("pump", "master") }))).not.toContain("sender");
  });

  it("a frame of a device: receivers; a sender written in the YAML makes it received, without receivers", () => {
    const own = ctx({ devices: devices("pump", "master") });
    expect(visible("frame", own)).toContain("receivers");
    const received = ctx({ values: { sender: "master" }, devices: devices("pump", "master") });
    expect(visible("frame", received)).toContain("extended");
    expect(visible("frame", received)).not.toContain("receivers");
  });

  it("a CANopen RX function is received by its device: no receivers", () => {
    const c = ctx({ values: { canopen: "pdo_rx1" }, devices: devices("pump", "master") });
    expect(visible("frame", c)).not.toContain("receivers");
  });

  it("a direction written in the map still counts", () => {
    const c = ctx({ values: { direction: "rx" }, devices: devices("pump", "master") });
    expect(visible("frame", c)).not.toContain("receivers");
  });

  it("TX frame: receivers", () => {
    const keys = visible("frame", ctx({ values: { canopen: "pdo_tx1" }, devices: devices("pump", "master") }));
    expect(keys).toContain("receivers");
  });

  it("frame of the bus: no direction, receivers", () => {
    const keys = visible("frame", ctx({ values: { canopen: "sync" }, devices: devices("pump", "master"), owner: null }));
    expect(keys).not.toContain("direction");
    expect(keys).toContain("receivers");
  });

  it("the type of a CANopen service frame sets its DLC; SYNC has 0 or 1", () => {
    expect(visible("frame", ctx({ values: { canopen: "nmt" } }))).not.toContain("length");
    expect(visible("frame", ctx({ values: { canopen: "heartbeat" } }))).not.toContain("length");
    expect(visible("frame", ctx({ values: { canopen: "sync" } }))).toContain("length");
    expect(visible("frame", ctx({ values: { canopen: "nmt" }, protocol: "can" }))).toContain("length");
    expect(isRequired(field("frame", "length"), ctx({ values: { canopen: "sync" } }))).toBe(false);
    expect(isRequired(field("frame", "length"), ctx({ protocol: "can" }))).toBe(true);
  });

  it("no type outside CANopen; J1939 has a PGN and no 29-bit flag", () => {
    const j = visible("frame", ctx({ protocol: "j1939", devices: [], owner: "ecu" }));
    expect(j).not.toContain("canopen");
    expect(j).not.toContain("extended");
    expect(j).toEqual(expect.arrayContaining(["pgn", "priority"]));
    const c = visible("frame", ctx({ protocol: "can", devices: [], owner: "dev" }));
    expect(c).not.toContain("canopen");
    expect(c).toContain("extended");
  });

  it("receivers: not the owner, not the sender, with the devices' labels", () => {
    const c = ctx({
      values: { sender: "master" },
      devices: [{ name: "pump", label: "Pump" }, { name: "master", label: "MCU" }, { name: "panel", label: "Panel" }],
    });
    expect(optionsOf(field("frame", "receivers"), c)).toEqual([["panel", "Panel", undefined]]);
  });

  it("BRS only on a CAN FD bus; empty shows the bus default", () => {
    expect(visible("frame", ctx())).not.toContain("brs");
    expect(visible("frame", ctx({ fd: true }))).toContain("brs");
    expect(optionsOf(field("frame", "brs"), ctx({ fd: true, busBrs: false }))[0]).toEqual(["", "as on the bus (off)", undefined]);
    expect(selectValue("false")).toBe(false);
    expect(selectValue("")).toBeNull();
  });
});

group("other nodes", () => {
  it("device address by protocol, required when an ID is computed from it", () => {
    expect(visible("device", ctx())).toContain("node_id");
    expect(visible("device", ctx({ protocol: "j1939" }))).toContain("address");
    expect(visible("device", ctx({ protocol: "can" }))).not.toContain("node_id");
    expect(isRequired(field("device", "node_id"), ctx({ frames: [{ canopen: "pdo_tx1" }] }))).toBe(true);
    expect(isRequired(field("device", "node_id"), ctx({ frames: [{ id: 0x100 }] }))).toBe(false);
  });

  it("the title of a bus and a device is required, of a frame and a signal it is not", () => {
    expect(field("bus", "title").required).toBe(true);
    expect(field("device", "title").required).toBe(true);
    expect(field("frame", "title").required).toBeFalsy();
    expect(field("signal", "title").required).toBeFalsy();
  });

  it("fields of the SDO value appear once it has an identifier", () => {
    expect(visible("sdo", ctx())).not.toContain("value.unit");
    expect(visible("sdo", ctx({ values: { "value.name": "speed" } }))).toContain("value.unit");
  });

  it("signal fields by its encoding and length", () => {
    const sig = (extra: Partial<FormContext>) => visible("signal", ctx({ protocol: "can", ...extra }));
    expect(sig({ signalEncoding: "number" })).toEqual(expect.arrayContaining(["factor", "unit", "invalid_raw"]));
    expect(sig({ signalEncoding: "enum" })).not.toContain("factor");
    // Each encoding has only its own value fields
    const own = (enc: string) => sig({ signalEncoding: enc }).filter((k) =>
      ["unit", "representation", "factor", "offset", "min", "max", "initial", "source", "invalid_raw", "value_format",
        "charset", "terminator", "multiplexer"].includes(k)).sort();
    expect(own("number")).toEqual(["factor", "initial", "invalid_raw", "max", "min", "multiplexer", "offset",
      "representation", "source", "unit"]);
    expect(own("enum")).toEqual(["initial", "multiplexer", "value_format"]);
    expect(own("bitfield")).toEqual([]);
    expect(own("bytes")).toEqual(["charset"]);
    // Floating point: no raw-value fields of an integer
    expect(sig({ signalEncoding: "number", values: { representation: "float" } })).not.toContain("invalid_raw");
    // Bytes: a terminator only for text
    expect(sig({ signalEncoding: "bytes" })).not.toContain("terminator");
    expect(sig({ signalEncoding: "bytes", values: { charset: "ascii" } })).toContain("terminator");
    expect(sig({ signalEncoding: "number", bitLength: 16 })).toContain("byte_order");
    expect(sig({ signalEncoding: "number", bitLength: 8 })).not.toContain("byte_order");
    expect(sig({ signalEncoding: "bytes", bitLength: 16 })).not.toContain("byte_order");
    // A multi-byte bit field: the order decides which byte holds its bit 0
    expect(sig({ signalEncoding: "bitfield", bitLength: 16 })).toContain("byte_order");
    // Fewer than 8 bits across a byte boundary: the order matters too
    expect(sig({ signalEncoding: "number", bitLength: 6, values: { start_bit: 4, bit_length: 6 } })).toContain("byte_order");
    expect(sig({ signalEncoding: "number", bitLength: 6, values: { byte: 1, bit: 2, bit_length: 6 } })).not.toContain("byte_order");
  });

  it("CANopen and J1939 carry little-endian data: no byte order unless it is set", () => {
    for (const protocol of ["canopen", "j1939"]) {
      expect(visible("signal", ctx({ protocol, signalEncoding: "number", bitLength: 16 }))).not.toContain("byte_order");
      expect(visible("signal", ctx({ protocol, signalEncoding: "bitfield", bitLength: 16 }))).not.toContain("byte_order");
      // Set in the YAML: shown, to see and fix it
      expect(visible("signal", ctx({ protocol, signalEncoding: "number", bitLength: 16, values: { byte_order: "big_endian" } })))
        .toContain("byte_order");
    }
  });
});

group("forms and the format", () => {
  const kinds = Object.keys(FORMS) as FormKind[];

  it("every field of the schema is in the form or in NOT_IN_FORM", () => {
    for (const kind of kinds) {
      const shown = new Set([...formFields(kind).map((f) => f.key), ...Object.keys(NOT_IN_FORM[kind])]);
      expect(schemaFields(kind).filter((k) => !shown.has(k)), kind).toEqual([]);
    }
  });

  it("every field of the forms and of NOT_IN_FORM is in the schema", () => {
    for (const kind of kinds) {
      const known = new Set(schemaFields(kind));
      const keys = [...formFields(kind).map((f) => f.key), ...Object.keys(NOT_IN_FORM[kind])];
      expect(keys.filter((k) => !known.has(k)), kind).toEqual([]);
    }
  });

  it("the value fields of a signal are those the format allows for its encoding (docs/format.md)", () => {
    // The table of encodings: | `raw` | meaning | `representation`, `unit`, … |; the validation is checked against it too
    const doc = formatDoc.replaceAll("\r", "");
    const rows: string[] = doc.split("#### Encodings")[1].split("\n\n")[2].split("\n").slice(2);
    const allowed = new Map<string, Set<string>>(rows.map((r) => {
      const cells = r.split("|").map((c) => c.trim());
      return [cells[1].replace(/`/g, ""), new Set(Array.from(cells[3].matchAll(/`(\w+)`/g), (m) => m[1]))];
    }));
    const keys = new Set([...allowed.values()].flatMap((f) => [...f]));
    const fields = formFields("signal").filter((f) => keys.has(f.key));
    expect(fields.length).toBeGreaterThan(5);
    for (const [enc, own] of allowed) {
      // With a charset, so that the terminator of a text shows too
      const shown = fields.filter((f) => applies(f, ctx({ protocol: "can", signalEncoding: enc, values: { charset: "ascii" } })))
        .map((f) => f.key);
      expect(shown.sort(), enc).toEqual(fields.map((f) => f.key).filter((k) => own.has(k)).sort());
    }
  });

  it("a field is in a form once", () => {
    for (const kind of kinds) {
      const keys = formFields(kind).map((f) => f.key);
      expect(keys.filter((k, i) => keys.indexOf(k) !== i), kind).toEqual([]);
    }
  });

  it("fields of the frames, signals, buses and devices have help from the format", () => {
    for (const kind of ["bus", "device", "frame", "signal", "flag", "sdo"] as FormKind[]) {
      const missing = formFields(kind).filter((f) => !f.key.startsWith("value.") && !fieldHelp(kind, f)).map((f) => f.key);
      expect(missing, kind).toEqual([]);
    }
    expect(describe("frame", "brs")).toMatch(/BRS/);
  });
});

group("input", () => {
  it("integers and hex", () => {
    expect(parseInteger("0x1A")).toBe(26);
    expect(parseInput("hex", "26")).toBe(26);
    expect(parseInput("hex", "0x1a")).toBe(26);
    // Typos do not silently become another number
    for (const raw of ["0x12 34", "0x1G", "-5", "0x", "1.5", "0x20000000000001"]) {
      expect(() => parseInput("hex", raw)).toThrow(ParseError);
    }
    expect(parseInput("float", "1,5")).toBe(1.5);
    expect(parseInput("intlist", "1, 2")).toEqual([1, 2]);
    expect(parseInput("rawlist", "0xFF")).toBe(255);
    expect(parseInput("rawlist", "0xFE, 0xFF00..0xFFFF")).toEqual([254, "0xFF00..0xFFFF"]);
    expect(() => parseInput("rawlist", "0xFF..0x10")).toThrow(ParseError);
    expect(() => parseInput("rawlist", "1..x")).toThrow(ParseError);
    expect(formatValue("rawlist", { not_available: ["0xFF00..0xFFFF"], error: 7 }))
      .toBe("not_available: 0xFF00..0xFFFF; error: 0x07");
    // Raw codes are shown in hex as they are written; a negative value of a signed signal as it is (#148)
    expect(formatValue("rawlist", 255)).toBe("0xFF");
    expect(formatValue("rawlist", [254, "0xFF00..0xFFFF", -1])).toBe("0xFE, 0xFF00..0xFFFF, -1");
    expect(parseInput("text", "  ")).toBeNull();
    expect(() => parseInteger("1.5")).toThrow(ParseError);
  });
});

group("encoding change", () => {
  const path = ["buses", 0, "frames", 0, "signals", 1];

  it("the list offers the four encodings without explanations", () => {
    const opts = optionsOf(field("signal", "encoding"), ctx({ values: { encoding: "number" } }));
    expect(opts.map(([v, label]) => [v, label])).toEqual(
      [["number", "number"], ["enum", "enum"], ["bitfield", "bitfield"], ["bytes", "bytes"]]);
  });

  it("removes the fields of the former encoding in one step", () => {
    const node = { name: "s", encoding: "number", byte: 2, byte_length: 2, unit: "V", factor: 0.1, min: 0,
      description: "x", mux: 1, multiplexer: true };
    expect(encodingChangeOps(path, node, "enum")).toEqual([
      { op: "set", path: [...path, "encoding"], value: "enum" },
      { op: "remove", path: [...path, "factor"] }, { op: "remove", path: [...path, "unit"] },
      { op: "remove", path: [...path, "min"] },
    ]);
    // A bit field cannot be a selector; its tables go with the encoding
    const ops = encodingChangeOps(path, { encoding: "enum", values: { 0: "OFF" }, multiplexer: true }, "bitfield");
    expect(ops.map((o) => o.path.at(-1))).toEqual(["encoding", "values", "multiplexer"]);
  });

  it("keeps the length a float implied, so the position stays", () => {
    const float = { encoding: "number", byte: 0, representation: "float", unit: "V" };
    expect(encodingChangeOps(path, float, "enum")).toContainEqual({ op: "set", path: [...path, "bit_length"], value: 32 });
    const written = encodingChangeOps(path, { ...float, bit_length: 64 }, "enum");
    expect(written.filter((o) => o.op === "set").map((o) => o.path.at(-1))).toEqual(["encoding"]);
  });
});
