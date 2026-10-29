<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { hex, rangeLabel } from "../bits";
import { addBus, addDevice, addDeviceInFile, addFrame, addSdo, addSignal, canRename, duplicateNode, receiveFrame, removeNode, removeSelected,
  renameNode, stopReceiving } from "../edit";
import { applies, CANOPEN_DLC, describe, encodingChangeOps, fieldHelp, FORMS, isRequired, optionsOf, parseInteger, ParseError,
  placeholderOf, UI_HELP, type FieldDef, type FormContext, type FormKind } from "@mapcan/forms";
import { canonicalPath, deviceLabel, displayName, getAt, HISTORY_PATH, isCanopen, namedTable, nodeKind, OBJECTS, ownerPath, pathKey, samePath,
  startsWith, txt } from "../model";
import { actions, askUser, includedPath, lang, resolvedFrames, selectedFramePath, selectedResolvedFrame, store, toast,
  viewData } from "../store";
import type { Diagnostic, Op, Path } from "../types";
import BitGrid from "./BitGrid.vue";
import DocumentRequisites from "./DocumentRequisites.vue";
import FieldInput from "./FieldInput.vue";
import FlagsTable from "./FlagsTable.vue";
import HelpTip from "./HelpTip.vue";
import HistoryEditor from "./HistoryEditor.vue";
import InlineRename from "./InlineRename.vue";
import ObjectsTable from "./ObjectsTable.vue";
import ValueTable from "./ValueTable.vue";
import { N_, t } from "../i18n";

const KIND_LABEL: Record<string, string> = {
  document: N_("Document"), history: "", revision: N_("History entry"), bus: N_("Bus"),
  device: N_("Device"), objects: N_("Object dictionary"), frame: N_("Frame"), signal: N_("Signal"), flag: N_("Flag"),
  sdo: N_("SDO exchange"), unknown: "",
};

const path = computed<Path>(() => store.selected);
const kind = computed(() => nodeKind(path.value));
// Together with the included files (include): their nodes are edited here, the edits go to their own file
const data = computed(() => viewData.value);
const node = computed(() => getAt(data.value, kind.value === "document" ? ["document"] : path.value));
const includedFile = computed(() => includedPath(path.value));
// bus.frame.signal.flag: how dashboards, plots and logs refer to the node (docs/format.md)
const refPath = computed(() => canonicalPath(data.value, path.value));

async function copyRefPath() {
  try {
    await navigator.clipboard.writeText(refPath.value!);
    toast(t("Copied {path}", { path: refPath.value }), "info");
  } catch {
    toast(t("Could not copy to the clipboard"));
  }
}
const readonly = computed(() => !!store.state?.readonly);
const diags = computed(() => store.state?.diagnostics ?? []);
// A signal of a CANopen frame is a dictionary object (CiA 301): the editor calls it so (#151)
const canopen = computed(() => path.value[0] === "buses" && isCanopen(getAt(data.value, path.value.slice(0, 2))));
const kindLabel = computed(() => (kind.value === "signal" && canopen.value ? N_("Object") : KIND_LABEL[kind.value]));

// What the form's conditions know about the node (see FormContext in packages/forms/src/spec.ts)
const formCtx = computed<FormContext>(() => {
  const s = kind.value === "signal" ? rsignal.value : null;
  const bus = path.value[0] === "buses" ? getAt(data.value, path.value.slice(0, 2)) : null;
  const frame = kind.value === "frame" ? rframe.value : undefined;
  const form = FORMS[kind.value as FormKind] ?? [];
  return {
    values: Object.fromEntries(form.flatMap((sec) => sec.fields).map((f) => [f.key, fieldValue(f)])),
    protocol: bus ? bus.protocol ?? "canopen" : "",
    fd: !!bus?.fd,
    busBrs: typeof bus?.brs === "boolean" ? bus.brs : null,
    owner: frame?.device ?? null,
    devices: (bus?.devices ?? []).filter((d: any) => d?.name)
      .map((d: any) => ({ name: d.name, label: deviceLabel(d, lang.value) })),
    signalEncoding: s?.encoding ?? null,
    bitLength: s?.bit_length ?? null,
    // The selector may be a field of another bit field; the bit field of the selector is not switched itself
    hasSelector: !!s && !!rframe.value?.signals.some((x) => !samePath(x.path, s.path)
      && (x.multiplexer || x.flags.some((f) => f.multiplexer))) && !s.flags.some((f) => f.multiplexer),
    frames: kind.value === "device" ? node.value?.frames ?? [] : undefined,
    hasHistory: kind.value === "document" && (node.value?.history ?? []).length > 0,
  };
});
// Sections of the form with the fields that apply. A field with a value, an error or a warning is shown even if it
// does not apply to the node's type or protocol, otherwise the problem could not be found. Position and
// transmission fields have their own controls above the form.
// Controls of the editor itself in a section: the signal's position, the frame's transmission
const customOf = (title: string | undefined) =>
  kind.value === "signal" && title === "Position" ? "position" as const
    : kind.value === "frame" && title === "Timing" ? "transmission" as const : null;
const sections = computed(() => (FORMS[kind.value as FormKind] ?? [])
  .map((sec) => ({
    title: sec.title,
    custom: customOf(sec.title),
    fields: sec.fields
      .filter((f) => !f.layout && (applies(f, formCtx.value) || fieldValue(f) != null
        || fieldDiags(f).some((d) => d.level !== "info")))
      .map((f) => ({ ...f, help: fieldHelp(kind.value as FormKind, f), isRequired: isRequired(f, formCtx.value),
        shownOptions: optionsOf(f, formCtx.value) })),
  }))
  .filter((sec) => sec.fields.length || (sec.custom === "position" ? !!rsignal.value : !!sec.custom)));
const fields = computed(() => sections.value.flatMap((sec) => sec.fields));
// The receiving device a frame of another device is shown under
const viaLabel = computed(() =>
  formCtx.value.devices.find((d) => d.name === store.selectedVia)?.label ?? store.selectedVia);
