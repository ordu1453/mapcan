// Structural edits of the tree: the operations sent to the server and what is selected after them.

import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Op, Path, ResolvedFrame } from "../src/types";

const fake = vi.hoisted(() => ({
  data: {} as any,
  applied: [] as Op[][],
  selected: [] as Path[],
  toasts: [] as Array<[string, string | undefined]>,
  ok: true,
  answer: null as string | null,
  frames: new Map<string, unknown>(),
  included: null as string | null,
  deviceFiles: [] as unknown[],
}));

vi.mock("../src/store", () => ({
  store: {
    get state() { return { data: fake.data, readonly: false, resolved: { language: "ru", frames: [...fake.frames.values()] } }; },
    meta: { user: { name: "Ann", github: "ann" } },
    selected: [] as Path[],
    selectedVia: null as string | null,
    selectedSender: null,
    renameRequest: null as Path | null,
    busy: false,
    tab: "editor",
  },
  actions: {
    apply: async (ops: Op[]) => { fake.applied.push(ops); return fake.ok; },
    select: (p: Path) => { fake.selected.push(p); },
    addDeviceFile: async (...args: unknown[]) => { fake.deviceFiles.push(args); return fake.ok; },
  },
  askText: async () => fake.answer,
  includedPath: () => fake.included,
  lang: { get value() { return fake.data?.document?.language ?? "ru"; } },
  resolvedFrames: { get value() { return fake.frames; } },
  viewData: { get value() { return fake.data; } },
  toast: (text: string, kind?: string) => { fake.toasts.push([text, kind]); },
}));

import * as E from "../src/edit";
import { store } from "../src/store";

const BUS: Path = ["buses", 0];
const DEV: Path = ["buses", 0, "devices", 0];
const FRAME: Path = [...DEV, "frames", 0];

function canopenMap() {
  return {
    document: { title: "Map", language: "ru", version: "1.0.0", history: [{ version: "1.0.0", changes: [] }] },
    buses: [{
      name: "can1", title: "Шина 1", protocol: "canopen",
      devices: [
        {
          name: "bms", title: "Устройство 1", node_id: 1,
          frames: [{
            name: "status", canopen: "pdo_tx1", length: 2, receivers: ["panel"],
            signals: [{ name: "soc", encoding: "number", byte: 0, byte_length: 1,
              flags: [{ name: "low", bit: 0 }, { name: "pair", bit: 1, bit_length: 2 }] }],
            sdo: [{ name: "ex", command: 0x2f, index: 0x2001, subindex: 3 }],
          }],
        },
        { name: "panel", title: "Устройство 2", node_id: 2, frames: [{ name: "cmd", canopen: "pdo_rx1", sender: "bms" }] },
      ],
    }],
  };
}

function resolved(path: Path, length: number, occupied: number[][], extra: Partial<ResolvedFrame> = {}) {
  fake.frames.set(path.join("/"), {
    path, name: "status", can_id: 0x181, extended: false, length, type: "pdo_tx1", direction: "tx",
    device: "bms", sender: "bms", receivers: [], signals: occupied.map((o) => ({ occupied: o })), ...extra,
  });
}

beforeEach(() => {
  fake.data = canopenMap();
  fake.applied = [];
  fake.selected = [];
  fake.toasts = [];
  fake.ok = true;
  fake.answer = null;
  fake.frames = new Map();
  fake.included = null;
  fake.deviceFiles = [];
  store.renameRequest = null;
  store.selected = [];
  store.selectedVia = null;
});

