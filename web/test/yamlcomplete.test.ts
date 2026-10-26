// Suggestions in the YAML tab, against the format's JSON Schema.

import { describe, expect, it } from "vitest";
import { complete, contextPath, schemaAt, type Schema } from "../src/yamlcomplete";
import schemaJson from "../../schema/mapcan.schema.json";

const schema = schemaJson as Schema;

const MAP = [
  "mapcan: 2",
  "document:",
  "  title: Map",
  "buses:",
  "  - name: demo",
  "    protocol: canopen",
  "    devices:",
  "      - name: pump",
  "        frames:",
  "          - name: state",
  "            signals:",
  "              - name: mode",
  "                encoding: enum",
].join("\n");

/** Suggestions at "^" in the text (the marker is removed). */
function at(marked: string, force = false) {
  const pos = marked.indexOf("^");
  return complete(marked.replace("^", ""), pos, schema, force);
}

const labels = (r: ReturnType<typeof at>) => r?.items.map((i) => i.label) ?? [];

describe("contextPath", () => {
  const lines = MAP.split("\n");

  it("finds the mapping a key belongs to", () => {
    expect(contextPath(lines, 2, 2)).toEqual(["document"]);
    expect(contextPath(lines, 5, 4)).toEqual(["buses", "[]"]);
    expect(contextPath(lines, 12, 16)).toEqual(["buses", "[]", "devices", "[]", "frames", "[]", "signals", "[]"]);
    expect(contextPath(lines, 0, 0)).toEqual([]);
  });

  it("reads a list written without an indent under its key", () => {
    expect(contextPath(["buses:", "- name: a", "  protocol: can"], 2, 2)).toEqual(["buses", "[]"]);
  });

  it("answers null inside a multi-line value", () => {
    expect(contextPath(["description: >", "  text", "  more"], 2, 2)).toBeNull();
    expect(contextPath(["a:", "  plain text", "    more"], 2, 4)).toBeNull();
  });
});

describe("schemaAt", () => {
  it("follows references, lists and maps of values", () => {
    expect(schemaAt(schema, ["buses", "[]", "devices", "[]", "frames", "[]", "signals", "[]", "encoding"])?.enum)
      .toEqual(["number", "enum", "bitfield", "bytes"]);
    expect(schemaAt(schema, ["document", "title"])).toBeDefined();
    expect(schemaAt(schema, ["nope"])).toBeUndefined();
    expect(schemaAt(schema, ["buses", "nope", "x"])).toBeUndefined();
  });
});

describe("keys in block notation", () => {
  it("suggests the keys of the mapping that start with the typed word, required ones first", () => {
    const r = at(MAP + "\n                by^");
    expect(labels(r)).toEqual(["byte", "byte_length", "byte_order"]);
    expect(r?.col).toBe(16);
    const sig = at("buses:\n  - name: a\n    devices:\n      - frames:\n          - signals:\n              - ^", true);
    expect(labels(sig).slice(0, 2)).toEqual(["name", "encoding"]);
    expect(sig?.items[0].detail).toBe("string · required");
  });

  it("leaves out the keys already set in the mapping", () => {
    expect(labels(at(MAP + "\n                ^", true))).not.toContain("encoding");
    expect(labels(at(MAP + "\n                ^", true))).not.toContain("name");
    expect(labels(at("document:\n  ti^\n  title: x"))).toEqual([]);
  });

  it("inserts a stub by the type of the value, and chains the next suggestions", () => {
    const items = at("document:\n  ^", true)!.items;
    const title = items.find((i) => i.label === "title")!;
    expect(title.edit.insert).toBe("title: ");
    const history = items.find((i) => i.label === "history")!;
    expect(history.edit.insert).toBe("history:\n    - ");
    expect(history.chain).toBe(true);
    const print = items.find((i) => i.label === "print")!;
    expect(print.edit.insert).toBe("print:\n    ");
    const byteOrder = at(MAP + "\n                byte_or^")!.items[0];
    expect(byteOrder.chain).toBe(true);
    const receivers = at(MAP.split("\n").slice(0, 10).join("\n") + "\n            receiv^")!.items[0];
    expect(receivers.edit.insert).toBe("receivers: []");
    expect(receivers.edit.selStart).toBe(receivers.edit.from + "receivers: [".length);
  });

  it("does not insert a colon that is already there", () => {
    const r = at("document:\n  tit^le2: x");
    expect(r?.items[0].edit.insert).toBe("title");
    expect(at("document:\n  tit^le: x")).toBeNull();
  });

  it("offers a one-line item after a new \"- \"", () => {
    const r = at(MAP + "\n              - ^", true);
    expect(r?.items.at(-1)).toMatchObject({ label: "{ }", chain: true, edit: { insert: "{}" } });
  });

  it("shows nothing without a typed word unless forced, and outside the format", () => {
    expect(at("document:\n  ^")).toBeNull();
    expect(at("nope:\n  ^", true)).toBeNull();
  });
});

describe("values", () => {
  it("suggests the values of an enum after the key", () => {
    expect(labels(at(MAP.replace("encoding: enum", "encoding: ^")))).toEqual(["number", "enum", "bitfield", "bytes"]);
    const r = at(MAP.replace("encoding: enum", "encoding: b^"));
    expect(labels(r)).toEqual(["bitfield", "bytes"]);
    // Right after the colon the value gets a space
    expect(at(MAP.replace("encoding: enum", "encoding:^"))!.items[0].edit.insert).toBe(" number");
    expect(labels(at("buses:\n  - fd: ^"))).toEqual(["true", "false"]);
  });

  it("shows nothing when the value is already complete or free text", () => {
    expect(at(MAP.replace("encoding: enum", "encoding: bitfiel^d"))).toBeNull();
    expect(at("document:\n  title: ^")).toBeNull();
    expect(at("nope: ^")).toBeNull();
  });
});

describe("flow notation", () => {
  const FLAGS = MAP + "\n                flags:\n                  - ";

  it("suggests keys inside {…} minus those written there", () => {
    const r = at(FLAGS + "{bit: 1, ^}", true);
    expect(labels(r)).toEqual(["name", "bit_length", "description", "values"]);
    // values is a table or the name of one in value_tables: written as a scalar
    expect(r?.items.find((i) => i.label === "values")?.edit.insert).toBe("values: ");
    expect(labels(at(FLAGS + "{bit: 1, na^}"))).toEqual(["name"]);
    expect(at(FLAGS + "{bit: 1, ^}")).toBeNull();
  });

  it("suggests values inside {…}", () => {
    const sig = MAP.replace("              - name: mode\n                encoding: enum", "              - {name: x, byte_order: ^}");
    expect(labels(at(sig))).toEqual(["little_endian", "big_endian"]);
    expect(at(sig.replace("byte_order: ^", "byte_order:^"))!.items[0].edit.insert).toBe(" little_endian");
  });

  it("follows nested brackets", () => {
    const nested = MAP.replace("              - name: mode\n                encoding: enum",
      "              - {name: x, flags: [{bit: 0, ^}]}");
    expect(labels(at(nested, true))).toContain("bit_length");
  });

  it("shows nothing inside […], strings and comments", () => {
    expect(at("buses: [^]", true)).toBeNull();
    expect(at(FLAGS + "{name: \"a ^", true)).toBeNull();
    expect(at(FLAGS + "# {^", true)).toBeNull();
    expect(at(FLAGS + "{nope: {^}}", true)).toBeNull();
  });
});