const hasRequired = computed(() => fields.value.some((f) => f.isRequired));

function fieldValue(def: FieldDef) {
  return getAt(node.value, def.key.split("."));
}

function shownValue(def: FieldDef) {
  return fieldValue(def);
}

function fieldPath(def: FieldDef): Path {
  return [...path.value, ...def.key.split(".")];
}

function fieldDiags(def: FieldDef) {
  const p = fieldPath(def);
  return diags.value.filter((d) => startsWith(d.node, p));
}

function placeholderFor(def: FieldDef): string {
  // The computed CAN ID of the frame is known here
  if (kind.value === "frame" && def.key === "id" && rframe.value) {
    return hex(rframe.value.can_id, rframe.value.extended ? 8 : 3) + " " + t("(computed)");
  }
  return placeholderOf(def, formCtx.value);
}

function commit(def: FieldDef, value: unknown, at?: Path) {
  // The selection moved before the field lost focus: the value goes to the node the field belongs to
  const owner = at ? at.slice(0, at.length - def.key.split(".").length) : null;
  if (owner && !samePath(owner, path.value)) {
    if (def.key === "name") void renameNode(owner, String(value ?? "")).then((err) => { if (err) toast(err); });
    else void actions.apply([{ op: "set", path: at!, value }]);
    return;
  }
  // The name goes through renameNode: a check that it is free, and the frames' receivers updated when a device is renamed
  if (def.key === "name" && canRename(path.value)) {
    void renameNode(path.value, String(value ?? "")).then((err) => { if (err) toast(err); });
    return;
  }
  // Changing the CANopen type: a written length not allowed for the new type is removed, the type's length applies
  const allowed = kind.value === "frame" && def.key === "canopen" ? CANOPEN_DLC[String(value ?? "")] : undefined;
  const length = node.value?.length;
  // encoding is required for an SDO value: a new value is created with encoding: number right away
  // Without an identifier an SDO exchange has no value: the value mapping is removed as a whole
  if (kind.value === "sdo" && def.key === "value.name" && (node.value?.value == null || !value)) {
    if (value) void actions.apply([{ op: "set", path: [...path.value, "value"], value: { name: value, encoding: "number", bit_length: 32 } }]);
    else if (node.value?.value != null) void actions.apply([{ op: "remove", path: [...path.value, "value"] }]);
    return;
  }
  // A new encoding starts with its defaults: the fields of the former one are removed in the same step
  if (kind.value === "signal" && def.key === "encoding" && value && value !== node.value?.encoding) {
    void actions.apply(encodingChangeOps(path.value, node.value ?? {}, String(value)));
    return;
  }
  // A device named as the sender does not receive the frame: it leaves the receivers
  const rec = node.value?.receivers;
  const leaves = kind.value === "frame" && def.key === "sender" && Array.isArray(rec) && rec.includes(value);
  const rest = leaves ? rec.filter((r: unknown) => r !== value) : [];
  void actions.apply([{ op: "set", path: [...path.value, ...def.key.split(".")], value },
    ...(allowed && length != null && !allowed.includes(length) ? [{ op: "remove" as const, path: [...path.value, "length"] }] : []),
    ...(leaves ? [rest.length ? { op: "set" as const, path: [...path.value, "receivers"], value: rest }
      : { op: "remove" as const, path: [...path.value, "receivers"] }] : [])]);
}

// The heading has the title for people (with the abbreviation for a device) and the identifier; each part is edited with a double click
const renaming = ref<"name" | "short" | "title" | null>(null);
const nodeTitle = computed(() => (["bus", "device", "frame", "signal"].includes(kind.value) ? txt(node.value?.title, lang.value) : ""));
watch(() => pathKey(path.value), () => { renaming.value = null; });

// Keys whose messages are shown at the form's fields and in the tables (values, flags, position, transmission)
const SHOWN_ELSEWHERE = ["values", "flags", "start_bit", "bit_length", "byte", "bit", "byte_length",
  "trigger", "cycle_ms", "signals", "frames", "devices", "sdo", "history"];

/** Messages of the node not shown at any field: on the node itself or on a field that is not in the form. */
const ownDiags = computed(() => {
  const shown = new Set([...fields.value.map((f) => f.key.split(".")[0]), ...SHOWN_ELSEWHERE]);
  const n = path.value.length;
  return diags.value.filter((d) => {
    if (d.level === "info") return false;
    if (kind.value === "document" && d.node.length === 0) return true;
    if (samePath(d.node, path.value)) return !layoutDiags.value.includes(d);
    return samePath(ownerPath(d.node), path.value) && !shown.has(String(d.node[n]));
  });
});

// ------------------------------------------------------------------ breadcrumbs

const crumbs = computed(() => {
  const out: Array<{ label: string; path: Path }> = [];
  const p = path.value;
  for (let n = 2; n <= p.length; n++) {
    const sub = p.slice(0, n);
    const k = nodeKind(sub);
    if (k === "unknown" || k === "document") continue;
    const nd = getAt(data.value, sub);
    const label = k === "history" ? t("Revision history") : k === "revision" ? nd?.version : k === "objects" ? t("Objects")
      : ["bus", "device", "frame", "signal"].includes(k) ? displayName(nd, lang.value) : nd?.name;
    out.push({ label, path: sub });
  }
  return out;
});

// ------------------------------------------------------------------ frame

const rframe = computed(() => selectedResolvedFrame.value);
const framePath = computed(() => selectedFramePath.value);
const frameData = computed(() => (framePath.value ? getAt(data.value, framePath.value) : null));

const muxValue = computed({
  get: () => (framePath.value ? store.muxView[pathKey(framePath.value)] ?? null : null),
  set: (v: number | null) => {
    if (framePath.value) store.muxView[pathKey(framePath.value)] = v;
  },
});

// Transmission mode: with a cycle_ms period cyclic (with trigger: event also on event), otherwise trigger
const txMode = computed(() => (node.value?.cycle_ms != null
  ? (node.value?.trigger === "event" ? "cyclic_event" : "cyclic") : node.value?.trigger ?? ""));