describe("adding nodes", () => {
  it("adds a bus with a free name and title, and asks for its title", async () => {
    store.selected = ["buses", 1];
    expect(await E.addBus()).toBe(true);
    expect(fake.applied).toEqual([[{ op: "insert", path: ["buses"],
      value: { name: "bus", title: "Шина 2", protocol: "can", devices: [] } }]]);
    expect(fake.selected).toEqual([["buses", 1]]);
    expect(store.renameRequest).toEqual(["buses", 1]);
  });

  it("gives a CANopen device the first free node ID, a J1939 one a free address, a CAN one neither", async () => {
    await E.addDevice(BUS);
    expect(fake.applied[0][0]).toEqual({ op: "insert", path: [...BUS, "devices"],
      value: { name: "device", title: "Устройство 3", node_id: 3, frames: [] } });
    fake.data.buses[0].protocol = "j1939";
    fake.data.buses[0].devices[0].address = 0x10;
    fake.data.document.language = "en";
    await E.addDevice(BUS);
    expect(fake.applied[1][0]).toMatchObject({ value: { name: "device", title: "Device 3", address: 0x11 } });
    fake.data.buses[0].protocol = "can";
    await E.addDevice(BUS);
    expect(fake.applied[2][0]).not.toHaveProperty("value.node_id");
    expect(fake.applied[2][0]).not.toHaveProperty("value.address");
  });

  it("adds a device in a file of its own", async () => {
    expect(await E.addDeviceInFile(BUS)).toBe(false);          // cancelled
    fake.answer = "  devices/dev.yaml ";
    expect(await E.addDeviceInFile(BUS)).toBe(true);
    expect(fake.deviceFiles).toEqual([[BUS, expect.objectContaining({ name: "device", node_id: 3 }), "devices/dev.yaml"]]);
    expect(fake.selected).toEqual([[...BUS, "devices", 2]]);
  });

  it("adds a frame of a free PDO type to a CANopen device, without selecting it", async () => {
    await E.addFrame(DEV);
    expect(fake.applied[0][0]).toEqual({ op: "insert", path: [...DEV, "frames"],
      value: { name: "bms_frame", canopen: "pdo_tx2", length: 8, cycle_ms: 100, signals: [] } });
    expect(fake.selected).toEqual([]);
  });

  it("gives a frame of a bus a free ID, and a J1939 frame a free proprietary PGN", async () => {
    resolved(FRAME, 8, [], { can_id: 0x100 });
    await E.addFrame(BUS);
    expect(fake.applied[0][0]).toMatchObject({ path: [...BUS, "frames"], value: { name: "frame", id: 0x101 } });
    fake.data.buses[0].protocol = "j1939";
    fake.data.buses[0].devices[0].frames[0].pgn = 0xff00;
    await E.addFrame(DEV);
    expect(fake.applied[1][0]).toMatchObject({ value: { name: "bms_frame", pgn: 0xff01, priority: 6, length: 8 } });
  });

  it("places a new signal in a free byte", async () => {
    resolved(FRAME, 2, [[0, 1, 2, 3, 4, 5, 6, 7]]);
    expect(await E.addSignal(FRAME)).toBe(true);
    expect(fake.applied[0]).toEqual([
      { op: "insert", path: [...FRAME, "signals"], value: { name: "signal", encoding: "number" } },
      { op: "set_layout", path: [...FRAME, "signals", 1], start_bit: 8, bit_length: 8 },
    ]);
    expect(fake.selected).toEqual([[...FRAME, "signals", 1]]);
  });

  it("extends a full frame by a byte, or a CAN FD frame to the next length", async () => {
    const full = Array.from({ length: 16 }, (_, i) => i);
    resolved(FRAME, 2, [full]);
    await E.addSignal(FRAME, undefined, "soc");
    expect(fake.applied[0]).toContainEqual({ op: "set", path: [...FRAME, "length"], value: 3 });
    expect(fake.applied[0][0]).toMatchObject({ value: { name: "soc_2" } });
    resolved(FRAME, 8, [Array.from({ length: 64 }, (_, i) => i)]);
    fake.data.buses[0].fd = true;
    await E.addSignal(FRAME);
    expect(fake.applied[1]).toContainEqual({ op: "set", path: [...FRAME, "length"], value: 12 });
  });

  it("takes the free bits of a frame of the maximum length, or refuses", async () => {
    resolved(FRAME, 8, [Array.from({ length: 64 }, (_, i) => i).filter((b) => b < 10 || b > 12)]);
    await E.addSignal(FRAME);
    expect(fake.applied[0]).toContainEqual({ op: "set_layout", path: [...FRAME, "signals", 1], start_bit: 10, bit_length: 3 });
    resolved(FRAME, 8, [Array.from({ length: 64 }, (_, i) => i)]);
    expect(await E.addSignal(FRAME)).toBe(false);
    expect(fake.toasts[0][0]).toMatch(/No free bits/);
    // A position given by the bit grid is taken as it is
    await E.addSignal(FRAME, { start_bit: 4, bit_length: 2 });
    expect(fake.applied[1]).toContainEqual({ op: "set_layout", path: [...FRAME, "signals", 1], start_bit: 4, bit_length: 2 });
  });

  it("adds a flag at the first free bit and an SDO exchange after the last one", async () => {
    const sig = [...FRAME, "signals", 0];
    await E.addFlag(sig);
    expect(fake.applied[0][0]).toEqual({ op: "insert", path: [...sig, "flags"], value: { bit: 3, name: "flag" } });
    await E.addSdo(FRAME);
    expect(fake.applied[1][0]).toEqual({ op: "insert", path: [...FRAME, "sdo"],
      value: { name: "exchange", command: 0x2f, index: 0x2001, subindex: 4 } });
  });

  it("adds a revision first in the history, with the next version and the author", async () => {
    await E.addRevision();
    const [insert, ...rest] = fake.applied[0];
    expect(insert).toMatchObject({ op: "insert", path: ["document", "history"], index: 0,
      value: { version: "1.0.1", author: "Ann", github: "ann", changes: [] } });
    // The version written in the document is that of the history: removed, it comes from the history now
    expect(rest).toEqual([{ op: "remove", path: ["document", "version"] }]);
    expect(fake.selected).toEqual([["document", "history", 0]]);
    // A version written ahead of the history is the new entry's
    fake.data.document.version = "2.0.0";
    await E.addRevision();
    expect(fake.applied[1][0]).toMatchObject({ value: { version: "2.0.0" } });
  });
});

