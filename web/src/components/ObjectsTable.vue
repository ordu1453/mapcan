<script setup lang="ts">
// Object dictionary of a CANopen device (#151): the objects of its PDOs and SDO exchanges by index, an array or a
// record opened to its subindices. Here indices and subindices are given; the object itself is edited in its frame
// (a click on its name goes there).
import { computed, ref } from "vue";
import { hex } from "../bits";
import { parseInput, ParseError } from "@mapcan/forms";
import { deviceObjects, getAt, samePath, startsWith, type OdEntry, type OdObject } from "../model";
import { actions, lang, resolvedFrames, store, toast, viewData } from "../store";
import type { Diagnostic, Op, Path } from "../types";
import { N_, t } from "../i18n";

const props = defineProps<{ device: Path }>();

const TYPE_LABEL: Record<string, string> = { var: "VAR", array: "ARRAY", record: "RECORD" };
const VIA_LABEL: Record<string, string> = { pdo: "PDO", sdo: "SDO" };
const VIA_HELP: Record<string, string> = {
  pdo: N_("mapped into a PDO"), sdo: N_("read or written by an SDO exchange"),
};

const readonly = computed(() => !!store.state?.readonly);
const objects = computed<OdObject[]>(() =>
  deviceObjects(getAt(viewData.value, props.device), props.device, resolvedFrames.value, lang.value));
const indexed = computed(() => objects.value.filter((o) => o.index !== null));
const unassigned = computed(() => objects.value.filter((o) => o.index === null));

const grouped = (o: OdObject) => o.type === "array" || o.type === "record";
const open = ref(new Set<number>());
function toggle(index: number) {
  const s = new Set(open.value);
  if (s.has(index)) s.delete(index);
  else s.add(index);
  open.value = s;
}

const unique = (xs: string[]) => [...new Set(xs.filter(Boolean))];
const frames = (o: OdObject) => unique(o.entries.map((e) => `${e.canId} ${e.frameLabel}`.trim()));
const vias = (o: OdObject) => unique(o.entries.map((e) => (e.via ? VIA_LABEL[e.via] : "")));

// Validation messages about the index or subindex of an entry (a duplicate object, an index outside the areas)
function entryDiags(e: OdEntry): Diagnostic[] {
  return (store.state?.diagnostics ?? []).filter((d) => d.level !== "info"
    && (startsWith(d.node, [...e.path, "index"]) || startsWith(d.node, [...e.path, "subindex"])));
}
function level(ds: Diagnostic[]): string {
  return ds.some((d) => d.level === "error") ? "error" : ds.some((d) => d.level === "warning") ? "warning" : "";
}
const objectDiags = (o: OdObject) => o.entries.flatMap(entryDiags);

/** The number typed in a cell, in [0, max]; undefined (and the cell back as it was) when it is not one. */
function read(e: Event, max: number, old: number | null): number | null | undefined {
  const el = e.target as HTMLInputElement;
  try {
    const v = parseInput("hex", el.value) as number | null;
    if (v === null || (v >= 0 && v <= max)) return v;
    toast(t("“{raw}” must be between {min} and {max}", { raw: el.value.trim(), min: 0, max: hex(max, 2) }));
  } catch (err) {
    toast(err instanceof ParseError ? err.message : String(err));
  }
  el.value = cell(old, max > 0xff ? 4 : 2);
  return undefined;
}

const cell = (v: number | null, width: number) => (v === null ? "" : hex(v, width));

// Subindex 0 of an array or a record holds the number of its entries (CiA 301): a signal does not take it, an SDO
// exchange may read it (the rule od-subindex-zero)
const ZERO_TAKEN = N_("Subindex 0x00 of an array or a record holds the number of its entries: give the object a subindex from 0x01");

/** The entry would be a signal at subindex 0 of `index` while that index has entries from subindex 1 (the entries
 * `moving` go along and do not count as already there). */
function takesZero(entry: OdEntry, index: number, subindex: number | null, moving: OdEntry[]): boolean {
  if (entry.via === "sdo" || subindex) return false;
  const others = objects.value.flatMap((o) => o.entries).filter((x) => x.index === index && !moving.includes(x));
  return others.some((x) => !!x.subindex) || moving.some((x) => x !== entry && !!x.subindex);
}

/** A new index of the entries (all entries of an array or a record move together); none takes a signal out of the
 * dictionary, its subindex too. An SDO exchange always has an index. */
function setIndex(entries: OdEntry[], e: Event) {
  const old = entries[0].index;
  const v = read(e, 0xffff, old);
  if (v === undefined || v === old) return;
  if (v === null && entries.some((x) => x.via === "sdo")) {
    toast(t("An SDO exchange always has an index"));
    (e.target as HTMLInputElement).value = cell(old, 4);
    return;
  }
  if (v !== null && entries.some((x) => takesZero(x, v, x.subindex, entries))) {
    toast(t(ZERO_TAKEN));
    (e.target as HTMLInputElement).value = cell(old, 4);
    return;
  }
  const ops: Op[] = entries.flatMap((x): Op[] => (v === null
    ? [{ op: "remove", path: [...x.path, "index"] },
      ...(x.subindex !== null ? [{ op: "remove" as const, path: [...x.path, "subindex"] }] : [])]
    : [{ op: "set", path: [...x.path, "index"], value: v }]));
  void actions.apply(ops);
}

