<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { hex, rangeLabel } from "../bits";
import { childActions, duplicateNode, moveNode, removeNode, addSignal } from "../edit";
import { HELP } from "../help";
import { FIELDS, parseInteger, ParseError, type FieldCtx, type FieldDef } from "../fields";
import { getAt, HISTORY_PATH, nodeKind, pathKey, samePath, startsWith, txt } from "../model";
import { actions, lang, resolvedFrames, selectedFramePath, selectedResolvedFrame, store } from "../store";
import type { Path } from "../types";
import BitGrid from "./BitGrid.vue";
import DocumentRequisites from "./DocumentRequisites.vue";
import FieldInput from "./FieldInput.vue";
import FlagsTable from "./FlagsTable.vue";
import HelpTip from "./HelpTip.vue";
import HistoryEditor from "./HistoryEditor.vue";
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
  return {
    protocol: path.value[0] === "buses" ? getAt(data.value, path.value.slice(0, 2))?.protocol ?? "canopen" : "",
    kind: s?.kind, bitLength: s?.bit_length,
    hasSelector: !!s && !!rframe.value?.signals.some((x) => x.multiplexer && !samePath(x.path, s.path)),
  };
});
const fields = computed(() => (FIELDS[kind.value] ?? []).filter(
  (f) => !f.when || f.when(node.value, fieldCtx.value) || fieldValue(f) != null));

function fieldValue(def: FieldDef) {
  return getAt(node.value, def.key.split("."));
}

/** Значение для формы: у сигнала без явного kind показываем вычисленный тип, а не пустое «авто». */
function shownValue(def: FieldDef) {
  const v = fieldValue(def);
  return v == null && kind.value === "signal" && def.key === "kind" ? rsignal.value?.kind : v;
}

function fieldDiags(def: FieldDef) {
  const p = [...path.value, ...def.key.split(".")];
  return diags.value.filter((d) => startsWith(d.node, p));
}

const DEFAULTS: Record<string, string> = {
  dlc: N_("8 (по умолчанию)"), factor: "1", offset: "0", bit_length: "1", protocol: "canopen",
};

function placeholderFor(def: FieldDef): string {
  if (kind.value === "frame" && def.key === "id" && rframe.value) {
    return hex(rframe.value.can_id, rframe.value.extended ? 8 : 3) + " " + t("(вычислен)");
  }
  if (def.key === "receivers") {
    const bus = getAt(data.value, path.value.slice(0, 2));
    return (bus?.devices ?? []).map((d: any) => d.name).filter((n: string) => n !== node.value?.name).join(", ");
  }
  if (def.key === "priority" && fieldCtx.value.protocol === "j1939") return "6";
  return t(DEFAULTS[def.key] ?? "");
}

function commit(def: FieldDef, value: unknown) {
  void actions.apply([{ op: "set", path: [...path.value, ...def.key.split(".")], value }]);
}

const ownDiags = computed(() =>
  diags.value.filter((d) => d.level !== "info" &&
    (samePath(d.node, path.value) || (kind.value === "document" && d.node.length === 0))),
);

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
      : k === "bus" ? txt(nd?.title, lang.value) || nd?.name : nd?.name;
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

