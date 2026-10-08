// Подписи узлов в дереве: названия для людей вместо идентификаторов, ссылки на принимаемые кадры.

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

describe("подписи", () => {
  it("название вместо идентификатора, у устройства — с сокращением", () => {
    expect(displayName(data.buses[0].devices[0], "ru")).toBe("BMS · Система управления батареей");
    expect(displayName(data.buses[0].devices[0], "en")).toBe("BMS · Battery management");
    expect(displayName({ name: "panel" }, "ru")).toBe("panel");
    expect(deviceLabel(data.buses[0].devices[0], "ru")).toBe("BMS");
    expect(deviceLabel({ name: "x", title: "Икс" }, "ru")).toBe("Икс");
  });

  it("дерево: шина без идентификатора справа, кадры и сигналы — по названию, без него — по имени", () => {
    expect(bus.label).toBe("Шина 1");
    expect(bus.sub).toBe("");
    const [bms, panel] = bus.children;
    expect(bms.label).toBe("BMS · Система управления батареей");
    expect(panel.label).toBe("panel");
    expect(bms.children[0].label).toBe("Состояния");
    expect(find(bms, "signal").map((s) => s.label)).toEqual(["Заряд", "temp"]);
    // поиск по идентификатору продолжает работать
    expect(bms.children[0].search).toContain("bms_status");
  });

  it("принимаемый кадр — ссылка под получателем с отправителем в подписи", () => {
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

describe("подключённые файлы", () => {
  const included = [{ path: ["buses", 0, "devices", 1], file: "common.yaml" }];
  const view = viewOf({ data: { ...data, buses: [] }, included_buses: data.buses });

  it("дерево строится вместе с подключёнными шинами", () => {
    expect(view.buses).toBe(data.buses);
    expect(viewOf({ data, included_buses: null })).toBe(data);
  });

  it("узлы подключённого файла помечены файлом, корень — отдельно", () => {
    const [, bus] = buildTree(view, new Map(), "ru", included);
    const [bms, panel] = bus.children;
    expect(bms.file).toBeUndefined();
    expect(panel.file).toBe("common.yaml");
    expect(panel.fileRoot).toBe(true);
    expect(includedFile(included, ["buses", 0, "devices", 1, "frames", 0])).toBe("common.yaml");
    expect(includedFile(included, ["buses", 0, "devices", 0])).toBeNull();
  });
});