const txCyclic = computed(() => txMode.value === "cyclic" || txMode.value === "cyclic_event");
const txCycle = computed(() => node.value?.cycle_ms ?? null);

function setMode(e: Event) {
  const m = (e.target as HTMLSelectElement).value;
  const p = path.value;
  const ops = [];
  const cyclic = m === "cyclic" || m === "cyclic_event";
  const trigger = m === "cyclic_event" ? "event" : cyclic ? "" : m;
  if (!cyclic && node.value?.cycle_ms != null) ops.push({ op: "remove" as const, path: [...p, "cycle_ms"] });
  if (!trigger && node.value?.trigger != null) ops.push({ op: "remove" as const, path: [...p, "trigger"] });
  if (cyclic) ops.push({ op: "set" as const, path: [...p, "cycle_ms"], value: txCycle.value ?? 100 });
  if (trigger) ops.push({ op: "set" as const, path: [...p, "trigger"], value: trigger });
  void actions.apply(ops);
}

// Errors of number input in the position and period fields; reset when going to another node
const MAX_FRAME_BITS = 64 * 8;
const inputErrors = ref<Record<string, string>>({});
watch(() => pathKey(path.value), () => { inputErrors.value = {}; });

/** An integer from an input in the range [min, max]; on error shows a message, puts the previous value back and gives null. */
function readInt(e: Event, key: string, min: number, max: number, old: number | null | undefined): number | null {
  const el = e.target as HTMLInputElement;
  let msg = "";
  let n: number | null = null;
  try {
    n = parseInteger(el.value);
    if (n < min || n > max) msg = t("“{raw}” must be between {min} and {max}", { raw: el.value.trim(), min, max });
  } catch (err) {
    msg = err instanceof ParseError ? err.message : String(err);
  }
  inputErrors.value = { ...inputErrors.value, [key]: msg };
  if (!msg) return n;
  el.value = old == null ? "" : String(old);
  return null;
}

// Messages about the transmission mode: on the period field if it is visible, otherwise on the mode select
const txDiags = computed(() =>
  kind.value === "frame"
    ? diags.value.filter((d) => startsWith(d.node, [...path.value, "trigger"]) || startsWith(d.node, [...path.value, "cycle_ms"]))
    : [],
);

function setCycle(e: Event) {
  const n = readInt(e, "cycle_ms", 1, 2 ** 31 - 1, txCycle.value);
  if (n === null) return;
  void actions.apply([{ op: "set", path: [...path.value, "cycle_ms"], value: n }]);
}

// An RX frame of a device may be a frame that is already described at its sender: it can be picked instead of the own copy
const rxSources = computed(() => {
  const f = rframe.value;
  if (kind.value !== "frame" || !f?.device || f.direction !== "rx") return [];
  return (store.state?.resolved?.frames ?? [])
    .filter((o) => o.path[1] === path.value[1] && o.sender && o.sender !== f.device && o.device !== f.device)
    // Frames with the same CAN ID first: most likely that is the frame described twice
    .sort((a, b) => Number(b.can_id === f.can_id) - Number(a.can_id === f.can_id)
      || a.sender!.localeCompare(b.sender!) || a.name.localeCompare(b.name))
    .map((o) => ({
      key: pathKey(o.path), path: o.path,
      label: `${o.sender} · ${o.name}` + (o.can_id != null ? ` (${hex(o.can_id, o.extended ? 8 : 3)})` : ""),
    }));
});

/** The original frame for an rx-duplicate message: the same CAN ID, described at the sender. */
const rxTwin = computed(() => {
  const f = rframe.value;
  if (!f || f.can_id == null) return null;
  return rxSources.value.find((o) => resolvedFrames.value.get(o.key)?.can_id === f.can_id) ?? null;
});

function setSource(e: Event) {
  const el = e.target as HTMLSelectElement;
  const src = rxSources.value.find((o) => o.key === el.value);
  el.value = "";
  if (src) void receiveFrame(path.value, src.path);
}

// ------------------------------------------------------------------ Esc: up to the node above

// Esc in a signal, a flag or an SDO exchange goes back to its frame (a flag to its signal), as a breadcrumb does.
// A field being typed in is written first (it loses focus); Esc handled by a dialog, the help, a list of units or
// a drag of the bit layout does not leave the node.
const root = ref<HTMLElement | null>(null);
function onEscape(e: KeyboardEvent) {
  if (e.key !== "Escape" || e.defaultPrevented || !["signal", "flag", "sdo"].includes(kind.value)) return;
  if (document.querySelector(".modal-backdrop") || !root.value?.offsetParent) return;
  const target = e.target as HTMLElement | null;
  if (target?.closest(".yaml-editor")) return;
  if (target?.matches("input, textarea, select")) target.blur();
  void actions.select(path.value.slice(0, -2));
}
onMounted(() => window.addEventListener("keydown", onEscape));
onBeforeUnmount(() => window.removeEventListener("keydown", onEscape));

// ------------------------------------------------------------------ signal

const rsignal = computed(() => {
  if (kind.value !== "signal" && kind.value !== "flag") return null;
  const sp = kind.value === "flag" ? path.value.slice(0, -2) : path.value;
  return rframe.value?.signals.find((s) => samePath(s.path, sp)) ?? null;
});

const signalPath = computed(() => (kind.value === "flag" ? path.value.slice(0, -2) : path.value));

function setLayout(field: "start_bit" | "bit_length", e: Event) {
  const s = rsignal.value;
  if (!s) return;
  const n = field === "start_bit"
    ? readInt(e, field, 0, MAX_FRAME_BITS - 1, s.start_bit)
    : readInt(e, field, 1, 64, s.bit_length);
  if (n === null) return;
  const start = field === "start_bit" ? n : s.start_bit;
  const length = field === "bit_length" ? n : s.bit_length;
  void actions.apply([{ op: "set_layout", path: s.path, start_bit: start, bit_length: length }]);
}

