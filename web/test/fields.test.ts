// Какие поля форм видны в зависимости от протокола, типа и направления кадра.

import { describe, expect, it } from "vitest";
import { FIELDS, parseInput, parseInteger, ParseError, type FieldCtx } from "../src/fields";
import type { NodeKind } from "../src/model";

/** Ключи полей, видимых по правилам when (NodeEditor ещё показывает заполненные поля и поля с ошибками). */
function visible(kind: NodeKind, node: unknown, ctx: FieldCtx): string[] {
  return FIELDS[kind].filter((f) => !f.when || f.when(node, ctx)).map((f) => f.key);
}

function options(key: string, ctx: FieldCtx): Array<[string, string]> {
  return FIELDS.frame.find((f) => f.key === key)!.optionsFor!(ctx);
}

const canopen = (extra: Partial<FieldCtx> = {}): FieldCtx => ({ protocol: "canopen", devices: ["pump"], owner: "pump", ...extra });

describe("кадр", () => {
  it("RX-кадр CANopen на шине из одного устройства: ни направления, ни отправителя, ни получателей", () => {
    const keys = visible("frame", { type: "pdo_rx1" }, canopen({ direction: "rx" }));
    expect(keys).not.toContain("direction");
    expect(keys).not.toContain("sender");
    expect(keys).not.toContain("receivers");
    expect(keys).not.toContain("extended");
    expect(keys).toContain("dlc");
  });

  it("RX-кадр без типа: направление и отправитель есть, получателей нет", () => {
    const keys = visible("frame", {}, canopen({ devices: ["pump", "master"], direction: "rx" }));
    expect(keys).toEqual(expect.arrayContaining(["direction", "sender", "extended"]));
    expect(keys).not.toContain("receivers");
  });

  it("TX-кадр: получатели есть, отправителя нет", () => {
    const keys = visible("frame", { type: "pdo_tx1" }, canopen({ devices: ["pump", "master"], direction: "tx" }));
    expect(keys).toContain("receivers");
    expect(keys).not.toContain("sender");
  });

  it("кадр шины: без направления, с отправителем и получателями", () => {
    const keys = visible("frame", { type: "sync" }, canopen({ devices: ["pump", "master"], owner: null }));
    expect(keys).not.toContain("direction");
    expect(keys).toEqual(expect.arrayContaining(["sender", "receivers"]));
  });

  it("DLC служебного кадра CANopen задан типом; у SYNC — на выбор 0 или 1", () => {
    expect(visible("frame", { type: "nmt" }, canopen())).not.toContain("dlc");
    expect(visible("frame", { type: "heartbeat" }, canopen())).not.toContain("dlc");
    expect(visible("frame", { type: "sync" }, canopen())).toContain("dlc");
    expect(visible("frame", { type: "nmt" }, { protocol: "can" })).toContain("dlc");
  });

  it("вне CANopen нет типа; у J1939 — PGN и нет 29-битного флага", () => {
    const j = visible("frame", {}, { protocol: "j1939", devices: [], owner: "ecu" });
    expect(j).not.toContain("type");
    expect(j).not.toContain("extended");
    expect(j).toEqual(expect.arrayContaining(["pgn", "priority"]));
    const c = visible("frame", {}, { protocol: "can", devices: [], owner: "dev" });
    expect(c).not.toContain("type");
    expect(c).toContain("extended");
  });

  it("отправитель и получатели: без владельца и отправителя, с подписями устройств", () => {
    const ctx = canopen({
      devices: ["pump", "master", "panel"], sender: "master",
      deviceLabels: { pump: "Насос", master: "MCU", panel: "Панель" },
    });
    expect(options("sender", ctx)).toEqual([["", "вне карты"], ["master", "MCU"], ["panel", "Панель"]]);
    expect(options("receivers", ctx)).toEqual([["panel", "Панель"]]);
  });
});

describe("прочие узлы", () => {
  it("адрес устройства — по протоколу", () => {
    expect(visible("device", {}, { protocol: "canopen" })).toContain("node_id");
    expect(visible("device", {}, { protocol: "j1939" })).toContain("address");
    expect(visible("device", {}, { protocol: "can" })).not.toContain("node_id");
  });

  it("название шины и устройства обязательно, у кадра и сигнала — нет", () => {
    const req = (kind: NodeKind, key: string) => FIELDS[kind].find((f) => f.key === key)?.required;
    expect(req("bus", "title")).toBe(true);
    expect(req("device", "title")).toBe(true);
    expect(req("frame", "title")).toBeFalsy();
    expect(req("signal", "title")).toBeFalsy();
  });

  it("поля значения SDO появляются, когда значение задано", () => {
    expect(visible("sdo", {}, { protocol: "canopen" })).not.toContain("value.unit");
    expect(visible("sdo", { value: { name: "speed" } }, { protocol: "canopen" })).toContain("value.unit");
  });

  it("поля сигнала — по его типу", () => {
    expect(visible("signal", {}, { protocol: "can", encoding: "scaled" })).toEqual(expect.arrayContaining(["factor", "unit"]));
    expect(visible("signal", {}, { protocol: "can", encoding: "enum" })).not.toContain("factor");
    expect(visible("signal", {}, { protocol: "canopen", encoding: "raw", bitLength: 16 })).toContain("byte_order");
    expect(visible("signal", {}, { protocol: "can", encoding: "raw", bitLength: 16 })).toContain("byte_order");
    expect(visible("signal", {}, { protocol: "can", encoding: "raw", bitLength: 8 })).not.toContain("byte_order");
    expect(visible("signal", {}, { protocol: "can", encoding: "bytes", bitLength: 16 })).not.toContain("byte_order");
  });
});

describe("разбор ввода", () => {
  it("целые и шестнадцатеричные", () => {
    expect(parseInteger("0x1A")).toBe(26);
    expect(parseInput("hex", "26")).toBe(26);
    expect(parseInput("hex", "0x1a")).toBe(26);
    // Опечатки не превращаются молча в другое число
    for (const raw of ["0x12 34", "0x1G", "-5", "0x", "1.5", "0x20000000000001"]) {
      expect(() => parseInput("hex", raw)).toThrow(ParseError);
    }
    expect(parseInput("float", "1,5")).toBe(1.5);
    expect(parseInput("intlist", "1, 2")).toEqual([1, 2]);
    expect(parseInput("text", "  ")).toBeNull();
    expect(() => parseInteger("1.5")).toThrow(ParseError);
  });
});
