<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { hex, rangeLabel } from "../bits";
import { addBus, addDevice, addFrame, addSdo, addSignal, canRename, duplicateNode, receiveFrame, removeNode, removeSelected,
  renameNode, stopReceiving } from "../edit";
import { HELP } from "../help";
import { CANOPEN_DLC, FIELDS, parseInteger, ParseError, type FieldCtx, type FieldDef } from "../fields";
import { deviceLabel, displayName, getAt, HISTORY_PATH, nodeKind, ownerPath, pathKey, samePath, startsWith, txt } from "../model";
import { actions, lang, resolvedFrames, selectedFramePath, selectedResolvedFrame, store, toast } from "../store";
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
  document: N_("Документ"), history: "", revision: N_("Запись истории"), bus: N_("Шина"),
  device: N_("Устройство"), frame: N_("Кадр"), signal: N_("Сигнал"), flag: N_("Флаг"), sdo: N_("SDO-обмен"), unknown: "",
};

const path = computed<Path>(() => store.selected);
const kind = computed(() => nodeKind(path.value));
const data = computed(() => store.state?.data);
const node = computed(() => getAt(data.value, kind.value === "document" ? ["document"] : path.value));
const readonly = computed(() => !!store.state?.readonly);
const diags = computed(() => store.state?.diagnostics ?? []);

const fieldCtx = computed<FieldCtx>(() => {
  const s = kind.value === "signal" ? rsignal.value : null;
  const bus = path.value[0] === "buses" ? getAt(data.value, path.value.slice(0, 2)) : null;
  const frame = kind.value === "frame" ? rframe.value : undefined;
  return {
    protocol: bus ? bus.protocol ?? "canopen" : "",
    encoding: s?.encoding, bitLength: s?.bit_length,
    hasSelector: !!s && !!rframe.value?.signals.some((x) => x.multiplexer && !samePath(x.path, s.path)),
    devices: (bus?.devices ?? []).map((d: any) => d?.name).filter(Boolean),
    deviceLabels: Object.fromEntries((bus?.devices ?? []).filter((d: any) => d?.name)
      .map((d: any) => [d.name, deviceLabel(d, lang.value)])),
    owner: frame?.device ?? null,
    direction: frame?.direction ?? null,
    sender: frame?.sender ?? null,
  };
});
// Поле с ошибкой или предупреждением показываем, даже если оно не относится к текущему типу/протоколу — иначе ошибку не найти
const fields = computed(() => (FIELDS[kind.value] ?? [])
  .filter((f) => !f.when || f.when(node.value, fieldCtx.value) || fieldValue(f) != null
    || fieldDiags(f).some((d) => d.level !== "info"))
  .map((f) => {
    const required = typeof f.required === "function" ? f.required(node.value, fieldCtx.value) : !!f.required;
    return { ...f, required: undefined, isRequired: required,
      options: f.optionsFor ? f.optionsFor(fieldCtx.value) : f.options };
  }));
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

const DEFAULTS: Record<string, string> = {
  factor: "1", offset: "0", bit_length: "1", protocol: "canopen",
};

function placeholderFor(def: FieldDef): string {
  if (kind.value === "frame" && def.key === "id" && rframe.value) {
    return hex(rframe.value.can_id, rframe.value.extended ? 8 : 3) + " " + t("(вычислен)");
  }
  if (def.key === "priority" && fieldCtx.value.protocol === "j1939") return "6";
  // DLC по умолчанию: 8, у служебного кадра CANopen — из типа
  if (kind.value === "frame" && def.key === "dlc") return t("{n} (по умолчанию)", { n: rframe.value?.dlc ?? 8 });
  return t(DEFAULTS[def.key] ?? "");
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
    if (value) void actions.apply([{ op: "set", path: [...path.value, "value"], value: { name: value, encoding: "raw" } }]);
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
  "transmission", "cycle_ms", "signals", "frames", "devices", "sdo", "history"];

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
    const label = k === "history" ? t("История изменений") : k === "revision" ? nd?.version
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

const txMode = computed(() => node.value?.transmission?.mode ?? (node.value?.cycle_ms != null ? "cyclic" : ""));
const txCycle = computed(() => node.value?.transmission?.cycle_ms ?? node.value?.cycle_ms ?? null);

