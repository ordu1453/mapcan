// Labels of nodes in the tree: titles for people instead of identifiers, links to received frames.

import { describe, expect, it } from "vitest";
import { buildTree, canonicalPath, deviceLabel, deviceObjects, displayName, flagFits, includedFile, isLink, localPath, mergedPath,
  namedTable, nodeKind, pathKey, shiftedFlags, viewOf, type TreeNode } from "../src/model";
import { issueUrl, ISSUES_URL } from "../src/links";
import type { ResolvedFrame } from "../src/types";

const data = {
  document: { title: "Карта" },
  buses: [{
    name: "can1", title: "Шина 1", protocol: "canopen",
    devices: [
      {
        name: "bms", short: "BMS", title: { ru: "Система управления батареей", en: "Battery management" },
        frames: [{ name: "bms_status", title: "Состояния", signals: [{ name: "soc", title: "Заряд" }, { name: "temp" }] }],
      },
      { name: "panel", frames: [] },
    ],
  }],
};

const frame = (path: Array<string | number>, extra: Partial<ResolvedFrame>): ResolvedFrame => ({
  path, name: "", ref: null, can_id: 0x181, extended: false, length: 8, type: "pdo_tx1", direction: "tx",
  device: null, sender: null, receivers: [], signals: [], ...extra,
});

const status = frame(["buses", 0, "devices", 0, "frames", 0],
  { name: "bms_status", device: "bms", sender: "bms", receivers: ["panel"] });
const tree = buildTree(data, new Map([[pathKey(status.path), status]]), "ru");
const bus = tree[1];
const find = (n: TreeNode, kind: string): TreeNode[] => [n, ...n.children.flatMap((c) => find(c, kind))]
  .filter((x) => x.kind === kind);

describe("labels", () => {
  it("title instead of the identifier, with the abbreviation for a device", () => {
    expect(displayName(data.buses[0].devices[0], "ru")).toBe("BMS · Система управления батареей");
    expect(displayName(data.buses[0].devices[0], "en")).toBe("BMS · Battery management");
    expect(displayName({ name: "panel" }, "ru")).toBe("panel");
    expect(deviceLabel(data.buses[0].devices[0], "ru")).toBe("BMS");
    expect(deviceLabel({ name: "x", title: "Икс" }, "ru")).toBe("Икс");
  });

  it("tree: a bus shows its identifier on the right, frames and signals their title, without one their name", () => {
    expect(bus.label).toBe("Шина 1");
    expect(bus.sub).toBe("");
    const [bms, panel] = bus.children;
    expect(bms.label).toBe("BMS · Система управления батареей");
    expect(panel.label).toBe("panel");
    // A device of a CANopen bus has its object dictionary first (#151)
    expect(bms.children[0]).toMatchObject({ kind: "objects", path: ["buses", 0, "devices", 0, "objects"], label: "Objects" });
    expect(bms.children[1].label).toBe("Состояния");
    expect(find(bms, "signal").map((s) => s.label)).toEqual(["Заряд", "temp"]);
    // search by identifier keeps working
    expect(bms.children[1].search).toContain("bms_status");
  });

  it("a bus shows its estimated load from the server (#131)", () => {
    const loads = new Map([[pathKey(["buses", 0]), { load: "≥12%", note: "Estimated bus load: ≥12%" }]]);
    const [, loaded] = buildTree(data, new Map(), "ru", [], loads);
    expect(loaded.sub).toBe("≥12%");
    expect(loaded.subHint).toBe("Estimated bus load: ≥12%");
  });

  it("a received frame is a link under the receiver with the sender in its label", () => {
    const [bms, panel] = bus.children;
    expect(bms.children.filter((c) => c.from !== undefined)).toEqual([]);
    const link = panel.children[1];
    expect(link.label).toBe("BMS · Состояния");
    expect(link.path).toEqual(status.path);
    expect(link.receiver).toBe("panel");
    expect(link.dir).toBe("rx");
    expect(link.key).not.toBe(pathKey(status.path));
  });
});

describe("canonical path (#100)", () => {
  it("names the bus, frame, signal and flag, not the device", () => {
    const flags = { buses: [{ name: "can1", frames: [{ name: "nmt" }],
      devices: [{ name: "bms", frames: [{ name: "faults", signals: [{ name: "bits", flags: [{ name: "ov" }] }] }] }] }] };
    expect(canonicalPath(flags, ["buses", 0, "frames", 0])).toBe("can1.nmt");
    expect(canonicalPath(flags, ["buses", 0, "devices", 0, "frames", 0, "signals", 0, "flags", 0])).toBe("can1.faults.bits.ov");
    expect(canonicalPath(data, ["buses", 0, "devices", 0, "frames", 0, "signals", 1])).toBe("can1.bms_status.temp");
  });

  it("is null for other nodes and while a name is missing", () => {
    expect(canonicalPath(data, ["buses", 0])).toBeNull();
    expect(canonicalPath(data, ["buses", 0, "devices", 0])).toBeNull();
    expect(canonicalPath({ buses: [{ name: "can1", frames: [{}] }] }, ["buses", 0, "frames", 0])).toBeNull();
  });
});

