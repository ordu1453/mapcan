<script setup lang="ts">
// Object dictionary tabs (#158): all CiA 301 areas, optional inherited entries and mandatory bus locks.
// Bus rows also show which devices include the object. Definitions inherited from the bus are edited on the bus.
import { computed, nextTick, ref } from "vue";
import { hex } from "../bits";
import { deviceLabel, getAt, isCanopen, pathKey, startsWith, uniqueName } from "../model";
import { AREAS, DATA_TYPES, DEVICE_AREA, dictionary, freeIndex, occupiedIndices, kindOf, objectTypeOps, standardAt, standardOffers, withSdo, type Area, type DictRow,
  type Standard } from "../od";
import { actions, lang, store, toast, viewData } from "../store";
import type { Diagnostic, Op, Path } from "../types";
import { t } from "../i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
const props = defineProps<{ owner: Path }>();

const COLUMNS = 2;

const readonly = computed(() => !!store.state?.readonly);
const busPath = computed(() => props.owner.slice(0, 2));
const isDevice = computed(() => props.owner.length === 4);
const owner = computed(() => getAt(viewData.value, props.owner));
const rows = computed<DictRow[]>(() =>
  (isCanopen(getAt(viewData.value, busPath.value))
    ? dictionary(viewData.value, busPath.value, isDevice.value ? props.owner : null, true) : []));
const devices = computed(() => getAt(viewData.value, busPath.value)?.devices ?? []);
/** On the bus's page each device has a column, as in the other structures: does it have the object. */
const deviceColumns = computed<any[]>(() => (isDevice.value ? [] : devices.value));
const DEVICE_COL_PX = 72;
/** Columns after the object's name on the bus's page: Locked and one per device. */
const extraColumns = computed(() => (isDevice.value ? 0 : 1 + deviceColumns.value.length));

function excludedAt(owner: Path, index: number): boolean {
  return !dictionary(viewData.value, busPath.value, owner).some((r) => r.index === index);
}
function includeInherited(owner: Path, index: number, on: boolean) {
  const excluded = new Set<number>(getAt(viewData.value, owner)?.excluded_objects ?? []);
  if (on) excluded.delete(index); else excluded.add(index);
  void edit([{ op: "set", path: [...owner, "excluded_objects"], value: [...excluded] },
    ...(on ? [{ op: "set" as const, path: [...owner, "objects_enabled"], value: true }] : [])]);
}

const areas = computed<Area[]>(() => AREAS);
/** A line of an area: an object of the dictionary, or a standard object not in the map (on the bus's page). */
interface Line { index: number; row?: DictRow; standard?: Standard }
function lines(a: Area): Line[] {
  const inside = (i: unknown) => typeof i === "number" && i >= a.first && i <= a.last;
  const out: Line[] = rows.value.filter((r) => inside(r.index)).map((r) => ({ index: r.index, row: r }));
  {
    const taken = new Set(out.map((l) => l.index));
    out.push(...standardOffers(taken).filter((s) => inside(s.index)).map((s) => ({ index: s.index, standard: s })));
    if (!isDevice.value) {
      const listed = new Set(out.map((line) => line.index));
      for (const device of devices.value) for (const object of device?.objects ?? []) {
        if (!inside(object?.index) || listed.has(object.index)) continue;
        listed.add(object.index);
        out.push({ index: object.index, standard: { index: object.index, title: () => object.name,
          make: () => ({ ...object, locked: false }) } });
      }
    }
  }
  out.sort((x, y) => x.index - y.index);
  // Objects without a numeric index (being written in the YAML) come last in the manufacturer area
  if (a.first === DEVICE_AREA.first) out.push(...rows.value.filter((r) => typeof r.index !== "number").map((r) => ({ index: NaN, row: r })));
  return out;
}

// Folded areas and opened arrays and records; the data types are folded at first
const folded = ref(new Set<number>([0]));
function fold(a: Area) {
  const s = new Set(folded.value);
  if (s.has(a.first)) s.delete(a.first);
  else s.add(a.first);
  folded.value = s;
}
const open = ref(new Set<string>());
function toggle(r: DictRow) {
  const s = new Set(open.value);
  const k = pathKey(r.path);
  if (s.has(k)) s.delete(k);
  else s.add(k);
  open.value = s;
}
const isOpen = (r: DictRow) => open.value.has(pathKey(r.path));

