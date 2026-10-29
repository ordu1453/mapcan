// Help of form fields: the description of the field in the format's JSON Schema, which is generated from the
// pydantic model (src/mapcan/model.py). Texts are English; the web editor shows them through t().

import schema from "../../../schema/mapcan.schema.json";
import { N_ } from "./i18n";
import type { FieldDef, FormKind } from "./spec";

interface SchemaDef {
  properties?: Record<string, { description?: string }>;
}

const DEFS = (schema as { $defs: Record<string, SchemaDef> }).$defs;

/** Definition in the schema of each node kind (and of the SDO value, the "value.<field>" keys). */
export const SCHEMA_DEFS: Record<FormKind | "sdo.value", string> = {
  document: "Document", revision: "HistoryEntry", bus: "Bus", device: "Device", frame: "Frame", signal: "Signal",
  flag: "Flag", sdo: "SdoExchange", "sdo.value": "SdoValue",
};

/** Fields of a node kind in the schema; the SDO value's fields as "value.<field>". */
export function schemaFields(kind: FormKind): string[] {
  const own = Object.keys(DEFS[SCHEMA_DEFS[kind]]?.properties ?? {});
  if (kind !== "sdo") return own;
  return [...own.filter((k) => k !== "value"), ...Object.keys(DEFS.SdoValue.properties ?? {}).map((k) => `value.${k}`)];
}

/** Description of a field in the schema. */
export function describe(kind: FormKind, key: string): string | undefined {
  const [def, field] = kind === "sdo" && key.startsWith("value.") ? [SCHEMA_DEFS["sdo.value"], key.slice(6)]
    : [SCHEMA_DEFS[kind], key];
  return DEFS[def]?.properties?.[field]?.description;
}

/** Help of a form field: its own text, else the description of the field in the format. */
export const fieldHelp = (kind: FormKind, f: FieldDef): string | undefined => f.help ?? describe(kind, f.key);

/** Help of the web editor's controls that are not fields of the format. */
export const UI_HELP = {
  source: N_("If the device receives a frame that is already described at another device, pick it: the device is added to that frame's receivers and the copy here is removed. A frame is described once, at its sender."),
  mux: N_("A multiplexed frame carries different signals depending on the value of its selector. Choose the selector here; each switched signal names the selector values it is sent at."),
  mode: N_("When the frame is sent: cyclically at a set period, on event (when data changes), both (every period and at once on an event) or on request."),
};
