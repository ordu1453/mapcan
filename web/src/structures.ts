import { getAt, isCanopen, type Data } from "./model";
import type { Path } from "./types";

export interface ValueStructure {
  title?: string;
  kind?: "enum" | "bitmask";
  enabled?: boolean;
  values?: Record<string, string | { name: string; description?: string }>;
  locked?: number[];
  excluded?: number[];
}

// States of the device (device_state of its status byte, not the NMT states) and generic EMCY classes/codes of
// CiA 301. Profile-specific codes are user additions.
// Source of the codes: can-cia.org/can-knowledge/special-function-protocols.
export const TEMPLATES: Record<string, ValueStructure> = {
  states: { title: "States", kind: "enum", values: {
    0: "INIT", 1: "DISABLED", 2: "READY", 3: "STARTING", 4: "STANDBY", 5: "RUN", 6: "STOPPING", 7: "FAULT",
  } },
  eec: { title: "EEC", kind: "enum", values: {
    0x0000: "ERROR_RESET", 0x1000: "GENERIC_ERROR", 0x2000: "CURRENT", 0x2100: "CURRENT_INPUT",
    0x2200: "CURRENT_INTERNAL", 0x2300: "CURRENT_OUTPUT", 0x3000: "VOLTAGE", 0x3100: "VOLTAGE_MAINS",
    0x3200: "VOLTAGE_INTERNAL", 0x3300: "VOLTAGE_OUTPUT", 0x4000: "TEMPERATURE", 0x4100: "TEMPERATURE_AMBIENT",
    0x4200: "TEMPERATURE_DEVICE", 0x5000: "HARDWARE", 0x6000: "SOFTWARE", 0x6100: "SOFTWARE_INTERNAL",
    0x6200: "SOFTWARE_USER", 0x6300: "DATA_SET", 0x7000: "ADDITIONAL_MODULES", 0x8000: "MONITORING",
    0x8100: "COMMUNICATION", 0x8110: "CAN_OVERRUN", 0x8120: "CAN_ERROR_PASSIVE", 0x8130: "LIFE_GUARD_OR_HEARTBEAT",
    0x8140: "BUS_OFF_RECOVERY", 0x8150: "CAN_ID_COLLISION", 0x8200: "PROTOCOL", 0x8210: "PDO_LENGTH",
    0x8220: "PDO_LENGTH_EXCEEDED", 0x8230: "DAM_MPDO_DESTINATION", 0x8240: "UNEXPECTED_SYNC_LENGTH",
    0x8250: "RPDO_TIMEOUT", 0x9000: "EXTERNAL_ERROR", 0xf000: "ADDITIONAL_FUNCTIONS", 0xff00: "DEVICE_SPECIFIC",
  } },
};

export function structureNames(data: Data, owner: Path, includeDisabled = false): string[] {
  const bus = getAt(data, owner.slice(0, 2));
  const own = getAt(data, owner);
  const names = new Set([...isCanopen(bus) ? Object.keys(TEMPLATES) : [],
    ...Object.keys(bus?.structures ?? {}), ...Object.keys(own?.structures ?? {}),
    ...(owner.length === 2 ? (bus?.devices ?? []).flatMap((d: Data) => Object.keys(d?.structures ?? {})) : [])]);
  return [...names].filter((name) => includeDisabled || effectiveStructure(data, owner, name) !== null);
}

export function effectiveStructure(data: Data, owner: Path, name: string): ValueStructure | null {
  const bus = getAt(data, owner.slice(0, 2));
  const base: ValueStructure | undefined = bus?.structures?.[name]?.enabled === false ? undefined : bus?.structures?.[name];
  const own: ValueStructure | undefined = owner.length === 4 ? getAt(data, owner)?.structures?.[name] : undefined;
  const locked = base?.locked ?? [];
  const template = isCanopen(bus) ? TEMPLATES[name] : undefined;
  if (own?.enabled === false && !locked.length) return null;
  if (owner.length === 2 && bus?.structures?.[name]?.enabled === false) return null;
  const deviceExample = owner.length === 2 ? (bus?.devices ?? []).find((d: Data) => d?.structures?.[name]?.enabled !== false && d?.structures?.[name])?.structures[name] : undefined;
  if (!base && !own && !template && !deviceExample) return null;
  // A template offers choices; it does not select them automatically.
  const values = { ...(base?.values ?? {}) };
  if (own) {
    for (const key of Object.keys(values)) {
      if (!locked.includes(Number(key)) && (own.enabled === false || own.excluded?.includes(Number(key)))) delete values[key];
    }
    if (own.enabled !== false) for (const [key, value] of Object.entries(own.values ?? {})) {
      if (!locked.includes(Number(key)) && !own.excluded?.includes(Number(key))) values[key] = value;
    }
  }
  return { title: deviceExample?.title, ...template, ...base, ...own, kind: base?.kind ?? own?.kind ?? template?.kind ?? deviceExample?.kind ?? "enum", values, locked };
}

export function structureOwner(path: Path): Path {
  return path[2] === "devices" ? path.slice(0, 4) : path.slice(0, 2);
}