// Objects of the bus and its devices of each data type
const typesUsed = computed(() => {
  const bus = getAt(viewData.value, busPath.value);
  const owners = [bus, ...(Array.isArray(bus?.devices) ? bus.devices : [])];
  const n = new Map<string, number>();
  for (const o of owners.flatMap((x) => (Array.isArray(x?.objects) ? x.objects : []))) {
    for (const dt of [o?.data_type, ...(Array.isArray(o?.entries) ? o.entries.map((e: any) => e?.data_type) : [])]) {
      if (typeof dt === "string") n.set(dt, (n.get(dt) ?? 0) + 1);
    }
  }
  return n;
});

function diagsAt(p: Path): Diagnostic[] {
  return (store.state?.diagnostics ?? []).filter((d) => startsWith(d.node, p));
}
/** Messages of the object itself, not of its entries. */
const ownDiags = (p: Path) => diagsAt(p).filter((d) => d.node[p.length] !== "entries");
const level = (ds: Diagnostic[]) =>
  (ds.some((d) => d.level === "error") ? "error" : ds.some((d) => d.level === "warning") ? "warning" : "");
const messages = (ds: Diagnostic[]) => ds.map((d) => d.message).join("\n") || undefined;

// ------------------------------------------------------------------ open and rename

// A click opens the object (an entry) in its form; a double click renames it in place. The click waits for a second
// one, so a double click does not leave the page.
const renaming = ref<string | null>(null);
let clickTimer: ReturnType<typeof setTimeout> | null = null;
function onNameClick(p: Path) {
  if (clickTimer) clearTimeout(clickTimer);
  clickTimer = setTimeout(() => {
    clickTimer = null;
    void actions.select(p);
  }, 250);
}
async function onNameDblClick(p: Path, inherited: boolean) {
  if (clickTimer) clearTimeout(clickTimer);
  clickTimer = null;
  if (readonly.value || inherited) return;
  renaming.value = pathKey(p);
  await nextTick();
  const el = document.querySelector<HTMLInputElement>(".od-table input.od-rename");
  el?.focus();
  el?.select();
}
function rename(p: Path, e: Event) {
  if (renaming.value !== pathKey(p)) return;
  renaming.value = null;
  const v = (e.target as HTMLInputElement).value.trim();
  if (v && v !== getAt(viewData.value, [...p, "name"])) void edit([{ op: "set", path: [...p, "name"], value: v }]);
}

// ------------------------------------------------------------------ adding and removing

/** An edit of the dictionary, with the object of the SDO frames of the devices brought in line. */
const edit = (ops: Op[]) => actions.apply(withSdo(viewData.value, busPath.value, ops));

function setObjectType(r: DictRow, event: Event) {
  if (readonly.value || r.inherited) return;
  const kind = (event.target as HTMLSelectElement).value;
  if (kind === kindOf(r.obj)) return;
  void edit(objectTypeOps(r.path, r.obj, kind === "var" ? "" : kind));
  if (kind !== "var") open.value = new Set([...open.value, pathKey(r.path)]);
}

const ownObjects = () => (Array.isArray(owner.value?.objects) ? owner.value.objects : []);

/** A new object of the area at its first free index, with a name to give it in place. */
function addObject(a: Area) {
  const index = freeIndex(a, occupiedIndices(viewData.value, props.owner));
  if (index === null) {
    toast(t("No free index in the area"));
    return;
  }
  if (folded.value.has(a.first)) fold(a);
  const name = uniqueName("object", ownObjects().map((o: any) => o?.name));
  void edit([{ op: "insert", path: [...props.owner, "objects"], value: { index, name, data_type: "unsigned8" } },
    { op: "set", path: [...props.owner, "objects_enabled"], value: true }]);
}

