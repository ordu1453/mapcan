<script setup lang="ts">
// Интерактивная битовая карта кадра: DLC строк × 8 бит (бит 7 слева, как в документах).
//  * протяжка по свободным битам — новый сигнал;
//  * перетаскивание выбранного сигнала — сдвиг;
//  * ручки на младшем/старшем бите (little-endian) — изменение длины.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { coexist, occupiedBits, rangeLabel } from "../bits";
import { samePath, startsWith } from "../model";
import type { Path, ResolvedFrame, ResolvedSignal } from "../types";
import { t } from "../i18n";

const props = defineProps<{
  frame: ResolvedFrame;
  selected: Path;
  palette: string[];
  readonly?: boolean;
  muxValue: number | null;
}>();
const emit = defineEmits<{
  select: [path: Path];
  layout: [path: Path, start: number, length: number];
  create: [start: number, length: number];
  "update:muxValue": [value: number | null];
}>();

type Drag =
  | { mode: "create"; anchor: number; cur: number }
  | { mode: "move"; sig: ResolvedSignal; grab: number; cur: number }
  | { mode: "resize"; sig: ResolvedSignal; edge: "lo" | "hi"; cur: number };

const drag = ref<Drag | null>(null);
const hover = ref<number | null>(null);

const nbits = computed(() => props.frame.dlc * 8);

const selector = computed(() => props.frame.signals.find((s) => s.multiplexer) ?? null);
const muxOptions = computed(() => {
  const sel = selector.value;
  if (!sel) return [];
  const vals = new Map<number, string>();
  for (const v of sel.values) vals.set(v.value, v.name);
  for (const s of props.frame.signals) for (const m of s.mux ?? []) if (!vals.has(m)) vals.set(m, "");
  return [...vals.entries()].sort((a, b) => a[0] - b[0]);
});

function visible(s: ResolvedSignal): boolean {
  return props.muxValue === null || s.mux === null || s.mux.includes(props.muxValue);
}

const selectedSignal = computed(() =>
  props.frame.signals.find((s) => startsWith(props.selected, s.path) && !s.synthetic) ?? null,
);
const selectedFlag = computed(() => {
  const s = selectedSignal.value;
  if (!s || props.selected.length !== s.path.length + 2) return null;
  return s.flags[Number(props.selected[s.path.length + 1])] ?? null;
});

/** Биты, которые займёт сигнал при текущем перетаскивании. */
const preview = computed<{ start: number; length: number; bits: Set<number> } | null>(() => {
  const d = drag.value;
  if (!d) return null;
  let start: number;
  let length: number;
  let be = false;
  if (d.mode === "create") {
    start = Math.min(d.anchor, d.cur);
    length = Math.abs(d.cur - d.anchor) + 1;
  } else if (d.mode === "move") {
    be = d.sig.byte_order === "big_endian";
    start = d.sig.start_bit + (d.cur - d.grab);
    length = d.sig.bit_length;
  } else {
    const lo = d.sig.start_bit;
    const hi = d.sig.start_bit + d.sig.bit_length - 1;
    if (d.edge === "lo") {
      start = Math.min(d.cur, hi);
      length = hi - start + 1;
    } else {
      start = lo;
      length = Math.max(d.cur, lo) - lo + 1;
    }
  }
  if (start < 0) return null;
  return { start, length, bits: new Set(occupiedBits(start, length, be)) };
});

interface Cell {
  bit: number;
  owners: ResolvedSignal[];
  flag: string | null;
  /** Номер флага в битовом поле (для чередования оттенков); null — не флаг или бит поля вне флагов. */
  flagIndex: number | null;
  /** Бит битового поля с флагами (единственный владелец). */
  inField: boolean;
  conflict: boolean;
}

const cells = computed<Cell[]>(() => {
  const out: Cell[] = [];
  const dragged = drag.value && drag.value.mode !== "create" ? drag.value.sig : null;
  for (let bit = 0; bit < nbits.value; bit++) {
    const owners = props.frame.signals.filter(
      (s) => visible(s) && s.occupied.includes(bit) && !(dragged && samePath(s.path, dragged.path)),
    );
    let flag: string | null = null;
    let flagIndex: number | null = null;
    const inField = owners.length === 1 && owners[0].flags.length > 0;
    if (inField) {
      flagIndex = owners[0].flags.findIndex((f) => f.occupied.includes(bit));
      if (flagIndex < 0) flagIndex = null;
      else flag = owners[0].flags[flagIndex].name;
    }
    let conflict = false;
    for (let i = 0; i < owners.length && !conflict; i++)
      for (let j = 0; j < i; j++) if (coexist(owners[i].mux, owners[j].mux)) conflict = true;
    out.push({ bit, owners, flag, flagIndex, inField, conflict });
  }
  return out;
});

function colorOf(s: ResolvedSignal): string {
  const i = props.frame.signals.indexOf(s);
  return props.palette[i % props.palette.length] ?? "#ccc";
}

