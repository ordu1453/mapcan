<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { hex, rangeLabel } from "../bits";
import { addBus, addDevice, addFrame, addSdo, addSignal, canRename, duplicateNode, receiveFrame, removeNode, removeSelected,
  renameNode, stopReceiving } from "../edit";
import { describe, fieldHelp, UI_HELP } from "../form/help";
import { parseInteger, ParseError } from "../form/input";
import { applies, CANOPEN_DLC, FORMS, isRequired, optionsOf, placeholderOf, type FieldDef, type FormContext,
  type FormKind } from "../form/spec";
import { deviceLabel, displayName, getAt, HISTORY_PATH, nodeKind, ownerPath, pathKey, samePath, startsWith, txt } from "../model";
import { actions, includedPath, lang, resolvedFrames, selectedFramePath, selectedResolvedFrame, store, toast, viewData }
  from "../store";
import type { Diagnostic, Path } from "../types";
import BitGrid from "./BitGrid.vue";
import DocumentRequisites from "./DocumentRequisites.vue";
import FieldInput from "./FieldInput.vue";
import FlagsTable from "./FlagsTable.vue";
import HelpTip from "./HelpTip.vue";
import HistoryEditor from "./HistoryEditor.vue";
import InlineRename from "./InlineRename.vue";
import ValueTable from "./ValueTable.vue";
import { N_, t } from "../i18n";

const KIND_LABEL: Record<string, string> = {
  document: N_("Document"), history: "", revision: N_("History entry"), bus: N_("Bus"),
  device: N_("Device"), frame: N_("Frame"), signal: N_("Signal"), flag: N_("Flag"), sdo: N_("SDO exchange"), unknown: "",
};

const path = computed<Path>(() => store.selected);
const kind = computed(() => nodeKind(path.value));
// Вместе с подключёнными файлами (include): их узлы видны, но правятся только в своём файле
const data = computed(() => viewData.value);
const node = computed(() => getAt(data.value, kind.value === "document" ? ["document"] : path.value));
const includedFile = computed(() => includedPath(path.value));
const readonly = computed(() => !!store.state?.readonly || !!includedFile.value);
const diags = computed(() => store.state?.diagnostics ?? []);

// What the form's conditions know about the node (see FormContext in form/spec.ts)
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
    frameDirection: frame?.direction ?? null,
    signalEncoding: s?.encoding ?? null,
    bitLength: s?.bit_length ?? null,
    hasSelector: !!s && !!rframe.value?.signals.some((x) => x.multiplexer && !samePath(x.path, s.path)),
    frames: kind.value === "device" ? node.value?.frames ?? [] : undefined,
  };
});
// Sections of the form with the fields that apply. A field with a value, an error or a warning is shown even if it
// does not apply to the node's type or protocol, otherwise the problem could not be found. Position and
// transmission fields have their own controls above the form.
const sections = computed(() => (FORMS[kind.value as FormKind] ?? [])
  .map((sec) => ({
    title: sec.title,
    fields: sec.fields
      .filter((f) => !f.layout && (applies(f, formCtx.value) || fieldValue(f) != null
        || fieldDiags(f).some((d) => d.level !== "info")))
      .map((f) => ({ ...f, help: fieldHelp(kind.value as FormKind, f), isRequired: isRequired(f, formCtx.value),
        shownOptions: optionsOf(f, formCtx.value) })),
  }))
  .filter((sec) => sec.fields.length));
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

function commit(def: FieldDef, value: unknown) {
  // Имя — через renameNode: проверка занятости и обновление получателей кадров при переименовании устройства
  if (def.key === "name" && canRename(path.value)) {
    void renameNode(path.value, String(value ?? "")).then((err) => { if (err) toast(err); });
    return;
  }
  // Смена типа CANopen: записанный DLC, недопустимый для нового типа, убираем — берётся длина типа
  const allowed = kind.value === "frame" && def.key === "type" ? CANOPEN_DLC[String(value ?? "raw")] : undefined;
  const dlc = node.value?.dlc;
  // У значения SDO encoding обязателен: новое значение создаётся сразу с encoding: raw
  // Без идентификатора у SDO-обмена нет значения: словарь value удаляется целиком
  if (kind.value === "sdo" && def.key === "value.name" && (node.value?.value == null || !value)) {
    if (value) void actions.apply([{ op: "set", path: [...path.value, "value"], value: { name: value, encoding: "raw", bit_length: 32 } }]);
    else if (node.value?.value != null) void actions.apply([{ op: "remove", path: [...path.value, "value"] }]);
    return;
  }
  void actions.apply([{ op: "set", path: [...path.value, ...def.key.split(".")], value },
    ...(allowed && dlc != null && !allowed.includes(dlc) ? [{ op: "remove" as const, path: [...path.value, "dlc"] }] : [])]);
}

