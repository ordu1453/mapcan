<script setup lang="ts">
// Interactive bit map of a frame: DLC rows × 8 bits (bit 7 on the left, as in the documents).
//  * dragging over two or more free bits, or a double click on one: a new signal (a click alone makes none);
//  * dragging the selected signal: moving it;
//  * handles on the least/most significant bit (little-endian): changing the length;
//  * in the selected bit field, a flag is selected by a click, moved by dragging and resized at its edges; Alt+drag
//    moves the whole field (#150).
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { coexist, occupiedBits, rangeLabel } from "../bits";
import { flagFits, samePath, startsWith } from "../model";
import type { Path, ResolvedFlag, ResolvedFrame, ResolvedSignal } from "../types";
import { t } from "../i18n";

const props = defineProps<{
  frame: ResolvedFrame;
  selected: Path;
  palette: string[];
  readonly?: boolean;
  muxValue: number | null;
  /** The frame is CANopen: what it carries is called objects (#151). */
  objects?: boolean;
}>();
const emit = defineEmits<{
  select: [path: Path];
  layout: [path: Path, start: number, length: number];
  create: [start: number, length: number];
  /** A flag moved or resized: its first bit and length in the field. */
  flag: [path: Path, bit: number, length: number];
  "update:muxValue": [value: number | null];
}>();

type Drag =
  | { mode: "create"; anchor: number; cur: number }
  | { mode: "move"; sig: ResolvedSignal; grab: number; cur: number }
  | { mode: "resize"; sig: ResolvedSignal; edge: "lo" | "hi"; cur: number }
  // A flag of the selected field: grab is the bit of the field it is taken at
  | { mode: "flag"; sig: ResolvedSignal; flag: ResolvedFlag; index: number; grab: number; cur: number }
  | { mode: "flagsize"; sig: ResolvedSignal; flag: ResolvedFlag; index: number; edge: "lo" | "hi"; cur: number };

const drag = ref<Drag | null>(null);
const hover = ref<number | null>(null);

const nbits = computed(() => props.frame.length * 8);

// The selector is a signal or a field of a bit field (#149): its name and value table
const selector = computed<{ name: string; values: { value: number; name: string }[] } | null>(() => {
  for (const s of props.frame.signals) {
    if (s.multiplexer) return s;
    const f = s.flags.find((x) => x.multiplexer);
    if (f) return f;
  }
  return null;
});
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
const selectedFlagIndex = computed(() => {
  const s = selectedSignal.value;
  return s && props.selected.length === s.path.length + 2 ? Number(props.selected[s.path.length + 1]) : null;
});
const selectedFlag = computed(() =>
  (selectedFlagIndex.value === null ? null : selectedSignal.value?.flags[selectedFlagIndex.value] ?? null));

/** Bit of the field (0: its LSB) at a bit of the frame; -1 outside the field. */
const fieldBit = (s: ResolvedSignal, bit: number) => s.occupied.indexOf(bit);

/** Where a flag being dragged goes, in bits of its field. */
const flagPlace = computed<{ bit: number; length: number } | null>(() => {
  const d = drag.value;
  if (d?.mode === "flag") {
    const at = fieldBit(d.sig, d.cur);
    return at < 0 ? null : { bit: d.flag.bit + at - d.grab, length: d.flag.bit_length };
  }
  if (d?.mode === "flagsize") {
    const at = fieldBit(d.sig, d.cur);
    if (at < 0) return null;
    const lo = d.flag.bit;
    const hi = d.flag.bit + d.flag.bit_length - 1;
    return d.edge === "lo" ? { bit: Math.min(at, hi), length: hi - Math.min(at, hi) + 1 }
      : { bit: lo, length: Math.max(at, lo) - lo + 1 };
  }
  return null;
});