// Messages about the signal's position: overlaps and exceeding the DLC (on the whole signal) and messages of the start/length fields
const LAYOUT_CODES = ["bit-overlap", "signal-out-of-frame"];
const layoutDiags = computed(() => {
  if (kind.value !== "signal") return [];
  const sp = signalPath.value;
  return diags.value.filter((d) => (samePath(d.node, sp) && LAYOUT_CODES.includes(d.code))
    || ["start_bit", "bit_length", "byte", "byte_length", "bit"].some((k) => startsWith(d.node, [...sp, k])));
});
const wholeDiags = computed(() => layoutDiags.value.filter((d) => samePath(d.node, signalPath.value)));
const lengthDiags = computed(() => layoutDiags.value.filter((d) =>
  ["bit_length", "byte_length"].includes(String(d.node[signalPath.value.length]))));
const startDiags = computed(() => layoutDiags.value.filter((d) => !wholeDiags.value.includes(d) && !lengthDiags.value.includes(d)));

function worstLevel(ds: Diagnostic[]): string {
  return ds.some((d) => d.level === "error") ? "error" : ds.some((d) => d.level === "warning") ? "warning" : "";
}

const showValues = computed(() => {
  const n = node.value;
  if (!n) return false;
  if (kind.value === "flag") return true;
  if (kind.value !== "signal") return false;
  return n.values != null || (rsignal.value?.encoding ?? n.encoding) === "enum";
});
// Values from a named table of value_tables (#143): shown read-only, the table is edited in the YAML tab. A table
// of an included file is not in the map's data: its values come from the resolved signal then (without descriptions).
const namedValues = computed(() => (typeof node.value?.values === "string" && store.state
  ? namedTable(store.state, data.value, node.value.values) : null));
const namedRows = computed(() => namedValues.value?.values
  ?? (kind.value === "signal" && rsignal.value
    ? Object.fromEntries(rsignal.value.values.map((v) => [String(v.value), v.name])) : undefined));

function openNamedTable() {
  const r = namedValues.value;
  if (r) void actions.openYaml(r.file, r.line);
}

// The encoding as written counts too: a bit field without flags may not parse yet
const showFlags = computed(() => kind.value === "signal"
  && (node.value?.flags != null || (rsignal.value?.encoding ?? node.value?.encoding) === "bitfield"));

// ------------------------------------------------------------------ lists of child nodes

const childFrames = computed(() => {
  if (kind.value !== "device" && kind.value !== "bus") return [];
  return (node.value?.frames ?? []).map((f: any, i: number) => {
    const p = [...path.value, "frames", i];
    const rf = resolvedFrames.value.get(pathKey(p));
    return { path: p, name: f?.name ?? "—", label: displayName(f, lang.value), id: rf ? hex(rf.can_id) : "—", type: f?.canopen ?? "raw",
      desc: txt(f?.description, lang.value), n: rf?.signals.length ?? 0 };
  });
});

/** Dictionary object of a signal as "0x2100:01" (index and subindex); "—" without an index. */
function odLabel(s: any): string {
  if (typeof s?.index !== "number") return "—";
  return `${hex(s.index, 4)}:${(s.subindex ?? 0).toString(16).toUpperCase().padStart(2, "0")}`;
}

const frameSignals = computed(() => {
  if (kind.value !== "frame" || !rframe.value) return [];
  return rframe.value.signals.map((s) => ({
    s, label: s.synthetic ? s.name : displayName(getAt(data.value, s.path), lang.value),
    desc: txt(getAt(data.value, s.path)?.description, lang.value),
    bits: rangeLabel(Math.min(...s.occupied), Math.max(...s.occupied)),
    od: odLabel(s.synthetic ? null : getAt(data.value, s.path)),
  }));
});

// An empty item "- " in the YAML draft is null: show a row without fields
const devices = computed(() => (kind.value === "bus" && Array.isArray(node.value?.devices)
  ? node.value.devices.map((d: any) => (d && typeof d === "object" ? d : {})) : []));

/** Who sends the frame and who receives it, as links to the devices (also when it is described at its receiver). */
const route = computed(() => {
  const f = rframe.value;
  if (kind.value !== "frame" || !f) return null;
  const devs: any[] = getAt(data.value, path.value.slice(0, 2))?.devices ?? [];
  const peer = (name: string) => {
    const i = devs.findIndex((d) => d?.name === name);
    return { name, label: i >= 0 ? deviceLabel(devs[i], lang.value) : name, path: i >= 0 ? [...path.value.slice(0, 2), "devices", i] : null };
  };
  return { sender: f.sender ? peer(f.sender) : null, receivers: f.receivers.map(peer) };
});

/** Exchange of the device, computed from the senders and receivers of all frames of the bus. */
const exchange = computed(() => {
  if (kind.value !== "device") return null;
  const name = node.value?.name;
  const bus = getAt(data.value, path.value.slice(0, 2));
  const label = (n: string | null) => {
    const d = n ? (bus?.devices ?? []).find((x: any) => x?.name === n) : null;
    return !n ? "—" : d ? deviceLabel(d, lang.value) : n;
  };
  const onBus = (store.state?.resolved?.frames ?? []).filter((f) => f.path[1] === path.value[1]);
  const row = (f: (typeof onBus)[number], peer: string) => ({
    path: f.path, name: f.name, label: displayName(getAt(data.value, f.path), lang.value), peer,
    id: hex(f.can_id, f.extended ? 8 : 3),
    desc: txt(getAt(data.value, f.path)?.description, lang.value),
  });
  return {
    // The own device can be removed from the receivers of another's frame; an own RX frame can only be deleted
    receives: onBus.filter((f) => f.receivers.includes(name))
      .map((f) => ({ ...row(f, label(f.sender)), foreign: f.device !== name })),
    sends: onBus.filter((f) => f.sender === name && f.device !== name)
      .map((f) => row(f, f.device ? label(f.device) : t("bus frame"))),
  };
});