function setCycle(e: Event) {
  const n = readInt(e, "cycle_ms", 1, 2 ** 31 - 1, txCycle.value);
  if (n === null) return;
  const p = path.value;
  if (node.value?.transmission != null) void actions.apply([{ op: "set", path: [...p, "transmission", "cycle_ms"], value: n }]);
  else void actions.apply([{ op: "set", path: [...p, "cycle_ms"], value: n }]);
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

const layoutDiags = computed(() =>
  diags.value.filter((d) => samePath(d.node, signalPath.value) && ["bit-overlap", "signal-out-of-frame"].includes(d.code)),
);

const showValues = computed(() => {
  const n = node.value;
  if (!n) return false;
  if (kind.value === "flag") return true;
  if (kind.value !== "signal") return false;
  return n.values != null || ["enum", "flag"].includes(rsignal.value?.kind ?? "");
});
const showFlags = computed(() => kind.value === "signal" && (node.value?.flags != null || node.value?.kind === "bitfield"));

// ------------------------------------------------------------------ списки дочерних узлов

const childFrames = computed(() => {
  if (kind.value !== "device" && kind.value !== "bus") return [];
  return (node.value?.frames ?? []).map((f: any, i: number) => {
    const p = [...path.value, "frames", i];
    const rf = resolvedFrames.value.get(pathKey(p));
    return { path: p, name: f.name, id: rf ? hex(rf.can_id) : "—", type: f.type ?? "raw", desc: txt(f.description, lang.value), n: rf?.signals.length ?? 0 };
  });
});

const frameSignals = computed(() => {
  if (kind.value !== "frame" || !rframe.value) return [];
  return rframe.value.signals.map((s) => ({
    s, desc: txt(getAt(data.value, s.path)?.description, lang.value),
    bits: rangeLabel(Math.min(...s.occupied), Math.max(...s.occupied)),
  }));
});

const devices = computed(() => (kind.value === "bus" ? (node.value?.devices ?? []) : []));

const add = computed(() => (readonly.value ? [] : childActions(path.value)));
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
          {{ kind === "document" ? txt(node?.title, lang) : kind === "history" ? t("История изменений")
            : kind === "revision" ? node?.version : node?.name }}
          <span v-if="kind === 'frame' && rframe" class="mono id-badge">{{ hex(rframe.can_id, rframe.extended ? 8 : 3) }}</span>
        </h2>
      </div>
      <div class="ne-actions">
        <button v-for="a in add" :key="a.label" class="small" @click="a.run()">+ {{ a.label }}</button>
        <template v-if="isListItem && !readonly">
          <button class="icon" :title="t('Выше')" @click="moveNode(path, -1)">↑</button>
          <button class="icon" :title="t('Ниже')" @click="moveNode(path, 1)">↓</button>
          <button class="icon" :title="t('Дублировать')" @click="duplicateNode(path)">⧉</button>
          <button class="icon danger" :title="t('Удалить (Delete)')" @click="removeNode(path)">✕</button>
        </template>
      </div>
    </header>

    <div v-for="d in ownDiags" :key="d.code + d.message" class="banner" :class="d.level">
      <b>{{ d.code }}</b>: {{ d.message }}
    </div>

    <!-- Битовая карта для кадра, сигнала, флага -->
    <section v-if="rframe && rframe.dlc > 0 && ['frame', 'signal', 'flag', 'sdo'].includes(kind)" class="card">
      <h3>{{ t("Раскладка кадра") }} <span class="muted">{{ frameData?.name }} · DLC {{ rframe.dlc }}</span></h3>
      <BitGrid :frame="rframe" :selected="path" :palette="store.state.palette" :readonly="readonly"
               v-model:mux-value="muxValue"
               @select="actions.select" @create="onCreate" @layout="onLayout" />
    </section>

    <section v-if="kind !== 'history'" class="card">
      <h3>{{ t("Свойства") }}</h3>
      <div class="form-grid">
        <!-- позиция сигнала -->
        <template v-if="kind === 'signal' && rsignal">
          <label class="field" :class="layoutDiags[0]?.level">
            <span class="field-label"><HelpTip :text="HELP['layout.start_bit']" />{{ t("Начальный бит (LSB)") }}</span>
            <input class="mono" :value="rsignal.start_bit" :readonly="readonly || rsignal.synthetic" @change="setLayout('start_bit', $event)" />
            <span v-if="inputErrors.start_bit" class="field-msg error">{{ inputErrors.start_bit }}</span>
          </label>
          <label class="field" :class="layoutDiags[0]?.level">
            <span class="field-label"><HelpTip :text="HELP['layout.bit_length']" />{{ t("Длина, бит") }}</span>
            <input class="mono" :value="rsignal.bit_length" :readonly="readonly || rsignal.synthetic" @change="setLayout('bit_length', $event)" />
            <span v-if="inputErrors.bit_length" class="field-msg error">{{ inputErrors.bit_length }}</span>
            <span class="field-hint">
              {{ t("байты {bytes}, биты {bits}", {
                bytes: rangeLabel(Math.floor(Math.min(...rsignal.occupied) / 8), Math.floor(Math.max(...rsignal.occupied) / 8)),
                bits: rangeLabel(Math.min(...rsignal.occupied), Math.max(...rsignal.occupied)) }) }}
            </span>
            <span v-for="d in layoutDiags" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
          </label>
        </template>

        <!-- режим передачи кадра -->
        <template v-if="kind === 'frame'">
          <label class="field">
            <span class="field-label"><HelpTip :text="HELP['layout.mode']" />{{ t("Передача") }}</span>
            <select :value="txMode" :disabled="readonly" @change="setMode">
              <option value="">{{ t("не указано") }}</option>
              <option value="cyclic">{{ t("циклически") }}</option>
              <option value="event">{{ t("по событию") }}</option>
              <option value="on_request">{{ t("по запросу") }}</option>
            </select>
          </label>
          <label v-if="txMode === 'cyclic'" class="field">
            <span class="field-label"><HelpTip :text="HELP['layout.cycle_ms']" />{{ t("Период, мс") }}</span>
            <input class="mono" :value="txCycle ?? ''" :readonly="readonly" @change="setCycle" />
            <span v-if="inputErrors.cycle_ms" class="field-msg error">{{ inputErrors.cycle_ms }}</span>
          </label>
        </template>

        <FieldInput v-for="def in fields" :key="path.join('/') + def.key" :def="def" :value="shownValue(def)"
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
      <h3>{{ t("Сигналы") }} <span class="muted">{{ frameSignals.length }}</span></h3>
      <table v-if="frameSignals.length" class="list">
        <thead><tr><th></th><th>{{ t("Сигнал") }}</th><th>{{ t("Биты") }}</th><th>{{ t("Тип") }}</th><th>{{ t("Описание") }}</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in frameSignals" :key="r.s.name" class="clickable"
              @click="actions.select(r.s.synthetic ? path : r.s.path)">
            <td><span class="swatch" :style="{ background: store.state.palette[i % store.state.palette.length] }" /></td>
            <td class="mono">{{ r.s.name }}<span v-if="r.s.synthetic" class="muted"> (SDO)</span></td>
            <td class="mono">{{ r.bits }}</td>
            <td>{{ r.s.kind }}<span v-if="r.s.mux" class="muted"> · mux {{ r.s.mux.join(", ") }}</span></td>
            <td>{{ r.desc }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted">{{ t("Сигналов нет. Протяните мышью по битам в раскладке выше или нажмите «+ Сигнал».") }}</p>
    </section>

    <!-- Кадры устройства / шины -->
    <section v-if="childFrames.length" class="card">
      <h3>{{ t("Кадры") }}</h3>
      <table class="list">
        <thead><tr><th>ID</th><th>{{ t("Кадр") }}</th><th>{{ t("Тип") }}</th><th>{{ t("Сигналов") }}</th><th>{{ t("Описание") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="f in childFrames" :key="f.name" class="clickable" @click="actions.select(f.path)">
            <td class="mono">{{ f.id }}</td><td class="mono">{{ f.name }}</td><td>{{ f.type }}</td>
            <td>{{ f.n }}</td><td>{{ f.desc }}</td>
            <td v-if="!readonly" class="act"><button class="icon danger" :title="t('Удалить')" @click.stop="removeNode(f.path)">✕</button></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="devices.length" class="card">
      <h3>{{ t("Устройства") }}</h3>
      <table class="list">
        <thead><tr><th>{{ t("Устройство") }}</th><th>node_id</th><th>{{ t("Название") }}</th><th>{{ t("Кадров") }}</th></tr></thead>
        <tbody>
          <tr v-for="(d, i) in devices" :key="d.name" class="clickable" @click="actions.select([...path, 'devices', i])">
            <td class="mono">{{ d.short ? d.short + " · " : "" }}{{ d.name }}</td>
            <td class="mono">{{ d.node_id != null ? hex(d.node_id, 2) : "—" }}</td>
            <td>{{ txt(d.title, lang) }}</td><td>{{ d.frames?.length ?? 0 }}</td>
          </tr>
        </tbody>
      </table>
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