/** Bits the signal will take during the current drag. */
const preview = computed<{ start: number; length: number; bits: Set<number>; bad?: boolean } | null>(() => {
  const d = drag.value;
  if (!d) return null;
  if (d.mode === "flag" || d.mode === "flagsize") {
    const f = flagPlace.value;
    if (!f) return null;
    const bits = d.sig.occupied.slice(Math.max(f.bit, 0), f.bit + f.length);
    return { start: f.bit, length: f.length, bits: new Set(bits),
      bad: !flagFits(d.sig.flags, d.index, f.bit, f.length, d.sig.bit_length) };
  }
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
  /** Number of the flag in the bit field (to alternate shades); null: not a flag, or a bit of the field outside the flags. */
  flagIndex: number | null;
  /** A bit of a bit field with flags (its only owner). */
  inField: boolean;
  conflict: boolean;
}

const cells = computed<Cell[]>(() => {
  const out: Cell[] = [];
  const dragged = drag.value && (drag.value.mode === "move" || drag.value.mode === "resize") ? drag.value.sig : null;
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
  /** Label of a flag on the bit field's bar (moved down below the field's name). */
  onPill: boolean;
}

/** Labels: consecutive bits of a row with the same owner are merged. */
const segments = computed<Segment[]>(() => {
  const out: Segment[] = [];
  for (let row = 0; row < props.frame.length; row++) {
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
          // Bits of the field outside the flags have no label: the field's name is written above the bars anyway
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

/** Name of the bit field above the bars: consecutive bits of a row of one field. */
const fieldSegments = computed<Array<{ row: number; col: number; span: number; label: string; mine: boolean }>>(() => {
  const out: Array<{ row: number; col: number; span: number; label: string; mine: boolean }> = [];
  const sel = selectedSignal.value;
  for (let row = 0; row < props.frame.length; row++) {
    let col = 0;
    while (col < 8) {
      const c = cells.value[row * 8 + (7 - col)];
      let span = 1;
      if (c.inField) {
        while (col + span < 8 && samePlace(c, cells.value[row * 8 + (7 - col - span)])) span++;
        out.push({ row, col, span, label: c.owners[0].name, mine: !!sel && samePath(c.owners[0].path, sel.path) });
      }
      col += span;
    }
  }
  return out;
});

const samePlace = (a: Cell, b: Cell | undefined) => !!b && b.inField && samePath(a.owners[0].path, b.owners[0].path);
/** The same flag (or the same part of the field outside the flags): the cells merge into one bar. */
const samePill = (a: Cell, b: Cell | undefined) => samePlace(a, b) && b!.flagIndex === a.flagIndex;

/** Edges of the bar: left in the grid is the higher bit of the same byte; at a byte boundary the bar is always closed. */
function pillEdges(c: Cell) {
  if (!c.inField) return {};
  const left = c.bit % 8 === 7 ? undefined : cells.value[c.bit + 1];
  const right = c.bit % 8 === 0 ? undefined : cells.value[c.bit - 1];
  return { "field-bit": true, "no-flag": c.flagIndex === null, "pill-l": !samePill(c, left), "pill-r": !samePill(c, right) };
}

/** Bits of the selected signal shown in the grid: with a selection, the other signals are dimmed. */
const selectedBits = computed(() => {
  const s = selectedSignal.value;
  return new Set(s && visible(s) ? s.occupied : []);
});

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
    "preview-bad": !!p && p.bits.has(c.bit) && (p.bad ?? (c.owners.length > 0 || c.bit >= nbits.value)),
    synthetic: c.owners.length > 0 && c.owners.every((s) => s.synthetic),
    ...pillEdges(c),
  };
}

/** A plain signal fills the cell; a bit field gets bars of its flags (::before) in the signal's color. */
function cellStyle(c: Cell) {
  if (!c.owners.length) return {};
  const sig = colorOf(c.owners[0]);
  return c.inField ? { "--sig": sig } : { "--sig": sig, background: sig };
}

/** Length handles in the cell; a one-bit signal has both in one cell. */
function handles(c: Cell): Array<"lo" | "hi"> {
  const s = selectedSignal.value;
  if (!s || props.readonly) return [];
  // The selected flag is resized at its first and last bit of the field
  const f = selectedFlag.value;
  if (f) {
    const out: Array<"lo" | "hi"> = [];
    if (c.bit === f.occupied[0]) out.push("lo");
    if (c.bit === f.occupied[f.occupied.length - 1]) out.push("hi");
    return out;
  }
  if (s.byte_order === "big_endian") return [];
  const out: Array<"lo" | "hi"> = [];
  if (c.bit === s.start_bit) out.push("lo");
  if (c.bit === s.start_bit + s.bit_length - 1) out.push("hi");
  return out;
}

function onDown(c: Cell, e: MouseEvent) {
  if (e.button !== 0) return;
  // A form field being typed in is committed first, to the node it belongs to: preventDefault below would keep
  // its focus while the click selects another node
  const active = document.activeElement as HTMLElement | null;
  if (active && active.matches("input, textarea, select")) active.blur();
  e.preventDefault();
  const sel = selectedSignal.value;
  const hs = handles(c);
  // The length changes at the edge of an end bit (the handle, shown by the cursor); the rest of the signal moves it
  const grip = (e.target as HTMLElement).dataset?.edge as "lo" | "hi" | undefined;
  const h = grip && hs.includes(grip) ? grip : null;
  const flag = selectedFlag.value;
  if (h && sel && flag) {
    drag.value = { mode: "flagsize", sig: sel, flag, index: selectedFlagIndex.value!, edge: h, cur: c.bit };
    return;
  }
  if (h && sel) {
    drag.value = { mode: "resize", sig: sel, edge: h, cur: c.bit };
    return;
  }
  // A flag of the selected field: the first click selects it, the selected one is moved by dragging. Alt+drag and
  // the bits of the field outside the flags move the whole field.
  if (sel && c.inField && samePath(c.owners[0].path, sel.path) && c.flagIndex !== null && !e.altKey) {
    const flagPath = [...sel.path, "flags", c.flagIndex];
    if (!samePath(props.selected, flagPath)) emit("select", flagPath);
    else if (!props.readonly) {
      drag.value = { mode: "flag", sig: sel, flag: sel.flags[c.flagIndex], index: c.flagIndex,
        grab: fieldBit(sel, c.bit), cur: c.bit };
    }
    return;
  }
  const own = c.owners.find((s) => sel && samePath(s.path, sel.path)) ?? c.owners[0];
  if (own) {
    // The first click only selects a signal; the selected one is moved by dragging (a stray click moves nothing)
    if (!startsWith(props.selected, own.path)) {
      emit("select", own.synthetic ? props.frame.path : own.path);
      return;
    }
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
  if (d.mode === "flag" || d.mode === "flagsize") {
    if (!p.bad && (p.start !== d.flag.bit || p.length !== d.flag.bit_length)) {
      emit("flag", [...d.sig.path, "flags", d.index], p.start, p.length);
    }
    return;
  }
  if (d.mode === "create") {
    // A click on a free bit makes no signal (a double click does): it only leaves the selected one
    if (p.length >= 2) emit("create", p.start, p.length);
    else emit("select", props.frame.path);
  } else if (d.mode === "move") {
    if (d.cur !== d.grab) emit("layout", d.sig.path, p.start, p.length);
  } else if (p.start !== d.sig.start_bit || p.length !== d.sig.bit_length) {
    emit("layout", d.sig.path, p.start, p.length);
  }
}

function onDouble(c: Cell) {
  if (!props.readonly && !c.owners.length) emit("create", c.bit, 1);
}

function onKey(e: KeyboardEvent) {
  // Esc cancels a drag (and does not also leave the node)
  if (e.key === "Escape" && drag.value) {
    drag.value = null;
    e.preventDefault();
  }
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
    if (d.mode === "flag" || d.mode === "flagsize") {
      return t("Flag {name}: bits {bits} of the field", { name: d.flag.name, bits: rangeLabel(p.start, p.start + p.length - 1) })
        + (p.bad ? " · " + t("does not fit: outside the field or over another flag") : "");
    }
    const verb = d.mode === "create" ? (props.objects ? t("New object") : t("New signal")) : d.mode === "move" ? t("Move") : t("Length");
    return t("{verb}: bits {bits} ({n} bits)", { verb, bits: rangeLabel(p.start, p.start + p.length - 1), n: p.length });
  }
  if (hover.value !== null) {
    const b = hover.value;
    const c = cells.value[b];
    const who = c?.owners.map((s) => s.name).join(", ");
    return t("bit {bit} — byte {byte}, bit {inbyte}", { bit: b, byte: Math.floor(b / 8), inbyte: b % 8 })
      + (who ? " · " + who : "") + (c?.flag ? " · " + c.flag : "");
  }
  if (!props.readonly && selectedSignal.value?.flags.length) {
    return t("Click a flag to select it, drag the selected flag to move it, its edge to resize. Alt+drag moves the whole field.");
  }
  return props.readonly
    ? t("View only")
    : props.objects
      ? t("Drag across two or more free bits to add an object (double-click: one bit). Drag an object to move it, its edge to resize.")
      : t("Drag across two or more free bits to add a signal (double-click: one bit). Drag a signal to move it, its edge to resize.");
});
</script>

<template>
  <div class="bitgrid-wrap">
    <div class="bitgrid" :class="{ 'has-selection': selectedBits.size > 0 }"
         :style="{ gridTemplateRows: `26px repeat(${frame.length}, 34px)` }" @mouseleave="hover = null">
      <div class="bg-head corner">{{ t("Byte") }}</div>
      <div v-for="b in 8" :key="'h' + b" class="bg-head" :style="{ gridColumn: b + 1, gridRow: 1 }">{{ 8 - b }}</div>

      <template v-for="row in frame.length" :key="'r' + row">
        <div class="bg-byte" :style="{ gridRow: row + 1 }">{{ row - 1 }}</div>
      </template>

      <div v-for="c in cells" :key="c.bit" class="bg-cell" :class="cellClass(c)" :style="{
             ...cellStyle(c), gridRow: Math.floor(c.bit / 8) + 2, gridColumn: 9 - (c.bit % 8) }"
           :title="t('bit {bit}', { bit: c.bit })" @mousedown="onDown(c, $event)" @dblclick="onDouble(c)" @mouseenter="onEnter(c)">
        <span v-for="h in handles(c)" :key="h" class="grip" :class="h" :data-edge="h" />
      </div>

      <div v-for="(f, i) in fieldSegments" :key="'f' + i" class="bg-field-label" :class="{ mine: f.mine }"
           :style="{ gridRow: f.row + 2, gridColumn: `${f.col + 2} / span ${f.span}` }">
        <span>{{ f.label }}</span>
      </div>

      <div v-for="(s, i) in segments" :key="'s' + i" class="bg-label"
           :class="{ conflict: s.conflict, selected: s.selected && !s.onPill, mine: s.selected, 'on-pill': s.onPill }"
           :title="s.title" :style="{ gridRow: s.row + 2, gridColumn: `${s.col + 2} / span ${s.span}` }">
        <span>{{ s.label }}</span>
      </div>
    </div>
    <div class="bitgrid-status muted">{{ status }}</div>
    <!-- Under the grid: the grid starts right under the heading's Bits tab -->
    <div v-if="muxOptions.length" class="mux-bar">
      <span class="muted">{{ t("Selector") }} <b>{{ selector?.name }}</b>:</span>
      <button :class="{ active: muxValue === null }" @click="emit('update:muxValue', null)">{{ t("All") }}</button>
      <button v-for="[v, n] in muxOptions" :key="v" :class="{ active: muxValue === v }"
              @click="emit('update:muxValue', v)">{{ v }}{{ n ? " · " + n : "" }}</button>
    </div>
  </div>
</template>