function setSubindex(entry: OdEntry, e: Event) {
  const v = read(e, 0xff, entry.subindex);
  if (v === undefined || v === entry.subindex) return;
  if (entry.index !== null && takesZero(entry, entry.index, v, [entry])) {
    toast(t(ZERO_TAKEN));
    (e.target as HTMLInputElement).value = cell(entry.subindex, 2);
    return;
  }
  void actions.apply([v === null ? { op: "remove", path: [...entry.path, "subindex"] }
    : { op: "set", path: [...entry.path, "subindex"], value: v }]);
}

const selected = (e: OdEntry) => samePath(store.selected, e.path);
</script>

<template>
  <section class="card">
    <h3>{{ t("Object dictionary") }} <span class="muted">{{ indexed.length }}</span></h3>
    <p class="muted od-note">
      {{ t("Indices and subindices of the device's objects. Click the name of an object to open it in its frame.") }}
    </p>
    <table v-if="objects.length" class="list od-table">
      <thead>
        <tr>
          <th class="od-twisty"></th><th>{{ t("Index") }}</th><th>{{ t("Subindex") }}</th><th>{{ t("Object") }}</th>
          <th>{{ t("Type") }}</th><th>{{ t("Frame") }}</th><th>PDO / SDO</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="o in indexed" :key="o.index!">
          <!-- An array or a record: its index for all entries, the entries under it -->
          <tr v-if="grouped(o)" class="od-group" :class="level(objectDiags(o))">
            <td class="od-twisty" @click="toggle(o.index!)">{{ open.has(o.index!) ? "▾" : "▸" }}</td>
            <td><input class="mono" :value="cell(o.index, 4)" :readonly="readonly" :aria-label="t('Index')"
                       :title="objectDiags(o).map((d) => d.message).join('\n')" @change="setIndex(o.entries, $event)" /></td>
            <td class="muted">{{ t("{n} entries", { n: o.entries.length }) }}</td>
            <td class="muted" @click="toggle(o.index!)">{{ o.entries.map((e) => e.label).join(", ") }}</td>
            <td class="mono">{{ TYPE_LABEL[o.type!] }}</td>
            <td>{{ frames(o).join(", ") }}</td>
            <td>{{ vias(o).join(", ") }}</td>
          </tr>
          <template v-if="!grouped(o) || open.has(o.index!)">
            <tr v-for="e in o.entries" :key="e.path.join('/')" :class="[level(entryDiags(e)), { 'od-entry': grouped(o), selected: selected(e) }]">
              <td class="od-twisty"></td>
              <td>
                <span v-if="grouped(o)" class="mono muted">{{ cell(e.index, 4) }}</span>
                <input v-else class="mono" :value="cell(e.index, 4)" :readonly="readonly" :aria-label="t('Index')"
                       :title="entryDiags(e).map((d) => d.message).join('\n')" @change="setIndex([e], $event)" />
              </td>
              <td><input class="mono" :value="cell(e.subindex, 2)" placeholder="0x00" :readonly="readonly"
                         :aria-label="t('Subindex')" :title="entryDiags(e).map((d) => d.message).join('\n')"
                         @change="setSubindex(e, $event)" /></td>
              <td><span class="od-link" :title="t('Open the object in its frame')"
                        @click="actions.select(e.path)">{{ e.label }}</span><span v-if="e.label !== e.name"
                                                                                       class="ident">{{ e.name }}</span></td>
              <td class="mono">{{ grouped(o) ? "" : TYPE_LABEL[o.type!] }}</td>
              <td><a @click="actions.select(e.framePath)"><span class="mono">{{ e.canId }}</span> {{ e.frameLabel }}</a></td>
              <td :title="e.via ? t(VIA_HELP[e.via]) : undefined">{{ e.via ? VIA_LABEL[e.via] : "—" }}</td>
            </tr>
          </template>
        </template>
        <tr v-if="unassigned.length" class="od-sep"><td colspan="7">{{ t("Without an index") }}
          <span class="muted">{{ unassigned.length }}</span></td></tr>
        <tr v-for="o in unassigned" :key="o.entries[0].path.join('/')" :class="{ selected: selected(o.entries[0]) }">
          <td class="od-twisty"></td>
          <td><input class="mono" value="" placeholder="0x2000" :readonly="readonly" :aria-label="t('Index')"
                     @change="setIndex(o.entries, $event)" /></td>
          <td><input class="mono" :value="cell(o.entries[0].subindex, 2)" placeholder="0x00" :readonly="readonly"
                     :aria-label="t('Subindex')" @change="setSubindex(o.entries[0], $event)" /></td>
          <td><span class="od-link" :title="t('Open the object in its frame')"
                    @click="actions.select(o.entries[0].path)">{{ o.entries[0].label }}</span><span
            v-if="o.entries[0].label !== o.entries[0].name" class="ident">{{ o.entries[0].name }}</span></td>
          <td class="muted">—</td>
          <td><a @click="actions.select(o.entries[0].framePath)"><span class="mono">{{ o.entries[0].canId }}</span>
            {{ o.entries[0].frameLabel }}</a></td>
          <td>{{ o.entries[0].via ? VIA_LABEL[o.entries[0].via] : "—" }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">{{ t("The device has no PDO objects or SDO exchanges yet.") }}</p>
  </section>
</template>