describe("object dictionary of a device (#151)", () => {
  const dev = ["buses", 0, "devices", 0];
  const device = {
    name: "drive",
    frames: [
      { name: "tpdo1", canopen: "pdo_tx1", signals: [
        { name: "status", index: 0x6041, encoding: "number", bit_length: 16 },
        { name: "a", title: "Ток A", index: 0x2100, subindex: 1, encoding: "number", bit_length: 16 },
        { name: "b", index: 0x2100, subindex: 2, encoding: "number", bit_length: 16 },
        { name: "spare", encoding: "number", bit_length: 8 },
      ] },
      { name: "rpdo1", canopen: "pdo_rx1", signals: [
        { name: "mode", index: 0x2200, subindex: 1, encoding: "enum", bit_length: 8 },
        { name: "speed", index: 0x2200, subindex: 2, encoding: "number", bit_length: 32 },
      ] },
      { name: "sdo_rx", canopen: "sdo_rx", sdo: [{ name: "save", command: 0x23, index: 0x1010, subindex: 1 }] },
      { name: "raw", id: 0x300, signals: [{ name: "plain", encoding: "number", bit_length: 8 }] },
    ],
  };
  const tpdo = frame([...dev, "frames", 0], { name: "tpdo1", can_id: 0x181 });
  const objects = deviceObjects(device, dev, new Map([[pathKey(tpdo.path), tpdo]]), "ru");

  it("is a page of the tree under a CANopen device only", () => {
    expect(nodeKind([...dev, "objects"])).toBe("objects");
    const [, can] = buildTree({ buses: [{ name: "c", protocol: "can", devices: [device] }] }, new Map(), "ru");
    expect(find(can, "objects")).toEqual([]);
    const [, co] = buildTree({ buses: [{ name: "c", devices: [device] }] }, new Map(), "ru");
    expect(find(co, "objects").map((n) => n.sub)).toEqual(["4"]);
  });

  it("lists objects by index: a var, an array of one type, a record of several, entries by subindex", () => {
    expect(objects.map((o) => [o.index, o.type])).toEqual([
      [0x1010, "array"], [0x2100, "array"], [0x2200, "record"], [0x6041, "var"], [null, null]]);
    const [save, currents] = objects;
    expect(save.entries[0]).toMatchObject({ via: "sdo", name: "save", subindex: 1, path: [...dev, "frames", 2, "sdo", 0] });
    expect(currents.entries.map((e) => [e.label, e.subindex, e.canId, e.via])).toEqual([
      ["Ток A", 1, "0x181", "pdo"], ["b", 2, "0x181", "pdo"]]);
  });

  it("offers the signals of PDOs without an index; signals of other frames only with one", () => {
    const loose = objects.filter((o) => o.index === null).flatMap((o) => o.entries.map((e) => e.name));
    expect(loose).toEqual(["spare"]);
  });
});

describe("flags of a bit field (#150)", () => {
  // An 8-bit field: a at bit 0, b at bits 2..3, c at bit 6
  const flags = [{ bit: 0 }, { bit: 2, bit_length: 2 }, { bit: 6 }];

  it("a flag fits inside the field and over no other flag", () => {
    expect(flagFits(flags, 0, 1, 1, 8)).toBe(true);
    expect(flagFits(flags, 0, 2, 1, 8)).toBe(false);       // over b
    expect(flagFits(flags, 2, 7, 2, 8)).toBe(false);       // beyond the field
    expect(flagFits(flags, 1, 3, 3, 8)).toBe(true);        // b over its own bits, up to bit 5
  });

  it("ticked flags move together, or not at all", () => {
    expect(shiftedFlags(flags, [0, 1, 2], 1, 8)).toEqual([1, 3, 7]);
    expect(shiftedFlags(flags, [0, 1, 2], 2, 8)).toBeNull();   // c would leave the field
    expect(shiftedFlags(flags, [0], 1, 8)).toEqual([1]);
    expect(shiftedFlags(flags, [0], 2, 8)).toBeNull();         // a would land on b, which stays
    expect(shiftedFlags(flags, [1, 2], -1, 8)).toEqual([1, 5]);
  });
});