const buses = computed(() => {
  if (kind.value !== "document") return [];
  return (data.value?.buses ?? []).map((b: any, i: number) => ({
    path: ["buses", i], name: b?.name ?? "—", label: displayName(b, lang.value), protocol: b?.protocol ?? "can",
    devices: b?.devices?.length ?? 0,
    frames: (b?.frames?.length ?? 0) + (b?.devices ?? []).reduce((n: number, d: any) => n + (d?.frames?.length ?? 0), 0),
  }));
});
// SDO exchanges only for CANopen frames
const canAddSdo = computed(() => kind.value === "frame" && (data.value?.buses?.[Number(path.value[1])]?.protocol ?? "canopen") === "canopen"
  && (node.value?.sdo != null || ["sdo_tx", "sdo_rx"].includes(node.value?.canopen)));
const isListItem = computed(() => typeof path.value[path.value.length - 1] === "number" && path.value.length > 1);

function onCreate(start: number, length: number) {
  if (framePath.value) void addSignal(framePath.value, { start_bit: start, bit_length: length });
}
function onLayout(p: Path, start: number, length: number) {
  void actions.apply([{ op: "set_layout", path: p, start_bit: start, bit_length: length }]);
}
/** A flag moved or resized in the bit layout; a length of 1 is not written (#150). */
function onFlag(p: Path, bit: number, length: number) {
  const written = getAt(data.value, [...p, "bit_length"]) != null;
  void actions.apply([{ op: "set", path: [...p, "bit"], value: bit },
    ...(length > 1 ? [{ op: "set" as const, path: [...p, "bit_length"], value: length }]
      : written ? [{ op: "remove" as const, path: [...p, "bit_length"] }] : [])]);
}

// ------------------------------------------------------------------ multiplexing of the frame (#149)

// The selector is a signal or a field of a bit field that has a value table, and is not switched by a selector
// itself; the selector written in the map is offered even if it is neither
const muxControl = computed(() => {
  if (kind.value !== "frame" || !rframe.value) return null;
  const signals: any[] = Array.isArray(node.value?.signals) ? node.value.signals : [];
  const options: { key: string; label: string; path: Path }[] = [];
  let selector = "";
  for (const s of rframe.value.signals) {
    if (s.synthetic) continue;
    const label = displayName(getAt(data.value, s.path), lang.value);
    if (s.multiplexer) selector = pathKey(s.path);
    if (s.multiplexer || (s.mux === null && s.values.length)) options.push({ key: pathKey(s.path), label, path: s.path });
    s.flags.forEach((f, i) => {
      const fp = [...s.path, "flags", i];
      if (f.multiplexer) selector = pathKey(fp);
      if (f.multiplexer || (s.mux === null && f.values.length)) options.push({ key: pathKey(fp), label: `${label} · ${f.name}`, path: fp });
    });
  }
  return { selector, options, switched: signals.filter((x) => x?.mux != null).length };
});

async function setSelector(e: Event) {
  const el = e.target as HTMLSelectElement;
  const key = el.value;
  const signals: any[] = Array.isArray(node.value?.signals) ? node.value.signals : [];
  const at = (i: number) => [...path.value, "signals", i];
  const ops: Op[] = [];
  // The former selector, a signal or a field, stops being one
  signals.forEach((x, i) => {
    if (x?.multiplexer && pathKey(at(i)) !== key) ops.push({ op: "remove", path: [...at(i), "multiplexer"] });
    (Array.isArray(x?.flags) ? x.flags : []).forEach((f: any, j: number) => {
      const fp = [...at(i), "flags", j];
      if (f?.multiplexer && pathKey(fp) !== key) ops.push({ op: "remove", path: [...fp, "multiplexer"] });
    });
  });
  if (key) {
    const chosen = muxControl.value?.options.find((o) => o.key === key);
    if (chosen) ops.push({ op: "set", path: [...chosen.path, "multiplexer"], value: true });
  } else {
    // Without a selector the selector values of the signals mean nothing: they go too, after a question
    const switched = signals.map((x, i) => (x?.mux != null ? i : -1)).filter((i) => i >= 0);
    if (switched.length) {
      const names = switched.map((i) => signals[i].name).join(", ");
      const answer = await askUser(t("Turn multiplexing off"),
        t("{names}: sent at certain selector values (mux). Turning multiplexing off removes these selector values.", { names }),
        [{ label: t("Cancel"), value: "cancel" }, { label: t("Turn off"), value: "off", kind: "danger" }]);
      if (answer !== "off") {
        el.value = muxControl.value?.selector ?? "";
        return;
      }
      for (const i of switched) ops.push({ op: "remove", path: [...at(i), "mux"] });
    }
  }
  if (framePath.value) store.muxView[pathKey(framePath.value)] = null;
  if (ops.length) void actions.apply(ops);
}
</script>