// В заголовке — название для людей (у устройства с сокращением) и идентификатор; каждая часть правится двойным щелчком
const renaming = ref<"name" | "short" | "title" | null>(null);
const nodeTitle = computed(() => (["bus", "device", "frame", "signal"].includes(kind.value) ? txt(node.value?.title, lang.value) : ""));
watch(() => pathKey(path.value), () => { renaming.value = null; });

// Ключи, сообщения по которым показываются у полей формы и в таблицах (значения, флаги, позиция, передача)
const SHOWN_ELSEWHERE = ["values", "flags", "start_bit", "bit_length", "byte", "bit", "byte_length",
  "trigger", "cycle_ms", "signals", "frames", "devices", "sdo", "history"];

/** Сообщения узла, которые не видны ни у одного поля: на сам узел или на поле, которого нет в форме. */
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

// ------------------------------------------------------------------ хлебные крошки

const crumbs = computed(() => {
  const out: Array<{ label: string; path: Path }> = [];
  const p = path.value;
  for (let n = 2; n <= p.length; n++) {
    const sub = p.slice(0, n);
    const k = nodeKind(sub);
    if (k === "unknown" || k === "document") continue;
    const nd = getAt(data.value, sub);
    const label = k === "history" ? t("Revision history") : k === "revision" ? nd?.version
      : ["bus", "device", "frame", "signal"].includes(k) ? displayName(nd, lang.value) : nd?.name;
    out.push({ label, path: sub });
  }
  return out;
});

// ------------------------------------------------------------------ кадр

const rframe = computed(() => selectedResolvedFrame.value);
const framePath = computed(() => selectedFramePath.value);
const frameData = computed(() => (framePath.value ? getAt(data.value, framePath.value) : null));

const muxValue = computed({
  get: () => (framePath.value ? store.muxView[pathKey(framePath.value)] ?? null : null),
  set: (v: number | null) => {
    if (framePath.value) store.muxView[pathKey(framePath.value)] = v;
  },
});

// Режим передачи: период cycle_ms — циклически, иначе trigger (по событию / по запросу)
const txMode = computed(() => (node.value?.cycle_ms != null ? "cyclic" : node.value?.trigger ?? ""));
const txCycle = computed(() => node.value?.cycle_ms ?? null);

function setMode(e: Event) {
  const m = (e.target as HTMLSelectElement).value;
  const p = path.value;
  const ops = [];
  if (m !== "cyclic" && node.value?.cycle_ms != null) ops.push({ op: "remove" as const, path: [...p, "cycle_ms"] });
  if ((m === "" || m === "cyclic") && node.value?.trigger != null) ops.push({ op: "remove" as const, path: [...p, "trigger"] });
  if (m === "cyclic") ops.push({ op: "set" as const, path: [...p, "cycle_ms"], value: txCycle.value ?? 100 });
  else if (m !== "") ops.push({ op: "set" as const, path: [...p, "trigger"], value: m });
  void actions.apply(ops);
}

// Ошибки ввода чисел в полях позиции и периода; сбрасываются при переходе к другому узлу
const MAX_FRAME_BITS = 64 * 8;
const inputErrors = ref<Record<string, string>>({});
watch(() => pathKey(path.value), () => { inputErrors.value = {}; });

/** Целое из поля ввода в диапазоне [min, max]; при ошибке показывает сообщение, возвращает в поле прежнее значение и даёт null. */
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

// Сообщения о режиме передачи: на поле периода, если оно видно, иначе на выборе режима
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