interface Segment {
  row: number;
  col: number;
  span: number;
  label: string;
  title: string;
  color: string;
  conflict: boolean;
  selected: boolean;
  /** Подпись флага на плашке битового поля (сдвинута вниз под имя поля). */
  onPill: boolean;
}

/** Подписи: подряд идущие биты строки с одинаковым владельцем объединяются. */
const segments = computed<Segment[]>(() => {
  const out: Segment[] = [];
  for (let row = 0; row < props.frame.dlc; row++) {
    let col = 0;
    while (col < 8) {
      const c = cells.value[row * 8 + (7 - col)];
      const key = c.owners.map((s) => s.name).join("|") + "#" + (c.flag ?? "");
      let span = 1;
      while (col + span < 8) {
        const n = cells.value[row * 8 + (7 - col - span)];
        if (n.owners.map((s) => s.name).join("|") + "#" + (n.flag ?? "") !== key) break;
        span++;
      }
      if (c.owners.length) {
        const sel = selectedSignal.value;
        out.push({
          row, col, span,
          // Биты поля вне флагов — без подписи: имя поля и так написано над плашками
          label: c.flag ?? (c.inField ? "" : c.owners.map((s) => s.name).join(" | ")),
          title: c.inField ? `${c.owners[0].name} · ${c.flag ?? "—"}` : c.owners.map((s) => s.name).join(" | "),
          color: colorOf(c.owners[0]),
          conflict: c.conflict,
          selected: !!sel && c.owners.some((s) => samePath(s.path, sel.path)),
          onPill: c.inField,
        });
      }
      col += span;
    }
  }
  return out;
});

/** Имя битового поля над плашками: подряд идущие биты строки одного поля. */
const fieldSegments = computed<Array<{ row: number; col: number; span: number; label: string }>>(() => {
  const out: Array<{ row: number; col: number; span: number; label: string }> = [];
  for (let row = 0; row < props.frame.dlc; row++) {
    let col = 0;
    while (col < 8) {
      const c = cells.value[row * 8 + (7 - col)];
      let span = 1;
      if (c.inField) {
        while (col + span < 8 && samePlace(c, cells.value[row * 8 + (7 - col - span)])) span++;
        out.push({ row, col, span, label: c.owners[0].name });
      }
      col += span;
    }
  }
  return out;
});

const samePlace = (a: Cell, b: Cell | undefined) => !!b && b.inField && samePath(a.owners[0].path, b.owners[0].path);
/** Тот же флаг (или тот же участок поля вне флагов) — ячейки сливаются в одну плашку. */
const samePill = (a: Cell, b: Cell | undefined) => samePlace(a, b) && b!.flagIndex === a.flagIndex;

/** Края плашки: слева в сетке — старший бит того же байта, на границе байта плашка всегда закрыта. */
function pillEdges(c: Cell) {
  if (!c.inField) return {};
  const left = c.bit % 8 === 7 ? undefined : cells.value[c.bit + 1];
  const right = c.bit % 8 === 0 ? undefined : cells.value[c.bit - 1];
  return { "field-bit": true, "no-flag": c.flagIndex === null, "pill-l": !samePill(c, left), "pill-r": !samePill(c, right) };
}

function cellClass(c: Cell) {
  const sel = selectedSignal.value;
  const isSel = !!sel && c.owners.some((s) => samePath(s.path, sel.path));
  const flagSel = selectedFlag.value?.occupied.includes(c.bit) ?? false;
  const p = preview.value;
  return {
    empty: !c.owners.length,
    conflict: c.conflict,
    selected: isSel,
    "flag-selected": flagSel,
    preview: !!p && p.bits.has(c.bit),
    "preview-bad": !!p && p.bits.has(c.bit) && (c.owners.length > 0 || c.bit >= nbits.value),
    synthetic: c.owners.length > 0 && c.owners.every((s) => s.synthetic),
    ...pillEdges(c),
  };
}

/** Обычный сигнал — заливка ячейки; битовое поле — плашки флагов (::before) цвета сигнала. */
function cellStyle(c: Cell) {
  if (!c.owners.length) return {};
  return c.inField ? { "--sig": colorOf(c.owners[0]) } : { background: colorOf(c.owners[0]) };
}

/** Ручки изменения длины в ячейке; у однобитного сигнала обе в одной ячейке. */
function handles(c: Cell): Array<"lo" | "hi"> {
  const s = selectedSignal.value;
  if (!s || props.readonly || s.byte_order === "big_endian") return [];
  const out: Array<"lo" | "hi"> = [];
  if (c.bit === s.start_bit) out.push("lo");
  if (c.bit === s.start_bit + s.bit_length - 1) out.push("hi");
  return out;
}