/** A new entry of an array or a record at the next subindex. */
function addEntry(r: DictRow) {
  const entries: any[] = Array.isArray(r.obj?.entries) ? r.obj.entries : [];
  const sub = Math.max(0, ...entries.map((x) => (typeof x?.subindex === "number" ? x.subindex : 0))) + 1;
  if (sub > 0xfe) return;
  open.value = new Set([...open.value, pathKey(r.path)]);
  void edit([{ op: "insert", path: [...r.path, "entries"], value: {
    subindex: sub, name: uniqueName("entry", entries.map((x) => x?.name)),
    data_type: (r.obj?.array && entries[0]?.data_type) || "unsigned8" } }]);
}

function removeEntry(r: DictRow, ei: number) {
  const entries: any[] = r.obj.entries;
  // Without its last entry the object is a variable of that entry's type
  void edit(entries.length > 1 ? [{ op: "remove", path: [...r.path, "entries", ei] }]
    : [{ op: "set", path: [...r.path, "data_type"], value: entries[0]?.data_type ?? "unsigned8" },
      { op: "set", path: [...r.path, "entries"], value: null }, { op: "set", path: [...r.path, "array"], value: null }]);
}

/** The tick of a standard object: in the map or not. */
function include(s: Standard, on: boolean, r?: DictRow) {
  if (on) void edit([{ op: "insert", path: [...props.owner, "objects"], value: s.make(lang.value) }]);
  else if (r) void edit([{ op: "remove", path: r.path }]);
}

function includeDeviceStandard(di: number, s: Standard, on: boolean) {
  const dp = [...busPath.value, "devices", di];
  const objects = devices.value[di]?.objects ?? [];
  const index = objects.findIndex((o: any) => o?.index === s.index);
  if (on && index < 0) void edit([{ op: "insert", path: [...dp, "objects"], value: s.make(lang.value) },
    { op: "set", path: [...dp, "objects_enabled"], value: true },
    { op: "set", path: [...dp, "excluded_objects"], value: (devices.value[di]?.excluded_objects ?? []).filter((i: number) => i !== s.index) }]);
  else if (!on && index >= 0) void edit([{ op: "remove", path: [...dp, "objects", index] }]);
}

const indexText = (i: unknown) => (typeof i === "number" ? hex(i, 4) : "—");
</script>