describe("versions", () => {
  it("reads the document's version", () => {
    expect(E.documentVersion({ version: "1.2.0" })).toBe("1.2.0");
    expect(E.documentVersion({ history: [{ version: "0.3.0" }] })).toBe("0.3.0");
    expect(E.documentVersion(undefined)).toBe("0.1");
    expect(E.removeDocumentVersion({ version: "1", date: "2026-01-01" }).map((o) => o.path)).toEqual(
      [["document", "version"], ["document", "date"]]);
    expect(E.removeDocumentVersion({})).toEqual([]);
  });
});

describe("renaming", () => {
  it("renames a device with the senders and receivers that name it", async () => {
    expect(await E.renameNode(DEV, " battery ")).toBeNull();
    expect(fake.applied[0]).toEqual([
      { op: "set", path: [...DEV, "name"], value: "battery" },
      { op: "set", path: [...BUS, "devices", 1, "frames", 0, "sender"], value: "battery" },
    ]);
    await E.renameNode([...BUS, "devices", 1], "dash");
    expect(fake.applied[1]).toContainEqual({ op: "set", path: [...FRAME, "receivers"], value: ["dash"] });
  });

  it("refuses an empty or taken name, and does nothing for the same one", async () => {
    expect(await E.renameNode(DEV, "  ")).toMatch(/empty/);
    expect(await E.renameNode(DEV, "panel")).toMatch(/already taken/);
    expect(await E.renameNode([...BUS, "devices", 1, "frames", 0], "status")).toMatch(/already taken/);
    expect(await E.renameNode(DEV, "bms")).toBeNull();
    expect(fake.applied).toEqual([]);
    fake.ok = false;
    expect(await E.renameNode(DEV, "new")).toMatch(/Could not rename/);
  });

  it("knows what can be renamed and removed", () => {
    expect(E.canRename(DEV)).toBe(true);
    expect(E.canRename(["document"])).toBe(false);
    expect(E.canRemove(FRAME)).toBe(true);
    expect(E.canRemove(["document"])).toBe(false);
  });

  it("sets the title in the document language", async () => {
    expect(await E.setTitle(DEV, "Battery")).toBeNull();
    expect(fake.applied[0]).toEqual([{ op: "set", path: [...DEV, "title"], value: "Battery" }]);
    fake.data.buses[0].devices[0].title = { ru: "Батарея", en: "Battery" };
    await E.setTitle(DEV, "АКБ");
    expect(fake.applied[1]).toEqual([{ op: "set", path: [...DEV, "title", "ru"], value: "АКБ" }]);
    expect(await E.setTitle(DEV, "Батарея")).toBeNull();
    expect(fake.applied).toHaveLength(2);
    expect(await E.setTitle(DEV, "")).toMatch(/cannot be empty/);
    // A frame may go without a title: an empty one removes it, and none to remove changes nothing
    expect(await E.setTitle(FRAME, "")).toBeNull();
    expect(fake.applied).toHaveLength(2);
    fake.data.buses[0].devices[0].frames[0].title = "Status";
    await E.setTitle(FRAME, "");
    expect(fake.applied[2]).toEqual([{ op: "set", path: [...FRAME, "title"], value: null }]);
  });

  it("sets or removes the abbreviation", async () => {
    expect(await E.setShort(DEV, "")).toBeNull();
    expect(fake.applied).toEqual([]);
    await E.setShort(DEV, " BMS ");
    expect(fake.applied[0]).toEqual([{ op: "set", path: [...DEV, "short"], value: "BMS" }]);
  });
});