// RX-кадр устройства может оказаться кадром, который уже описан у отправителя: его можно выбрать вместо своей копии
const rxSources = computed(() => {
  const f = rframe.value;
  if (kind.value !== "frame" || !f?.device || f.direction !== "rx") return [];
  return (store.state?.resolved?.frames ?? [])
    .filter((o) => o.path[1] === path.value[1] && o.sender && o.sender !== f.device && o.device !== f.device)
    // Кадры с тем же CAN ID — первыми: скорее всего, это и есть описанный дважды кадр
    .sort((a, b) => Number(b.can_id === f.can_id) - Number(a.can_id === f.can_id)
      || a.sender!.localeCompare(b.sender!) || a.name.localeCompare(b.name))
    .map((o) => ({
      key: pathKey(o.path), path: o.path,
      label: `${o.sender} · ${o.name}` + (o.can_id != null ? ` (${hex(o.can_id, o.extended ? 8 : 3)})` : ""),
    }));
});

/** Кадр-оригинал для сообщения rx-duplicate: тот же CAN ID, описан у отправителя. */
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

// ------------------------------------------------------------------ сигнал

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

// Сообщения о позиции сигнала: пересечения и выход за DLC (на сигнал целиком) и сообщения полей начала/длины
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
  return n.values != null || ["enum", "flag"].includes(rsignal.value?.encoding ?? "");
});
const showFlags = computed(() => kind.value === "signal" && (node.value?.flags != null || node.value?.kind === "bitfield"));

// ------------------------------------------------------------------ списки дочерних узлов

const childFrames = computed(() => {
  if (kind.value !== "device" && kind.value !== "bus") return [];
  return (node.value?.frames ?? []).map((f: any, i: number) => {
    const p = [...path.value, "frames", i];
    const rf = resolvedFrames.value.get(pathKey(p));
    return { path: p, name: f?.name ?? "—", label: displayName(f, lang.value), id: rf ? hex(rf.can_id) : "—", type: f?.type ?? "raw",
      desc: txt(f?.description, lang.value), n: rf?.signals.length ?? 0 };
  });
});

const frameSignals = computed(() => {
  if (kind.value !== "frame" || !rframe.value) return [];
  return rframe.value.signals.map((s) => ({
    s, label: s.synthetic ? s.name : displayName(getAt(data.value, s.path), lang.value),
    desc: txt(getAt(data.value, s.path)?.description, lang.value),
    bits: rangeLabel(Math.min(...s.occupied), Math.max(...s.occupied)),
  }));
});

// Пустой элемент «- » в черновике YAML — null: показываем строку без полей
const devices = computed(() => (kind.value === "bus" && Array.isArray(node.value?.devices)
  ? node.value.devices.map((d: any) => (d && typeof d === "object" ? d : {})) : []));

/** Обмен устройства — вычисляется из отправителей и получателей всех кадров шины. */
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
    // Своё устройство из получателей чужого кадра можно убрать; свой RX-кадр — только удалить
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
// SDO-обмены — только у кадров CANopen
const canAddSdo = computed(() => kind.value === "frame" && (data.value?.buses?.[Number(path.value[1])]?.protocol ?? "canopen") === "canopen"
  && (node.value?.sdo != null || ["sdo_tx", "sdo_rx"].includes(node.value?.type)));
const isListItem = computed(() => typeof path.value[path.value.length - 1] === "number" && path.value.length > 1);

function onCreate(start: number, length: number) {
  if (framePath.value) void addSignal(framePath.value, { start_bit: start, bit_length: length });
}
function onLayout(p: Path, start: number, length: number) {
  void actions.apply([{ op: "set_layout", path: p, start_bit: start, bit_length: length }]);
}
</script>