function onDown(c: Cell, e: MouseEvent) {
  if (e.button !== 0) return;
  e.preventDefault();
  const sel = selectedSignal.value;
  const hs = handles(c);
  // Крайняя ячейка многобитного сигнала — ручка целиком; у однобитного — только сама ручка, иначе сдвиг
  const grip = (e.target as HTMLElement).dataset?.edge as "lo" | "hi" | undefined;
  const h = hs.length === 1 ? hs[0] : grip && hs.includes(grip) ? grip : null;
  if (h && sel) {
    drag.value = { mode: "resize", sig: sel, edge: h, cur: c.bit };
    return;
  }
  const own = c.owners.find((s) => sel && samePath(s.path, sel.path)) ?? c.owners[0];
  if (own) {
    emit("select", own.synthetic ? props.frame.path : own.path);
    if (!props.readonly && !own.synthetic) drag.value = { mode: "move", sig: own, grab: c.bit, cur: c.bit };
    return;
  }
  if (!props.readonly) drag.value = { mode: "create", anchor: c.bit, cur: c.bit };
}

function onEnter(c: Cell) {
  hover.value = c.bit;
  if (drag.value) drag.value.cur = c.bit;
}

function onUp() {
  const d = drag.value;
  const p = preview.value;
  drag.value = null;
  if (!d || !p) return;
  if (d.mode === "create") {
    emit("create", p.start, p.length);
  } else if (d.mode === "move") {
    if (d.cur !== d.grab) emit("layout", d.sig.path, p.start, p.length);
  } else if (p.start !== d.sig.start_bit || p.length !== d.sig.bit_length) {
    emit("layout", d.sig.path, p.start, p.length);
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") drag.value = null;
}

onMounted(() => {
  window.addEventListener("mouseup", onUp);
  window.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  window.removeEventListener("mouseup", onUp);
  window.removeEventListener("keydown", onKey);
});

const status = computed(() => {
  const p = preview.value;
  const d = drag.value;
  if (p && d) {
    const verb = d.mode === "create" ? t("New signal") : d.mode === "move" ? t("Move") : t("Length");
    return t("{verb}: bits {bits} ({n} bits)", { verb, bits: rangeLabel(p.start, p.start + p.length - 1), n: p.length });
  }
  if (hover.value !== null) {
    const b = hover.value;
    const c = cells.value[b];
    const who = c?.owners.map((s) => s.name).join(", ");
    return t("bit {bit} — byte {byte}, bit {inbyte}", { bit: b, byte: Math.floor(b / 8), inbyte: b % 8 })
      + (who ? " · " + who : "") + (c?.flag ? " · " + c.flag : "");
  }
  return props.readonly
    ? t("View only")
    : t("Drag across free bits to add a signal. Drag a signal to move it, drag its edge to resize.");
});
</script>

<template>
  <div class="bitgrid-wrap">
    <div v-if="muxOptions.length" class="mux-bar">
      <span class="muted">{{ t("Selector") }} <b>{{ selector?.name }}</b>:</span>
      <button :class="{ active: muxValue === null }" @click="emit('update:muxValue', null)">{{ t("All") }}</button>
      <button v-for="[v, n] in muxOptions" :key="v" :class="{ active: muxValue === v }"
              @click="emit('update:muxValue', v)">{{ v }}{{ n ? " · " + n : "" }}</button>
    </div>

    <div class="bitgrid" :style="{ gridTemplateRows: `26px repeat(${frame.dlc}, 34px)` }" @mouseleave="hover = null">
      <div class="bg-head corner">{{ t("Byte") }}</div>
      <div v-for="b in 8" :key="'h' + b" class="bg-head" :style="{ gridColumn: b + 1, gridRow: 1 }">{{ 8 - b }}</div>

      <template v-for="row in frame.dlc" :key="'r' + row">
        <div class="bg-byte" :style="{ gridRow: row + 1 }">{{ row - 1 }}</div>
      </template>

      <div v-for="c in cells" :key="c.bit" class="bg-cell" :class="cellClass(c)" :style="{
             ...cellStyle(c), gridRow: Math.floor(c.bit / 8) + 2, gridColumn: 9 - (c.bit % 8) }"
           :title="t('bit {bit}', { bit: c.bit })" @mousedown="onDown(c, $event)" @mouseenter="onEnter(c)">
        <span v-for="h in handles(c)" :key="h" class="grip" :class="h" :data-edge="h" />
      </div>

      <div v-for="(f, i) in fieldSegments" :key="'f' + i" class="bg-field-label"
           :style="{ gridRow: f.row + 2, gridColumn: `${f.col + 2} / span ${f.span}` }">
        <span>{{ f.label }}</span>
      </div>

      <div v-for="(s, i) in segments" :key="'s' + i" class="bg-label"
           :class="{ conflict: s.conflict, selected: s.selected && !s.onPill, 'on-pill': s.onPill }"
           :title="s.title" :style="{ gridRow: s.row + 2, gridColumn: `${s.col + 2} / span ${s.span}` }">
        <span>{{ s.label }}</span>
      </div>
    </div>
    <div class="bitgrid-status muted">{{ status }}</div>
  </div>
</template>