<template>
  <section class="card">
    <h3>{{ t("Object dictionary") }}</h3>
    <p class="muted od-note">
      {{ isDevice
        ? t("Select the objects this device needs in any protocol area. Unlocked bus objects can be excluded.")
        : t("Bus objects are inherited by devices. Lock an object to make it mandatory for every device.") }}
      {{ t("A click on an identifier opens the object, a double click renames it.") }}
    </p>
    <div class="od-scroll">
      <table class="list od-table" :style="{ minWidth: `${420 + DEVICE_COL_PX * extraColumns}px` }">
        <colgroup><col class="od-c-twisty" /><col class="od-c-index" /><col />
          <col v-for="di in extraColumns" :key="di" :style="{ width: `${DEVICE_COL_PX}px` }" /><col class="od-c-act" /></colgroup>
        <thead v-if="!isDevice"><tr>
          <th></th><th>{{ t("Index") }}</th><th>{{ t("Object") }}</th><th class="od-dev">{{ t("Locked") }}</th>
          <th v-for="(d, di) in deviceColumns" :key="di" class="od-dev" :title="deviceLabel(d, lang)">{{ deviceLabel(d, lang) }}</th><th></th>
        </tr></thead>
        <tbody v-for="a in areas" :key="a.first">
          <!-- The heading of an area, as a section heading in code: it folds the area, its + adds an object -->
          <tr class="od-area" :aria-expanded="!folded.has(a.first)" @click="fold(a)">
            <td class="od-twisty">{{ folded.has(a.first) ? "▸" : "▾" }}</td>
            <td :colspan="COLUMNS + extraColumns">
              <span class="mono">{{ hex(a.first, 4) }}–{{ hex(a.last, 4) }}</span> {{ t(a.title) }}
            </td>
            <td class="act">
              <button v-if="!readonly && a.first !== 0" class="od-icon" :title="t('New object')" :aria-label="t('New object')"
                      @click.stop="addObject(a)"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2v12M2 8h12" /></svg></button>
            </td>
          </tr>
          <template v-if="!folded.has(a.first)">
            <!-- The data types of CiA 301 with the number of objects of each -->
            <template v-if="a.first === 0">
              <tr v-for="d in DATA_TYPES" :key="d[1]" :class="{ 'od-unused': !typesUsed.get(d[0]) }">
                <td class="od-twisty"></td><td class="mono">{{ hex(d[1], 4) }}</td>
                <td :colspan="1 + extraColumns"><span class="mono">{{ d[0].toUpperCase() }}</span>
                  <span v-if="d[2]" class="muted od-badge">{{ t("{n} bits", { n: d[2] }) }}</span></td><td></td>
              </tr>
            </template>
            <template v-else>
              <template v-for="l in lines(a)" :key="l.row ? pathKey(l.row.path) : `std:${l.index}`">
                <!-- A standard object not in the map: its tick puts it there -->
                <tr v-if="l.standard" class="od-standard">
                  <td class="od-twisty"></td><td class="mono">{{ hex(l.index, 4) }}<span v-if="kindOf(l.standard.make(lang)) === 'var'">:00</span></td>
                  <td>{{ l.standard.make(lang).name }}</td>
                  <td v-if="!isDevice"></td>
                  <td v-for="(d, di) in deviceColumns" :key="di" class="od-dev">
                    <input type="checkbox" :checked="!excludedAt([...busPath, 'devices', Number(di)], l.index)" :disabled="readonly"
                           :aria-label="deviceLabel(d, lang)"
                           @change="includeDeviceStandard(Number(di), l.standard!, ($event.target as HTMLInputElement).checked)" />
                  </td>
                  <td class="act"><input class="od-icon" type="checkbox" :checked="false" :disabled="readonly"
                                         :aria-label="t('Include {name} in the map', { name: l.standard.make(lang).name })"
                                         :title="t('Include in the map')" @change="include(l.standard, true)" /></td>
                </tr>
                <template v-else-if="l.row">
                  <tr :class="['od-obj', level(ownDiags(l.row.path)), { 'od-inherited': l.row.inherited, 'od-group': kindOf(l.row.obj) !== 'var' }]"
                      :title="messages(ownDiags(l.row.path))">
                    <td class="od-twisty" @click="toggle(l.row)">{{ kindOf(l.row.obj) === "var" ? "" : isOpen(l.row) ? "▾" : "▸" }}</td>
                    <td class="mono">{{ indexText(l.row.index) }}<span v-if="kindOf(l.row.obj) === 'var'">:00</span></td>
                    <td>
                      <input v-if="renaming === pathKey(l.row.path)" class="mono od-rename" :value="l.row.obj?.name"
                             :aria-label="t('Identifier')" @change="rename(l.row.path, $event)" @blur="rename(l.row.path, $event)"
                             @keydown.esc.stop="renaming = null" />
                      <span v-else class="mono od-name" :title="t('A click opens the object, a double click renames it')"
                            @click="!l.row.inherited && onNameClick(l.row.path)" @dblclick="onNameDblClick(l.row.path, l.row.inherited)">{{ l.row.obj?.name }}</span>
                      <select class="od-kind mono" :value="kindOf(l.row.obj)" :disabled="readonly || l.row.inherited"
                              :aria-label="t('Object type')" @change="setObjectType(l.row, $event)">
                        <option value="var">var</option><option value="array">array</option><option value="record">record</option>
                      </select>
                      <span v-if="l.row.overrides" class="muted od-badge"
                            :title="t('Takes the place of the bus\'s object with this index')">{{ t("instead of the bus's") }}</span>
                    </td>
                    <td v-if="!isDevice" class="od-dev">
                      <input type="checkbox" :checked="!!l.row.obj.locked" :disabled="readonly" :aria-label="t('Locked')"
                             @change="edit([{ op: 'set', path: [...l.row!.path, 'locked'], value: ($event.target as HTMLInputElement).checked }])" />
                    </td>
                    <td v-for="(d, di) in deviceColumns" :key="di" class="od-dev">
                      <input type="checkbox" :checked="!excludedAt([...busPath, 'devices', Number(di)], l.row.index)"
                             :disabled="readonly || l.row.obj.locked" :aria-label="deviceLabel(d, lang)"
                             @change="includeInherited([...busPath, 'devices', Number(di)], l.row!.index, ($event.target as HTMLInputElement).checked)" />
                    </td>
                    <td class="act">
                      <input v-if="l.row.inherited" type="checkbox" :checked="!l.row.excluded" :disabled="readonly || l.row.obj.locked"
                             :aria-label="t('Include {name} in the map', { name: l.row.obj.name })"
                             @change="includeInherited(props.owner, l.row.index, ($event.target as HTMLInputElement).checked)" />
                      <button v-if="!readonly && !l.row.inherited && kindOf(l.row.obj) !== 'var'" class="od-icon"
                              :title="t('New entry')" :aria-label="t('New entry')" @click="addEntry(l.row)"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2v12M2 8h12" /></svg></button>
                      <span v-if="l.row.inherited && l.row.obj.locked" class="od-icon od-lock" :title="t('An object of the bus: it is changed on the bus\'s page')"
                            :aria-label="t('An object of the bus: it is changed on the bus\'s page')">
                        <svg viewBox="0 0 16 16" aria-hidden="true"><rect class="od-fill" x="2.5" y="7" width="11" height="7.5" rx="1.5" /><path d="M5 7V5a3 3 0 0 1 6 0v2" /></svg>
                      </span>
                      <input v-else-if="!l.row.inherited && standardAt(l.row.index)" class="od-icon" type="checkbox" checked :disabled="readonly"
                             :aria-label="t('Include {name} in the map', { name: l.row.obj?.name })" :title="t('Include in the map')"
                             @change="include(standardAt(l.row.index)!, false, l.row)" />
                      <button v-else-if="!readonly && !l.row.inherited" class="od-icon" :title="t('Delete')" :aria-label="t('Delete')"
                              @click="edit([{ op: 'remove', path: l.row.path }])"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg></button>
                    </td>
                  </tr>
                  <!-- Entries of an array or a record by subindex -->
                  <template v-if="kindOf(l.row.obj) !== 'var' && isOpen(l.row)">
                    <tr v-for="(e, ei) in l.row.obj.entries" :key="ei" class="od-entry"
                        :class="[level(diagsAt([...l.row.path, 'entries', ei])), { 'od-inherited': l.row.inherited }]"
                        :title="messages(diagsAt([...l.row.path, 'entries', ei]))">
                      <td class="od-twisty"></td>
                      <td class="mono"><span class="muted">{{ indexText(l.row.index) }}</span>:{{ typeof e?.subindex === "number" ? hex(e.subindex, 2).slice(2) : "—" }}</td>
                      <td :colspan="1 + extraColumns">
                        <input v-if="renaming === pathKey([...l.row.path, 'entries', ei])" class="mono od-rename" :value="e?.name"
                               :aria-label="t('Identifier')" @change="rename([...l.row.path, 'entries', ei], $event)"
                               @blur="rename([...l.row.path, 'entries', ei], $event)" @keydown.esc.stop="renaming = null" />
                        <span v-else class="mono od-name" :title="t('A click opens the entry, a double click renames it')"
                              @click="!l.row.inherited && onNameClick([...l.row.path, 'entries', ei])"
                              @dblclick="onNameDblClick([...l.row.path, 'entries', ei], l.row.inherited)">{{ e?.name }}</span>
                      </td>
                      <td class="act">
                        <span v-if="l.row.inherited" class="od-icon od-lock" :title="t('An object of the bus: it is changed on the bus\'s page')"
                              :aria-label="t('An object of the bus: it is changed on the bus\'s page')"><svg viewBox="0 0 16 16" aria-hidden="true"><rect class="od-fill" x="2.5" y="7" width="11" height="7.5" rx="1.5" /><path d="M5 7V5a3 3 0 0 1 6 0v2" /></svg></span>
                        <button v-else-if="!readonly" class="od-icon" :title="t('Delete')" :aria-label="t('Delete')"
                                @click="removeEntry(l.row, Number(ei))"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg></button>
                      </td>
                    </tr>
                  </template>
                </template>
              </template>
              <tr v-if="!lines(a).length"><td></td><td :colspan="COLUMNS + 1 + extraColumns" class="muted">{{ t("No objects in this area.") }}</td></tr>
            </template>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>
