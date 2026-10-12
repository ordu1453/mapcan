// Forms of the nodes (src/form): which fields apply, and that they cover the format's schema.

import { describe as group, expect, it } from "vitest";
import { describe, fieldHelp, schemaFields } from "../src/form/help";
import { parseInput, parseInteger, ParseError, selectValue } from "../src/form/input";
import { applies, FORMS, formFields, isRequired, NOT_IN_FORM, optionsOf, type FormContext, type FormKind } from "../src/form/spec";

const ctx = (extra: Partial<FormContext> = {}): FormContext => ({
  values: {}, protocol: "canopen", fd: false, busBrs: null, owner: "pump",
  devices: [{ name: "pump", label: "pump" }], frameDirection: null, signalEncoding: null, bitLength: null,
  hasSelector: false, ...extra,
});

const devices = (...names: string[]) => names.map((name) => ({ name, label: name }));

/** Keys of the fields that apply (the hosts also show fields with a value or a diagnostic). */
const visible = (kind: FormKind, c: FormContext): string[] =>
  formFields(kind).filter((f) => applies(f, c)).map((f) => f.key);

const field = (kind: FormKind, key: string) => formFields(kind).find((f) => f.key === key)!;

group("frame", () => {
  it("CANopen RX frame on a bus with one device: no direction, sender or receivers", () => {
    const keys = visible("frame", ctx({ values: { type: "pdo_rx1" }, frameDirection: "rx" }));
    expect(keys).not.toContain("direction");
    expect(keys).not.toContain("sender");
    expect(keys).not.toContain("receivers");
    expect(keys).not.toContain("extended");
    expect(keys).toContain("length");
  });

  it("RX frame without a type: direction and sender, no receivers", () => {
    const keys = visible("frame", ctx({ devices: devices("pump", "master"), frameDirection: "rx" }));
    expect(keys).toEqual(expect.arrayContaining(["direction", "sender", "extended"]));
    expect(keys).not.toContain("receivers");
  });

  it("TX frame: receivers, no sender", () => {
    const keys = visible("frame", ctx({ values: { type: "pdo_tx1" }, devices: devices("pump", "master") }));
    expect(keys).toContain("receivers");
    expect(keys).not.toContain("sender");
  });

  it("frame of the bus: no direction, a sender and receivers", () => {
    const keys = visible("frame", ctx({ values: { type: "sync" }, devices: devices("pump", "master"), owner: null }));
    expect(keys).not.toContain("direction");
    expect(keys).toEqual(expect.arrayContaining(["sender", "receivers"]));
  });

  it("the type of a CANopen service frame sets its DLC; SYNC has 0 or 1", () => {
    expect(visible("frame", ctx({ values: { type: "nmt" } }))).not.toContain("length");
    expect(visible("frame", ctx({ values: { type: "heartbeat" } }))).not.toContain("length");
    expect(visible("frame", ctx({ values: { type: "sync" } }))).toContain("length");
    expect(visible("frame", ctx({ values: { type: "nmt" }, protocol: "can" }))).toContain("length");
    expect(isRequired(field("frame", "length"), ctx({ values: { type: "sync" } }))).toBe(false);
    expect(isRequired(field("frame", "length"), ctx({ protocol: "can" }))).toBe(true);
  });

  it("no type outside CANopen; J1939 has a PGN and no 29-bit flag", () => {
    const j = visible("frame", ctx({ protocol: "j1939", devices: [], owner: "ecu" }));
    expect(j).not.toContain("type");
    expect(j).not.toContain("extended");
    expect(j).toEqual(expect.arrayContaining(["pgn", "priority"]));
    const c = visible("frame", ctx({ protocol: "can", devices: [], owner: "dev" }));
    expect(c).not.toContain("type");
    expect(c).toContain("extended");
  });

  it("sender and receivers: not the owner, not the sender, with the devices' labels", () => {
    const c = ctx({
      values: { sender: "master" },
      devices: [{ name: "pump", label: "Pump" }, { name: "master", label: "MCU" }, { name: "panel", label: "Panel" }],
    });
    expect(optionsOf(field("frame", "sender"), c)).toEqual([["", "outside the map", undefined],
      ["master", "MCU", undefined], ["panel", "Panel", undefined]]);
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
    expect(isRequired(field("device", "node_id"), ctx({ frames: [{ type: "pdo_tx1" }] }))).toBe(true);
    expect(isRequired(field("device", "node_id"), ctx({ frames: [{ type: "raw", id: 0x100 }] }))).toBe(false);
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
    expect(sig({ signalEncoding: "scaled" })).toEqual(expect.arrayContaining(["factor", "unit"]));
    expect(sig({ signalEncoding: "enum" })).not.toContain("factor");
    expect(visible("signal", ctx({ signalEncoding: "raw", bitLength: 16 }))).toContain("byte_order");
    expect(sig({ signalEncoding: "raw", bitLength: 16 })).toContain("byte_order");
    expect(sig({ signalEncoding: "raw", bitLength: 8 })).not.toContain("byte_order");
    expect(sig({ signalEncoding: "bytes", bitLength: 16 })).not.toContain("byte_order");
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
    expect(parseInput("text", "  ")).toBeNull();
    expect(() => parseInteger("1.5")).toThrow(ParseError);
  });
});