<template>
  <div v-if="store.state?.data" ref="root" class="node-editor">
    <header class="ne-head">
      <div>
        <div class="crumbs">
          <a @click="actions.select(['document'])">{{ txt(data?.document?.title, lang) || t("Document") }}</a>
          <template v-for="c in crumbs" :key="c.path.join('/')">
            <span class="sep">›</span><a @click="actions.select(c.path)">{{ c.label }}</a>
          </template>
        </div>
        <h2>
          <span v-if="kindLabel" class="kind-badge">{{ t(kindLabel) }}</span>
          <InlineRename v-if="renaming" :path="path" :field="renaming"
                        :value="renaming === 'title' ? nodeTitle : node?.[renaming] ?? ''" @done="renaming = null" />
          <template v-else-if="canRename(path)">
            <template v-if="kind === 'device' && node?.short">
              <span class="renamable" :title="t('Double-click to edit the abbreviation')"
                    @dblclick="renaming = 'short'">{{ node.short }}</span><span class="muted">·</span>
            </template>
            <span v-if="nodeTitle" class="renamable" :title="t('Double-click to edit the title')"
                  @dblclick="renaming = 'title'">{{ nodeTitle }}</span>
            <span class="renamable mono" :class="{ secondary: !!nodeTitle }" :title="t('Double-click to edit the identifier')"
                  @dblclick="renaming = 'name'">{{ node?.name }}</span>
          </template>
          <template v-else>
            {{ kind === "document" ? txt(node?.title, lang) : kind === "history" ? t("Revision history")
              : kind === "revision" ? node?.version : kind === "objects" ? displayName(getAt(data, path.slice(0, -1)), lang)
                : node?.name }}
          </template>
          <span v-if="kind === 'frame' && rframe" class="mono id-badge">{{ hex(rframe.can_id, rframe.extended ? 8 : 3) }}</span>
        </h2>
      </div>
      <div class="ne-actions">
        <button v-if="refPath" class="icon" :title="t('Copy path {path}', { path: refPath })"
                :aria-label="t('Copy path {path}', { path: refPath })" @click="copyRefPath">⎘</button>
        <template v-if="isListItem && !readonly && !store.selectedSender">
          <button class="icon" :title="t('Duplicate')" @click="duplicateNode(path)">⧉</button>
          <button class="icon danger" :title="store.selectedVia ? t('Stop receiving (remove from receivers)') : t('Delete (Del)')"
                  @click="removeSelected()">✕</button>
        </template>
      </div>
    </header>

    <div v-if="includedFile" class="banner info">
      🔗 {{ t("The node is described in the included file {file}: edits go to that file, and Save writes it too.",
              { file: includedFile }) }}
      <button class="small fix" @click="actions.openYaml(includedFile)">{{ t("Open the YAML of {file}", { file: includedFile }) }}</button>
    </div>
    <div v-for="d in ownDiags" :key="d.code + d.message" class="banner" :class="d.level">
      <b>{{ d.code }}</b>: {{ d.message }}
      <button v-if="d.code === 'rx-duplicate' && rxTwin && !readonly" class="small fix"
              @click="receiveFrame(path, rxTwin.path)">{{ t("Receive frame {frame}", { frame: rxTwin.label }) }}</button>
    </div>
    <p v-if="route" class="frame-route">
      <span class="muted">{{ t("Sender") }}:</span>
      <a v-if="route.sender?.path" @click="actions.select(route.sender.path)">{{ route.sender.label }}</a>
      <span v-else-if="route.sender">{{ route.sender.label }}</span>
      <span v-else class="muted">{{ t("outside the map") }}</span>
      <span class="muted">→ {{ t("Receivers") }}:</span>
      <template v-for="(r, i) in route.receivers" :key="r.name">
        <span v-if="i" class="muted">, </span>
        <a v-if="r.path" @click="actions.select(r.path)">{{ r.label }}</a><span v-else>{{ r.label }}</span>
      </template>
      <span v-if="!route.receivers.length" class="muted">—</span>
    </p>
    <div v-if="kind === 'frame' && store.selectedVia" class="banner info">
      {{ t("The frame is described at its sender; {device} receives it. Delete or ✕ stops receiving it and keeps the frame.",
           { device: viaLabel }) }}
    </div>

    <!-- Bit map for a frame, a signal, a flag -->
    <section v-if="rframe && rframe.length > 0 && ['frame', 'signal', 'flag', 'sdo'].includes(kind)" class="card">
      <!-- The "Bits" tab at the right end of the heading, over the row of bit numbers like the tab of a folder -->
      <h3 class="layout-head">{{ t("Frame layout") }} <span class="muted">{{ frameData?.name }} · {{ t("{n} bytes", { n: rframe.length }) }}</span>
        <span class="bitgrid-tab">{{ t("Bits") }}</span></h3>
      <BitGrid :frame="rframe" :selected="path" :palette="store.state.palette" :readonly="readonly" :objects="canopen"
               v-model:mux-value="muxValue"
               @select="actions.select" @create="onCreate" @layout="onLayout" @flag="onFlag" />
    </section>

    <ObjectsTable v-if="kind === 'objects'" :key="pathKey(path)" :device="path.slice(0, -1)" />

    <section v-if="kind !== 'history' && kind !== 'objects'" class="card">
      <h3>{{ t("Properties") }} <span v-if="hasRequired" class="muted req-note"><span class="req">*</span> {{ t("— required field") }}</span></h3>
      <!-- One row per section: its name on the left, its fields in a grid on the right (short fields take one
           column, the others two, texts the whole row) -->
      <div class="form-rows">
        <div v-for="(sec, i) in sections" :key="sec.title ?? ''" class="form-row">
          <h4 class="form-section">{{ t(sec.title ?? "General") }}</h4>
          <div class="form-grid" :class="{ pair: sec.fields.length === 2 && sec.fields.every((f) => f.wide) }">
            <!-- RX frame: pick a frame of another device instead of it -->
            <label v-if="i === 0 && rxSources.length && !readonly" class="field">
              <span class="field-label"><HelpTip :text="UI_HELP.source" />{{ t("Frame of another device") }}</span>
              <select value="" @change="setSource">
                <option value="">{{ t("none — the frame is described here") }}</option>
                <option v-for="o in rxSources" :key="o.key" :value="o.key">{{ o.label }}</option>
              </select>
              <span class="field-hint">{{ t("the device receives a frame described at its sender") }}</span>
            </label>

            <!-- position of the signal -->
            <template v-if="sec.custom === 'position' && rsignal">
              <label class="field half" :class="worstLevel([...wholeDiags, ...startDiags])">
                <span class="field-label"><HelpTip :text="describe('signal', 'start_bit') ?? ''" />{{ t("Start bit (LSB)") }}</span>
                <input class="mono" :value="rsignal.start_bit" :readonly="readonly || rsignal.synthetic" @change="setLayout('start_bit', $event)" />
                <span v-if="inputErrors.start_bit" class="field-msg error">{{ inputErrors.start_bit }}</span>
                <span v-for="d in startDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
              </label>
              <label class="field half" :class="worstLevel([...wholeDiags, ...lengthDiags])">
                <span class="field-label"><HelpTip :text="describe('signal', 'bit_length') ?? ''" />{{ t("Length, bits") }}</span>
                <input class="mono" :value="rsignal.bit_length" :readonly="readonly || rsignal.synthetic" @change="setLayout('bit_length', $event)" />
                <span v-if="inputErrors.bit_length" class="field-msg error">{{ inputErrors.bit_length }}</span>
                <span v-for="d in [...wholeDiags, ...lengthDiags]" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
              </label>
              <div class="field position-hint">
                <span class="field-hint">
                  {{ t("bytes {bytes}, bits {bits}", {
                    bytes: rangeLabel(Math.floor(Math.min(...rsignal.occupied) / 8), Math.floor(Math.max(...rsignal.occupied) / 8)),
                    bits: rangeLabel(Math.min(...rsignal.occupied), Math.max(...rsignal.occupied)) }) }}
                </span>
              </div>
            </template>

            <!-- transmission mode of the frame -->
            <template v-if="sec.custom === 'transmission'">
              <label class="field" :class="txCyclic ? '' : worstLevel(txDiags)">
                <span class="field-label"><HelpTip :text="UI_HELP.mode" />{{ t("Transmission") }}</span>
                <select :value="txMode" :disabled="readonly" @change="setMode">
                  <option value="">{{ t("not set") }}</option>
                  <option value="cyclic">{{ t("cyclic") }}</option>
                  <option value="cyclic_event">{{ t("cyclic and on event") }}</option>
                  <option value="event">{{ t("on event") }}</option>
                  <option value="on_request">{{ t("on request") }}</option>
                </select>
                <template v-if="!txCyclic">
                  <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
                </template>
              </label>
              <label v-if="txCyclic" class="field half" :class="worstLevel(txDiags)">
                <span class="field-label"><HelpTip :text="describe('frame', 'cycle_ms') ?? ''" />{{ t("Period, ms") }}</span>
                <input class="mono" :value="txCycle ?? ''" :readonly="readonly" @change="setCycle" />
                <span v-if="inputErrors.cycle_ms" class="field-msg error">{{ inputErrors.cycle_ms }}</span>
                <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
              </label>
            </template>

            <FieldInput v-for="def in sec.fields" :key="path.join('/') + def.key" :def="def" :value="shownValue(def)"
                        :options="def.shownOptions" :path="fieldPath(def)" :required="def.isRequired"
                        :diags="fieldDiags(def)" :readonly="readonly"
                        :placeholder="placeholderFor(def)"
                        @commit="(v, at) => commit(def, v, at)" />
          </div>
        </div>
        <!-- Multiplexing of the frame: the selector among its signals (#149); each switched signal names its
             selector values in its own form -->
        <div v-if="muxControl" class="form-row">
          <h4 class="form-section">{{ t("Multiplexing") }}</h4>
          <div class="form-grid">
            <label class="field">
              <span class="field-label"><HelpTip :text="UI_HELP.mux" />{{ t("Selector (mux)") }}</span>
              <select :value="muxControl.selector" :disabled="readonly" @change="setSelector">
                <option value="">{{ t("off — no multiplexing") }}</option>
                <option v-for="o in muxControl.options" :key="o.key" :value="o.key">{{ o.label }}</option>
              </select>
              <span v-if="muxControl.selector" class="field-hint">
                {{ t("sent at certain selector values: {n}", { n: muxControl.switched }) }}</span>
              <span v-else-if="!muxControl.options.length" class="field-hint">
                {{ t("the selector is a signal or a bit field's field with a value table") }}</span>
            </label>
          </div>
        </div>
      </div>
    </section>

    <DocumentRequisites v-if="kind === 'document'" />
    <HistoryEditor v-if="kind === 'history' || kind === 'revision'" :path="path" />

    <section v-if="namedValues" class="card">
      <ValueTable :path="path" :values="namedRows" :hex="node?.value_format === 'hex'" readonly :diags="[]"
                  :title="t('Values from table “{name}”', { name: node.values })" />
      <p class="muted">
        {{ t("A table of value_tables, used by signals and flags: {n}. It is edited in the YAML tab.",
             { n: namedValues.users }) }}
        <button v-if="namedValues.line !== null" class="small" @click="openNamedTable">{{ t("Open in YAML") }}</button>
      </p>
    </section>
    <ValueTable v-else-if="showValues" class="card" :path="path" :values="node?.values" :hex="node?.value_format === 'hex'"
                :readonly="readonly" :diags="diags" />
    <FlagsTable v-if="showFlags" class="card" :path="path" :flags="node?.flags" :readonly="readonly" :diags="diags"
                :field-length="rsignal?.bit_length ?? null" />

    <!-- Signals of the frame -->
    <section v-if="kind === 'frame'" class="card">
      <h3>
        {{ canopen ? t("Objects") : t("Signals") }} <span class="muted">{{ frameSignals.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button v-if="canAddSdo" class="small" @click="addSdo(path)">+ {{ t("SDO exchange") }}</button>
          <button class="small" @click="addSignal(path)">+ {{ canopen ? t("Object") : t("Signal") }}</button>
        </span>
      </h3>
      <table v-if="frameSignals.length" class="list">
        <thead><tr><th></th><th>{{ canopen ? t("Object") : t("Signal") }}</th><th v-if="canopen">{{ t("Index") }}</th>
          <th>{{ t("Bits") }}</th><th>{{ t("Type") }}</th><th>{{ t("Description") }}</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in frameSignals" :key="r.s.name" class="clickable"
              @click="actions.select(r.s.synthetic ? path : r.s.path)">
            <td><span class="swatch" :style="{ background: store.state.palette[i % store.state.palette.length] }" /></td>
            <td>{{ r.label }}<span v-if="r.label !== r.s.name" class="ident">{{ r.s.name }}</span><span
              v-if="r.s.synthetic" class="muted"> (SDO)</span></td>
            <td v-if="canopen" class="mono">{{ r.od }}</td>
            <td class="mono">{{ r.bits }}</td>
            <td>{{ r.s.encoding }}<span v-if="r.s.mux" class="muted"> · mux {{ r.s.mux.join(", ") }}</span></td>
            <td>{{ r.desc }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ canopen ? t("No objects yet. Drag across the bits in the layout above or click “+ Object”.")
        : t("No signals yet. Drag across the bits in the layout above or click “+ Signal”.") }}</p>
    </section>

    <!-- Frames of the device / bus -->
    <section v-if="kind === 'bus' || kind === 'device'" class="card">
      <h3>
        {{ t("Frames") }} <span class="muted">{{ childFrames.length }}</span>
        <span class="card-actions">
          <button v-if="kind === 'device' && canopen" class="small"
                  @click="actions.select([...path, OBJECTS])">{{ t("Object dictionary") }}</button>
          <button v-if="!readonly" class="small" @click="addFrame(path)">+ {{ t("Frame") }}</button>
        </span>
      </h3>
      <table v-if="childFrames.length" class="list">
        <thead><tr><th>ID</th><th>{{ t("Frame") }}</th><th>{{ t("Type") }}</th><th>{{ canopen ? t("Objects") : t("Signals") }}</th>
          <th>{{ t("Description") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="f in childFrames" :key="f.name" class="clickable" @click="actions.select(f.path)">
            <td class="mono">{{ f.id }}</td><td>{{ f.label }}<span v-if="f.label !== f.name" class="ident">{{ f.name }}</span></td><td>{{ f.type }}</td>
            <td>{{ f.n }}</td><td>{{ f.desc }}</td>
            <td v-if="!readonly" class="act"><button class="icon danger" :title="t('Delete')" @click.stop="removeNode(f.path)">✕</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("No frames.") }}</p>
    </section>

    <!-- Exchange of the device: what it receives and which frames of others it sends -->
    <section v-if="exchange" class="card">
      <h3>{{ t("Receives") }} <span class="muted">{{ exchange.receives.length }}</span></h3>
      <table v-if="exchange.receives.length" class="list">
        <thead><tr><th>ID</th><th>{{ t("Frame") }}</th><th>{{ t("Sender") }}</th><th>{{ t("Description") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="f in exchange.receives" :key="f.name" class="clickable" @click="actions.select(f.path)">
            <td class="mono">{{ f.id }}</td><td>{{ f.label }}<span v-if="f.label !== f.name" class="ident">{{ f.name }}</span></td>
            <td>{{ f.peer }}</td><td>{{ f.desc }}</td>
            <td v-if="!readonly" class="act">
              <button v-if="f.foreign" class="icon danger" :title="t('Stop receiving (remove from receivers)')"
                      @click.stop="stopReceiving(f.path, node.name)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("The device is not a receiver of any frame.") }}</p>
      <template v-if="exchange.sends.length">
        <h3 class="sub">{{ t("Transmits frames of other devices") }} <span class="muted">{{ exchange.sends.length }}</span></h3>
        <table class="list">
          <thead><tr><th>ID</th><th>{{ t("Frame") }}</th><th>{{ t("Device") }}</th><th>{{ t("Description") }}</th></tr></thead>
          <tbody>
            <tr v-for="f in exchange.sends" :key="f.name" class="clickable" @click="actions.select(f.path)">
              <td class="mono">{{ f.id }}</td><td>{{ f.label }}<span v-if="f.label !== f.name" class="ident">{{ f.name }}</span></td>
              <td>{{ f.peer }}</td><td>{{ f.desc }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </section>

    <section v-if="kind === 'bus'" class="card">
      <h3>
        {{ t("Devices") }} <span class="muted">{{ devices.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addDevice(path)">+ {{ t("Device") }}</button>
          <button class="small" :title="t('A device in a file of its own, which the map includes')"
                  @click="addDeviceInFile(path)">+ {{ t("Device in a new file") }}</button>
        </span>
      </h3>
      <table v-if="devices.length" class="list">
        <thead><tr><th>{{ t("Device") }}</th><th>{{ t("Address") }}</th><th>{{ t("Frames") }}</th></tr></thead>
        <tbody>
          <tr v-for="(d, i) in devices" :key="i" class="clickable" @click="actions.select([...path, 'devices', i])">
            <td>{{ displayName(d, lang) }}<span v-if="d.name" class="ident">{{ d.name }}</span></td>
            <td class="mono">{{ d.node_id != null ? hex(d.node_id, 2) : d.address != null ? hex(d.address, 2) : "—" }}</td>
            <td>{{ d.frames?.length ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("No devices.") }}</p>
    </section>

    <section v-if="kind === 'document'" class="card">
      <h3>
        {{ t("Buses") }} <span class="muted">{{ buses.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addBus()">+ {{ t("Bus") }}</button>
        </span>
      </h3>
      <table v-if="buses.length" class="list">
        <thead><tr><th>{{ t("Bus") }}</th><th>{{ t("Protocol") }}</th><th>{{ t("Devices") }}</th><th>{{ t("Frames") }}</th></tr></thead>
        <tbody>
          <tr v-for="b in buses" :key="b.name" class="clickable" @click="actions.select(b.path)">
            <td>{{ b.label }}<span v-if="b.label !== b.name" class="ident">{{ b.name }}</span></td><td>{{ b.protocol }}</td>
            <td>{{ b.devices }}</td><td>{{ b.frames }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("No buses.") }}</p>
    </section>

    <!-- The revision history is a separate node of the tree -->
    <section v-if="kind === 'document'" class="card">
      <h3>{{ t("Revision history") }} <span class="muted">{{ node?.history?.length ?? 0 }}</span></h3>
      <p v-if="node?.history?.length" class="muted">
        {{ t("Latest entry:") }} <b class="mono">{{ node.history[0].version }}</b>
        <template v-if="node.history[0].date"> {{ t("({date})", { date: node.history[0].date }) }}</template>
      </p>
      <button class="small" @click="actions.select(HISTORY_PATH)">{{ t("Open history") }}</button>
    </section>
  </div>
</template>
