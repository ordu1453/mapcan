// Labels of nodes in the tree: titles for people instead of identifiers, links to received frames.

import { describe, expect, it } from "vitest";
import { buildTree, deviceLabel, displayName, includedFile, pathKey, viewOf, type TreeNode } from "../src/model";
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
  path, name: "", can_id: 0x181, extended: false, dlc: 8, type: "pdo_tx1", direction: "tx",
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
    expect(bms.children[0].label).toBe("Состояния");
    expect(find(bms, "signal").map((s) => s.label)).toEqual(["Заряд", "temp"]);
    // search by identifier keeps working
    expect(bms.children[0].search).toContain("bms_status");
  });

  it("a received frame is a link under the receiver with the sender in its label", () => {
    const [bms, panel] = bus.children;
    expect(bms.children.filter((c) => c.from !== undefined)).toEqual([]);
    const link = panel.children[0];
    expect(link.label).toBe("BMS · Состояния");
    expect(link.path).toEqual(status.path);
    expect(link.receiver).toBe("panel");
    expect(link.dir).toBe("rx");
    expect(link.key).not.toBe(pathKey(status.path));
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
});
