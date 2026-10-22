// Labels of nodes in the tree: titles for people instead of identifiers, links to received frames.

import { describe, expect, it } from "vitest";
import { buildTree, deviceLabel, displayName, includedFile, isLink, localPath, mergedPath, pathKey, viewOf, type TreeNode }
  from "../src/model";
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
  path, name: "", can_id: 0x181, extended: false, length: 8, type: "pdo_tx1", direction: "tx",
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

  it("a bus shows its estimated load from the server (#131)", () => {
    const loads = new Map([[pathKey(["buses", 0]), { load: "≥12%", note: "Estimated bus load: ≥12%" }]]);
    const [, loaded] = buildTree(data, new Map(), "ru", [], loads);
    expect(loaded.sub).toBe("≥12%");
    expect(loaded.subHint).toBe("Estimated bus load: ≥12%");
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
    expect(panel.children[0].label).toBe("BMS · Команда");
    expect(isLink(panel.children[0])).toBe(false);
  });

  it("the sender has a link to it, named after the device it is described at", () => {
    const link = bms.children[0];
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