<template>
  <div v-if="store.state?.data" class="node-editor">
    <header class="ne-head">
      <div>
        <div class="crumbs">
          <a @click="actions.select(['document'])">{{ txt(data?.document?.title, lang) || t("Document") }}</a>
          <template v-for="c in crumbs" :key="c.path.join('/')">
            <span class="sep">›</span><a @click="actions.select(c.path)">{{ c.label }}</a>
          </template>
        </div>
        <h2>
          <span v-if="KIND_LABEL[kind]" class="kind-badge">{{ t(KIND_LABEL[kind]) }}</span>
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
              : kind === "revision" ? node?.version : node?.name }}
          </template>
          <span v-if="kind === 'frame' && rframe" class="mono id-badge">{{ hex(rframe.can_id, rframe.extended ? 8 : 3) }}</span>
        </h2>
      </div>
      <div class="ne-actions">
        <template v-if="isListItem && !readonly">
          <button class="icon" :title="t('Duplicate')" @click="duplicateNode(path)">⧉</button>
          <button class="icon danger" :title="store.selectedVia ? t('Stop receiving (remove from receivers)') : t('Delete (Del)')"
                  @click="removeSelected()">✕</button>
        </template>
      </div>
    </header>

    <div v-if="includedFile" class="banner info">
      🔗 {{ t("The node is described in the included file {file}: it is read-only here, edit it in that file.",
              { file: includedFile }) }}
    </div>
    <div v-for="d in ownDiags" :key="d.code + d.message" class="banner" :class="d.level">
      <b>{{ d.code }}</b>: {{ d.message }}
      <button v-if="d.code === 'rx-duplicate' && rxTwin && !readonly" class="small fix"
              @click="receiveFrame(path, rxTwin.path)">{{ t("Receive frame {frame}", { frame: rxTwin.label }) }}</button>
    </div>
    <div v-if="kind === 'frame' && store.selectedVia" class="banner info">
      {{ t("The frame is described at its sender; {device} receives it. Delete or ✕ stops receiving it and keeps the frame.",
           { device: viaLabel }) }}
    </div>

    <!-- Битовая карта для кадра, сигнала, флага -->
    <section v-if="rframe && rframe.dlc > 0 && ['frame', 'signal', 'flag', 'sdo'].includes(kind)" class="card">
      <h3>{{ t("Frame layout") }} <span class="muted">{{ frameData?.name }} · DLC {{ rframe.dlc }}</span></h3>
      <BitGrid :frame="rframe" :selected="path" :palette="store.state.palette" :readonly="readonly"
               v-model:mux-value="muxValue"
               @select="actions.select" @create="onCreate" @layout="onLayout" />
    </section>

    <section v-if="kind !== 'history'" class="card">
      <h3>{{ t("Properties") }} <span v-if="hasRequired" class="muted req-note"><span class="req">*</span> {{ t("— required field") }}</span></h3>
      <div class="form-grid">
        <!-- позиция сигнала -->
        <template v-if="kind === 'signal' && rsignal">
          <label class="field" :class="worstLevel([...wholeDiags, ...startDiags])">
            <span class="field-label"><HelpTip :text="describe('signal', 'start_bit') ?? ''" />{{ t("Start bit (LSB)") }}</span>
            <input class="mono" :value="rsignal.start_bit" :readonly="readonly || rsignal.synthetic" @change="setLayout('start_bit', $event)" />
            <span v-if="inputErrors.start_bit" class="field-msg error">{{ inputErrors.start_bit }}</span>
            <span v-for="d in startDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
          <label class="field" :class="worstLevel([...wholeDiags, ...lengthDiags])">
            <span class="field-label"><HelpTip :text="describe('signal', 'bit_length') ?? ''" />{{ t("Length, bits") }}</span>
            <input class="mono" :value="rsignal.bit_length" :readonly="readonly || rsignal.synthetic" @change="setLayout('bit_length', $event)" />
            <span v-if="inputErrors.bit_length" class="field-msg error">{{ inputErrors.bit_length }}</span>
            <span class="field-hint">
              {{ t("bytes {bytes}, bits {bits}", {
                bytes: rangeLabel(Math.floor(Math.min(...rsignal.occupied) / 8), Math.floor(Math.max(...rsignal.occupied) / 8)),
                bits: rangeLabel(Math.min(...rsignal.occupied), Math.max(...rsignal.occupied)) }) }}
            </span>
            <span v-for="d in [...wholeDiags, ...lengthDiags]" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
        </template>

        <!-- RX-кадр: выбрать вместо него кадр другого устройства -->
        <label v-if="rxSources.length && !readonly" class="field">
          <span class="field-label"><HelpTip :text="UI_HELP.source" />{{ t("Frame of another device") }}</span>
          <select value="" @change="setSource">
            <option value="">{{ t("none — the frame is described here") }}</option>
            <option v-for="o in rxSources" :key="o.key" :value="o.key">{{ o.label }}</option>
          </select>
          <span class="field-hint">{{ t("the device receives a frame described at its sender") }}</span>
        </label>

        <!-- режим передачи кадра -->
        <template v-if="kind === 'frame'">
          <label class="field" :class="txMode === 'cyclic' ? '' : worstLevel(txDiags)">
            <span class="field-label"><HelpTip :text="UI_HELP.mode" />{{ t("Transmission") }}</span>
            <select :value="txMode" :disabled="readonly" @change="setMode">
              <option value="">{{ t("not set") }}</option>
              <option value="cyclic">{{ t("cyclic") }}</option>
              <option value="event">{{ t("on event") }}</option>
              <option value="on_request">{{ t("on request") }}</option>
            </select>
            <template v-if="txMode !== 'cyclic'">
              <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
            </template>
          </label>
          <label v-if="txMode === 'cyclic'" class="field" :class="worstLevel(txDiags)">
            <span class="field-label"><HelpTip :text="describe('frame', 'cycle_ms') ?? ''" />{{ t("Period, ms") }}</span>
            <input class="mono" :value="txCycle ?? ''" :readonly="readonly" @change="setCycle" />
            <span v-if="inputErrors.cycle_ms" class="field-msg error">{{ inputErrors.cycle_ms }}</span>
            <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
        </template>

        <template v-for="sec in sections" :key="sec.title ?? ''">
          <h4 v-if="sec.title" class="form-section">{{ t(sec.title) }}</h4>
          <FieldInput v-for="def in sec.fields" :key="path.join('/') + def.key" :def="def" :value="shownValue(def)"
                      :options="def.shownOptions" :path="fieldPath(def)" :required="def.isRequired"
                      :diags="fieldDiags(def)" :readonly="readonly"
                      :placeholder="placeholderFor(def)"
                      @commit="commit(def, $event)" />
        </template>
      </div>
    </section>

    <DocumentRequisites v-if="kind === 'document'" />
    <HistoryEditor v-if="kind === 'history' || kind === 'revision'" :path="path" />

    <section v-if="typeof node?.values === 'string'" class="card">
      <h3>{{ t("Values") }}</h3>
      <p class="muted">{{ t("Table \"{name}\" from value_tables; edit it there.", { name: node.values }) }}</p>
    </section>
    <ValueTable v-else-if="showValues" class="card" :path="path" :values="node?.values" :hex="node?.value_format === 'hex'"
                :readonly="readonly" :diags="diags" />
    <FlagsTable v-if="showFlags" class="card" :path="path" :flags="node?.flags" :readonly="readonly" :diags="diags" />

    <!-- Сигналы кадра -->
    <section v-if="kind === 'frame'" class="card">
      <h3>
        {{ t("Signals") }} <span class="muted">{{ frameSignals.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button v-if="canAddSdo" class="small" @click="addSdo(path)">+ {{ t("SDO exchange") }}</button>
          <button class="small" @click="addSignal(path)">+ {{ t("Signal") }}</button>
        </span>
      </h3>
      <table v-if="frameSignals.length" class="list">
        <thead><tr><th></th><th>{{ t("Signal") }}</th><th>{{ t("Bits") }}</th><th>{{ t("Type") }}</th><th>{{ t("Description") }}</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in frameSignals" :key="r.s.name" class="clickable"
              @click="actions.select(r.s.synthetic ? path : r.s.path)">
            <td><span class="swatch" :style="{ background: store.state.palette[i % store.state.palette.length] }" /></td>
            <td>{{ r.label }}<span v-if="r.label !== r.s.name" class="ident">{{ r.s.name }}</span><span
              v-if="r.s.synthetic" class="muted"> (SDO)</span></td>
            <td class="mono">{{ r.bits }}</td>
            <td>{{ r.s.encoding }}<span v-if="r.s.mux" class="muted"> · mux {{ r.s.mux.join(", ") }}</span></td>
            <td>{{ r.desc }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("No signals yet. Drag across the bits in the layout above or click “+ Signal”.") }}</p>
    </section>

    <!-- Кадры устройства / шины -->
    <section v-if="kind === 'bus' || kind === 'device'" class="card">
      <h3>
        {{ t("Frames") }} <span class="muted">{{ childFrames.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addFrame(path)">+ {{ t("Frame") }}</button>
        </span>
      </h3>
      <table v-if="childFrames.length" class="list">
        <thead><tr><th>ID</th><th>{{ t("Frame") }}</th><th>{{ t("Type") }}</th><th>{{ t("Signals") }}</th><th>{{ t("Description") }}</th><th v-if="!readonly"></th></tr></thead>
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

    <!-- Обмен устройства: что оно принимает и какие чужие кадры передаёт -->
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

    <!-- История изменений — отдельный узел дерева -->
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