function setMode(e: Event) {
  const m = (e.target as HTMLSelectElement).value;
  const p = path.value;
  const hasTr = node.value?.transmission != null;
  const ops = [];
  if (m === "") {
    if (hasTr) ops.push({ op: "remove" as const, path: [...p, "transmission"] });
    if (node.value?.cycle_ms != null) ops.push({ op: "remove" as const, path: [...p, "cycle_ms"] });
  } else if (m === "cyclic") {
    const c = txCycle.value ?? 100;
    if (hasTr) ops.push({ op: "set" as const, path: [...p, "transmission"], value: { mode: "cyclic", cycle_ms: c } });
    else ops.push({ op: "set" as const, path: [...p, "cycle_ms"], value: c });
  } else {
    if (node.value?.cycle_ms != null) ops.push({ op: "remove" as const, path: [...p, "cycle_ms"] });
    ops.push({ op: "set" as const, path: [...p, "transmission"], value: { mode: m } });
  }
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
    if (n < min || n > max) msg = t("«{raw}» — допустимо от {min} до {max}", { raw: el.value.trim(), min, max });
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
    ? diags.value.filter((d) => startsWith(d.node, [...path.value, "transmission"]) || startsWith(d.node, [...path.value, "cycle_ms"]))
    : [],
);

function setCycle(e: Event) {
  const n = readInt(e, "cycle_ms", 1, 2 ** 31 - 1, txCycle.value);
  if (n === null) return;
  const p = path.value;
  if (node.value?.transmission != null) void actions.apply([{ op: "set", path: [...p, "transmission", "cycle_ms"], value: n }]);
  else void actions.apply([{ op: "set", path: [...p, "cycle_ms"], value: n }]);
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
      .map((f) => row(f, f.device ? label(f.device) : t("кадр шины"))),
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
          <a @click="actions.select(['document'])">{{ txt(data?.document?.title, lang) || t("Документ") }}</a>
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
              <span class="renamable" :title="t('Двойной щелчок — изменить сокращение')"
                    @dblclick="renaming = 'short'">{{ node.short }}</span><span class="muted">·</span>
            </template>
            <span v-if="nodeTitle" class="renamable" :title="t('Двойной щелчок — изменить название')"
                  @dblclick="renaming = 'title'">{{ nodeTitle }}</span>
            <span class="renamable mono" :class="{ secondary: !!nodeTitle }" :title="t('Двойной щелчок — изменить идентификатор')"
                  @dblclick="renaming = 'name'">{{ node?.name }}</span>
          </template>
          <template v-else>
            {{ kind === "document" ? txt(node?.title, lang) : kind === "history" ? t("История изменений")
              : kind === "revision" ? node?.version : node?.name }}
          </template>
          <span v-if="kind === 'frame' && rframe" class="mono id-badge">{{ hex(rframe.can_id, rframe.extended ? 8 : 3) }}</span>
        </h2>
      </div>
      <div class="ne-actions">
        <template v-if="isListItem && !readonly">
          <button class="icon" :title="t('Дублировать')" @click="duplicateNode(path)">⧉</button>
          <button class="icon danger" :title="store.selectedVia ? t('Не принимать (убрать из получателей)') : t('Удалить (Delete)')"
                  @click="removeSelected()">✕</button>
        </template>
      </div>
    </header>

    <div v-for="d in ownDiags" :key="d.code + d.message" class="banner" :class="d.level">
      <b>{{ d.code }}</b>: {{ d.message }}
      <button v-if="d.code === 'rx-duplicate' && rxTwin && !readonly" class="small fix"
              @click="receiveFrame(path, rxTwin.path)">{{ t("Принимать кадр {frame}", { frame: rxTwin.label }) }}</button>
    </div>
    <div v-if="kind === 'frame' && store.selectedVia" class="banner info">
      {{ t("Кадр описан у отправителя, {device} принимает его. Delete или ✕ — перестать принимать, кадр останется.",
           { device: fieldCtx.deviceLabels?.[store.selectedVia] ?? store.selectedVia }) }}
    </div>

    <!-- Битовая карта для кадра, сигнала, флага -->
    <section v-if="rframe && rframe.dlc > 0 && ['frame', 'signal', 'flag', 'sdo'].includes(kind)" class="card">
      <h3>{{ t("Раскладка кадра") }} <span class="muted">{{ frameData?.name }} · DLC {{ rframe.dlc }}</span></h3>
      <BitGrid :frame="rframe" :selected="path" :palette="store.state.palette" :readonly="readonly"
               v-model:mux-value="muxValue"
               @select="actions.select" @create="onCreate" @layout="onLayout" />
    </section>

    <section v-if="kind !== 'history'" class="card">
      <h3>{{ t("Свойства") }} <span v-if="hasRequired" class="muted req-note"><span class="req">*</span> {{ t("— обязательное поле") }}</span></h3>
      <div class="form-grid">
        <!-- позиция сигнала -->
        <template v-if="kind === 'signal' && rsignal">
          <label class="field" :class="worstLevel([...wholeDiags, ...startDiags])">
            <span class="field-label"><HelpTip :text="HELP['layout.start_bit']" />{{ t("Начальный бит (LSB)") }}</span>
            <input class="mono" :value="rsignal.start_bit" :readonly="readonly || rsignal.synthetic" @change="setLayout('start_bit', $event)" />
            <span v-if="inputErrors.start_bit" class="field-msg error">{{ inputErrors.start_bit }}</span>
            <span v-for="d in startDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
          <label class="field" :class="worstLevel([...wholeDiags, ...lengthDiags])">
            <span class="field-label"><HelpTip :text="HELP['layout.bit_length']" />{{ t("Длина, бит") }}</span>
            <input class="mono" :value="rsignal.bit_length" :readonly="readonly || rsignal.synthetic" @change="setLayout('bit_length', $event)" />
            <span v-if="inputErrors.bit_length" class="field-msg error">{{ inputErrors.bit_length }}</span>
            <span class="field-hint">
              {{ t("байты {bytes}, биты {bits}", {
                bytes: rangeLabel(Math.floor(Math.min(...rsignal.occupied) / 8), Math.floor(Math.max(...rsignal.occupied) / 8)),
                bits: rangeLabel(Math.min(...rsignal.occupied), Math.max(...rsignal.occupied)) }) }}
            </span>
            <span v-for="d in [...wholeDiags, ...lengthDiags]" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
        </template>

        <!-- RX-кадр: выбрать вместо него кадр другого устройства -->
        <label v-if="rxSources.length && !readonly" class="field">
          <span class="field-label"><HelpTip :text="HELP['layout.source']" />{{ t("Кадр другого устройства") }}</span>
          <select value="" @change="setSource">
            <option value="">{{ t("нет — кадр описан здесь") }}</option>
            <option v-for="o in rxSources" :key="o.key" :value="o.key">{{ o.label }}</option>
          </select>
          <span class="field-hint">{{ t("устройство принимает кадр, описанный у отправителя") }}</span>
        </label>

        <!-- режим передачи кадра -->
        <template v-if="kind === 'frame'">
          <label class="field" :class="txMode === 'cyclic' ? '' : worstLevel(txDiags)">
            <span class="field-label"><HelpTip :text="HELP['layout.mode']" />{{ t("Передача") }}</span>
            <select :value="txMode" :disabled="readonly" @change="setMode">
              <option value="">{{ t("не указано") }}</option>
              <option value="cyclic">{{ t("циклически") }}</option>
              <option value="event">{{ t("по событию") }}</option>
              <option value="on_request">{{ t("по запросу") }}</option>
            </select>
            <template v-if="txMode !== 'cyclic'">
              <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
            </template>
          </label>
          <label v-if="txMode === 'cyclic'" class="field" :class="worstLevel(txDiags)">
            <span class="field-label"><HelpTip :text="HELP['layout.cycle_ms']" />{{ t("Период, мс") }}</span>
            <input class="mono" :value="txCycle ?? ''" :readonly="readonly" @change="setCycle" />
            <span v-if="inputErrors.cycle_ms" class="field-msg error">{{ inputErrors.cycle_ms }}</span>
            <span v-for="d in txDiags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
        </template>

        <FieldInput v-for="def in fields" :key="path.join('/') + def.key" :def="def" :value="shownValue(def)"
                    :path="fieldPath(def)" :required="def.isRequired"
                    :diags="fieldDiags(def)" :readonly="readonly"
                    :placeholder="placeholderFor(def)"
                    @commit="commit(def, $event)" />
      </div>
    </section>

    <DocumentRequisites v-if="kind === 'document'" />
    <HistoryEditor v-if="kind === 'history' || kind === 'revision'" :path="path" />

    <ValueTable v-if="showValues" class="card" :path="path" :values="node?.values" :hex="node?.value_format === 'hex'"
                :readonly="readonly" :diags="diags" />
    <FlagsTable v-if="showFlags" class="card" :path="path" :flags="node?.flags" :readonly="readonly" :diags="diags" />

    <!-- Сигналы кадра -->
    <section v-if="kind === 'frame'" class="card">
      <h3>
        {{ t("Сигналы") }} <span class="muted">{{ frameSignals.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button v-if="canAddSdo" class="small" @click="addSdo(path)">+ {{ t("SDO-обмен") }}</button>
          <button class="small" @click="addSignal(path)">+ {{ t("Сигнал") }}</button>
        </span>
      </h3>
      <table v-if="frameSignals.length" class="list">
        <thead><tr><th></th><th>{{ t("Сигнал") }}</th><th>{{ t("Биты") }}</th><th>{{ t("Тип") }}</th><th>{{ t("Описание") }}</th></tr></thead>
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
      <p v-else class="muted">{{ t("Сигналов нет. Протяните мышью по битам в раскладке выше или нажмите «+ Сигнал».") }}</p>
    </section>

    <!-- Кадры устройства / шины -->
    <section v-if="kind === 'bus' || kind === 'device'" class="card">
      <h3>
        {{ t("Кадры") }} <span class="muted">{{ childFrames.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addFrame(path)">+ {{ t("Кадр") }}</button>
        </span>
      </h3>
      <table v-if="childFrames.length" class="list">
        <thead><tr><th>ID</th><th>{{ t("Кадр") }}</th><th>{{ t("Тип") }}</th><th>{{ t("Сигналов") }}</th><th>{{ t("Описание") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="f in childFrames" :key="f.name" class="clickable" @click="actions.select(f.path)">
            <td class="mono">{{ f.id }}</td><td>{{ f.label }}<span v-if="f.label !== f.name" class="ident">{{ f.name }}</span></td><td>{{ f.type }}</td>
            <td>{{ f.n }}</td><td>{{ f.desc }}</td>
            <td v-if="!readonly" class="act"><button class="icon danger" :title="t('Удалить')" @click.stop="removeNode(f.path)">✕</button></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("Кадров нет.") }}</p>
    </section>

    <!-- Обмен устройства: что оно принимает и какие чужие кадры передаёт -->
    <section v-if="exchange" class="card">
      <h3>{{ t("Принимает") }} <span class="muted">{{ exchange.receives.length }}</span></h3>
      <table v-if="exchange.receives.length" class="list">
        <thead><tr><th>ID</th><th>{{ t("Кадр") }}</th><th>{{ t("Отправитель") }}</th><th>{{ t("Описание") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="f in exchange.receives" :key="f.name" class="clickable" @click="actions.select(f.path)">
            <td class="mono">{{ f.id }}</td><td>{{ f.label }}<span v-if="f.label !== f.name" class="ident">{{ f.name }}</span></td>
            <td>{{ f.peer }}</td><td>{{ f.desc }}</td>
            <td v-if="!readonly" class="act">
              <button v-if="f.foreign" class="icon danger" :title="t('Не принимать (убрать из получателей)')"
                      @click.stop="stopReceiving(f.path, node.name)">✕</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("Устройство не указано получателем ни одного кадра.") }}</p>
      <template v-if="exchange.sends.length">
        <h3 class="sub">{{ t("Передаёт кадры других устройств") }} <span class="muted">{{ exchange.sends.length }}</span></h3>
        <table class="list">
          <thead><tr><th>ID</th><th>{{ t("Кадр") }}</th><th>{{ t("Устройство") }}</th><th>{{ t("Описание") }}</th></tr></thead>
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
        {{ t("Устройства") }} <span class="muted">{{ devices.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addDevice(path)">+ {{ t("Устройство") }}</button>
        </span>
      </h3>
      <table v-if="devices.length" class="list">
        <thead><tr><th>{{ t("Устройство") }}</th><th>{{ t("Адрес") }}</th><th>{{ t("Кадров") }}</th></tr></thead>
        <tbody>
          <tr v-for="(d, i) in devices" :key="i" class="clickable" @click="actions.select([...path, 'devices', i])">
            <td>{{ displayName(d, lang) }}<span v-if="d.name" class="ident">{{ d.name }}</span></td>
            <td class="mono">{{ d.node_id != null ? hex(d.node_id, 2) : d.address != null ? hex(d.address, 2) : "—" }}</td>
            <td>{{ d.frames?.length ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("Устройств нет.") }}</p>
    </section>

    <section v-if="kind === 'document'" class="card">
      <h3>
        {{ t("Шины") }} <span class="muted">{{ buses.length }}</span>
        <span v-if="!readonly" class="card-actions">
          <button class="small" @click="addBus()">+ {{ t("Шина") }}</button>
        </span>
      </h3>
      <table v-if="buses.length" class="list">
        <thead><tr><th>{{ t("Шина") }}</th><th>{{ t("Протокол") }}</th><th>{{ t("Устройства") }}</th><th>{{ t("Кадров") }}</th></tr></thead>
        <tbody>
          <tr v-for="b in buses" :key="b.name" class="clickable" @click="actions.select(b.path)">
            <td>{{ b.label }}<span v-if="b.label !== b.name" class="ident">{{ b.name }}</span></td><td>{{ b.protocol }}</td>
            <td>{{ b.devices }}</td><td>{{ b.frames }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("Шин нет.") }}</p>
    </section>

    <!-- История изменений — отдельный узел дерева -->
    <section v-if="kind === 'document'" class="card">
      <h3>{{ t("История изменений") }} <span class="muted">{{ node?.history?.length ?? 0 }}</span></h3>
      <p v-if="node?.history?.length" class="muted">
        {{ t("Последняя запись:") }} <b class="mono">{{ node.history[0].version }}</b>
        <template v-if="node.history[0].date"> {{ t("от {date}", { date: node.history[0].date }) }}</template>
      </p>
      <button class="small" @click="actions.select(HISTORY_PATH)">{{ t("Открыть историю") }}</button>
    </section>
  </div>
</template>