describe("a frame described at its receiver", () => {
  // panel receives a frame that bms sends, written at panel with sender: bms
  const map = {
    buses: [{
      name: "can1", protocol: "canopen",
      devices: [{ name: "bms", short: "BMS", frames: [] },
        { name: "panel", title: "Панель", frames: [{ name: "cmd", title: "Команда", sender: "bms" }] }],
    }],
  };
  const cmd = frame(["buses", 0, "devices", 1, "frames", 0],
    { name: "cmd", device: "panel", sender: "bms", receivers: ["panel"], direction: "rx" });
  const [, can1] = buildTree(map, new Map([[pathKey(cmd.path), cmd]]), "ru");
  const [bms, panel] = can1.children;

  it("the frame names its sender", () => {
    expect(panel.children[1].label).toBe("BMS · Команда");
    expect(isLink(panel.children[1])).toBe(false);
  });

  it("the sender has a link to it, named after the device it is described at", () => {
    const link = bms.children[1];
    expect(isLink(link)).toBe(true);
    expect([link.label, link.dir, link.to, link.sender]).toEqual(["Панель · Команда", "tx", "Панель", "bms"]);
    expect(link.path).toEqual(cmd.path);
    expect(link.key).not.toBe(pathKey(cmd.path));
  });
});

describe("included files", () => {
  const included = [{ path: ["buses", 0, "devices", 1], file: "common.yaml" }];
  const view = viewOf({ data: { ...data, buses: [] }, included_buses: data.buses });

  it("the tree is built together with the included buses", () => {
    expect(view.buses).toBe(data.buses);
    expect(viewOf({ data, included_buses: null })).toBe(data);
  });

  it("nodes of an included file are marked with the file, the root separately", () => {
    const [, bus] = buildTree(view, new Map(), "ru", included);
    const [bms, panel] = bus.children;
    expect(bms.file).toBeUndefined();
    expect(panel.file).toBe("common.yaml");
    expect(panel.fileRoot).toBe(true);
    expect(includedFile(included, ["buses", 0, "devices", 1, "frames", 0])).toBe("common.yaml");
    expect(includedFile(included, ["buses", 0, "devices", 0])).toBeNull();
  });

  it("a node's path in its file and back (the YAML tab of that file)", () => {
    const parts = [
      { path: ["buses", 0, "devices", 1], file: "panel.yaml", local: ["buses", 0, "devices", 0] },
      { path: ["buses", 1], file: "common.yaml", local: ["buses", 0] },
    ];
    expect(localPath(parts, ["buses", 0, "devices", 1, "frames", 2]))
      .toEqual({ file: "panel.yaml", path: ["buses", 0, "devices", 0, "frames", 2] });
    expect(localPath(parts, ["buses", 1, "devices", 0])).toEqual({ file: "common.yaml", path: ["buses", 0, "devices", 0] });
    expect(localPath(parts, ["buses", 0, "devices", 0])).toEqual({ file: null, path: ["buses", 0, "devices", 0] });
    expect(mergedPath(parts, "panel.yaml", ["buses", 0, "devices", 0, "frames", 2]))
      .toEqual(["buses", 0, "devices", 1, "frames", 2]);
    expect(mergedPath(parts, "common.yaml", ["buses", 0, "name"])).toEqual(["buses", 1, "name"]);
    expect(mergedPath(parts, "panel.yaml", ["buses", 0])).toBeNull();    // the bus only extended by the file
    expect(mergedPath(parts, null, ["document"])).toEqual(["document"]);
  });
});

describe("report an issue", () => {
  it("a new issue with the versions filled in, the map is not in it", () => {
    const url = new URL(issueUrl({ version: "0.23.1", mode: "app", system: "Windows 11, Python 3.12.8" }));
    expect(url.origin + url.pathname).toBe(ISSUES_URL);
    const body = url.searchParams.get("body") ?? "";
    expect(body).toContain("mapcan 0.23.1, web editor (mapcan app)");
    expect(body).toContain("Server: Windows 11, Python 3.12.8");
    expect(body).toContain("Browser: ");
    expect(issueUrl(null)).toBe(ISSUES_URL);
  });
});

describe("named value tables (#143)", () => {
  const text = [
    "mapcan: 2",
    "value_tables:",
    "  states: {0: OFF, 1: ON}",
    "buses: []",
  ].join("\n");
  const own = { value_tables: { states: { 0: "OFF", 1: "ON" } }, buses: [] };
  const view = {
    buses: [
      { frames: [{ signals: [{ values: "states" }, { values: { 0: "A" } }] }],
        devices: [{ frames: [{ signals: [{ values: "faults", flags: [{ values: "states" }] }] }] }, {}] },
    ],
  };

  it("finds a table of the map with its rows, line and users", () => {
    expect(namedTable({ data: own, text }, view, "states")).toEqual(
      { values: { 0: "OFF", 1: "ON" }, file: null, line: 3, users: 2 });
  });

  it("finds a table of an included file by its text", () => {
    const parts = { "common.yaml": "mapcan: 2\npart_of: m.yaml\nvalue_tables:\n  faults:\n    0: OK\n" };
    expect(namedTable({ data: own, text, parts }, view, "faults")).toEqual(
      { values: null, file: "common.yaml", line: 4, users: 1 });
  });

  it("answers without a place for a table that is nowhere", () => {
    expect(namedTable({ data: null, text: "" }, null, "nope")).toEqual({ values: null, file: null, line: null, users: 0 });
  });
});