describe("receiving and removing", () => {
  it("turns the copy of a frame into a receiver of the original", async () => {
    const rx: Path = [...BUS, "devices", 1, "frames", 0];
    expect(await E.receiveFrame(rx, FRAME)).toBe(true);
    // panel is already a receiver: only its copy goes
    expect(fake.applied[0]).toEqual([{ op: "remove", path: rx }]);
    fake.data.buses[0].devices[0].frames[0].receivers = undefined;
    await E.receiveFrame(rx, FRAME);
    expect(fake.applied[1][0]).toEqual({ op: "set", path: [...FRAME, "receivers"], value: ["panel"] });
    expect(fake.toasts.at(-1)?.[1]).toBe("info");
    expect(await E.receiveFrame(rx, [...FRAME.slice(0, -1), 9])).toBe(false);
  });

  it("stops receiving a frame, removing the list when it is empty", async () => {
    await E.stopReceiving(FRAME, "panel");
    expect(fake.applied[0]).toEqual([{ op: "remove", path: [...FRAME, "receivers"] }]);
    fake.data.buses[0].devices[0].frames[0].receivers = ["panel", "x"];
    await E.stopReceiving(FRAME, "panel");
    expect(fake.applied[1]).toEqual([{ op: "set", path: [...FRAME, "receivers"], value: ["x"] }]);
  });

  it("selects the parent after removing a node", async () => {
    await E.removeNode(FRAME);
    expect(fake.selected).toEqual([DEV]);
    await E.removeNode(BUS);
    await E.removeNode(["document", "history", 0]);
    expect(fake.selected.slice(1)).toEqual([["document"], ["document", "history"]]);
  });

  it("removes a frame selected through a link from the receivers instead", async () => {
    store.selected = FRAME;
    store.selectedVia = "panel";
    await E.removeSelected();
    expect(fake.applied[0]).toEqual([{ op: "remove", path: [...FRAME, "receivers"] }]);
    expect(fake.selected).toEqual([[...BUS, "devices", 1]]);
    store.selectedVia = null;
    await E.removeSelected();
    expect(fake.applied[1]).toEqual([{ op: "remove", path: FRAME }]);
  });
});

describe("duplicating", () => {
  it("copies a node after it with a free name, without the identifiers", async () => {
    await E.duplicateNode(DEV);
    const [insert] = fake.applied[0];
    expect(insert).toMatchObject({ op: "insert", path: [...BUS, "devices"], index: 1, value: { name: "bms_copy" } });
    expect(insert).not.toHaveProperty("value.node_id");
    fake.data.buses[0].devices[0].frames[0].id = 0x100;
    await E.duplicateNode(FRAME);
    expect(fake.applied[1][0]).toMatchObject({ index: 1, value: { name: "status_copy" } });
    expect(fake.applied[1][0]).not.toHaveProperty("value.id");
    expect(fake.selected).toEqual([[...BUS, "devices", 1], [...DEV, "frames", 1]]);
  });

  it("copies a revision as it is", async () => {
    await E.duplicateNode(["document", "history", 0]);
    expect(fake.applied[0]).toEqual([{ op: "insert", path: ["document", "history"], index: 1,
      value: { version: "1.0.0", changes: [] } }]);
  });
});
