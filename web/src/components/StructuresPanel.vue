<script setup lang="ts">
import { computed, ref } from "vue";
import { actions, lang, store, toast, viewData } from "../store";
import { deviceLabel, getAt, isCanopen } from "../model";
import { effectiveStructure, TEMPLATES, type ValueStructure } from "../structures";
import { hex } from "../bits";
import { parseInteger } from "@mapcan/forms";
import type { Path } from "../types";
import { t } from "../i18n";

const props = defineProps<{ owner: Path; name: string }>();
const bus = computed(() => getAt(viewData.value, props.owner.slice(0, 2)));
const own = computed<ValueStructure>(() => getAt(viewData.value, [...props.owner, "structures", props.name]) ?? {});
const base = computed<ValueStructure>(() => bus.value?.structures?.[props.name]?.enabled === false ? {} : bus.value?.structures?.[props.name] ?? {});
const effective = computed(() => effectiveStructure(viewData.value, props.owner, props.name));
const isDevice = computed(() => props.owner.length === 4);
const readonly = computed(() => !!store.state?.readonly);
const code = ref("");
const newName = ref("");
const newDescription = ref("");
const rows = computed(() => {
  const deviceValues = isDevice.value ? {} : Object.assign({}, ...(bus.value?.devices ?? [])
    .map((d: { structures?: Record<string, ValueStructure> }) => d.structures?.[props.name]?.values ?? {}));
  const values = { ...(isCanopen(bus.value) ? TEMPLATES[props.name]?.values : {}), ...deviceValues, ...base.value.values, ...own.value.values } as NonNullable<ValueStructure["values"]>;
  for (const key of base.value.locked ?? []) {
    if (base.value.values?.[key] !== undefined) values[key] = base.value.values[key];
  }
  return Object.entries(values).map(([key, v]) => ({ key, code: Number(key), name: typeof v === "string" ? v : v.name,
    description: typeof v === "string" ? "" : v.description ?? "", value: v,
    selected: Object.hasOwn(effective.value?.values ?? {}, key), locked: base.value.locked?.includes(Number(key)) ?? false,
    inherited: isDevice.value && Object.hasOwn(base.value.values ?? {}, key),
  })).sort((a, b) => a.code - b.code);
});
type Row = typeof rows.value[number];
async function save(patch: Partial<ValueStructure>, owner = props.owner) {
  const previous = getAt(viewData.value, [...owner, "structures", props.name]) ?? {};
  return actions.apply([{ op: "set", path: [...owner, "structures", props.name],
    value: { kind: effective.value?.kind ?? "enum", values: {}, ...previous, ...patch } }]);
}
function toggle(row: Row, on: boolean) {
  if (isDevice.value && row.locked) return;
  const values = { ...own.value.values };
  const excluded = new Set(own.value.excluded ?? []);
  if (on) excluded.delete(row.code);
  if (row.inherited) { if (on) excluded.delete(row.code); else { excluded.add(row.code); delete values[row.key]; } }
  else if (on) values[row.key] = row.value;
  else delete values[row.key];
  void save({ values, excluded: [...excluded], locked: (own.value.locked ?? []).filter((k) => on || k !== row.code) });
}
function lock(row: Row, on: boolean) {
  const locked = new Set(own.value.locked ?? []);
  if (on) locked.add(row.code); else locked.delete(row.code);
  void save({ locked: [...locked], values: { ...own.value.values, [row.key]: row.value } });
}
function rename(row: Row, field: "name" | "description", event: Event) {
  const value = (event.target as HTMLInputElement).value.trim();
  if ((isDevice.value && row.locked) || !row.selected || (field === "name" && !value)) return;
  void save({ values: { ...own.value.values, [row.key]: { name: row.name, description: row.description, [field]: value } } });
}
async function add() {
  let n: number;
  try { n = parseInteger(code.value); } catch { toast(t("Enter an integer value.")); return; }
  if (!Number.isSafeInteger(n) || n < 0 || !newName.value.trim()) return;
  if (effective.value?.kind === "bitmask" && (n < 1 || !Number.isInteger(Math.log2(n)))) { toast(t("A bit mask value must be a power of two.")); return; }
  if (rows.value.some((r) => r.code === n)) { toast(t("Value {n} is already in the table", { n })); return; }
  if (await save({ values: { ...own.value.values, [n]: { name: newName.value.trim(), description: newDescription.value.trim() } } })) {
    code.value = ""; newName.value = ""; newDescription.value = "";
  }
}
function deviceSelected(di: number, key: string) {
  return Object.hasOwn(effectiveStructure(viewData.value, [...props.owner, "devices", di], props.name)?.values ?? {}, key);
}
function toggleDevice(di: number, row: Row, on: boolean) {
  const owner = [...props.owner, "devices", di];
  const structure: ValueStructure = getAt(viewData.value, [...owner, "structures", props.name]) ?? {};
  const excluded = new Set(structure.excluded ?? []);
  const values = { ...structure.values };
  if (on) excluded.delete(row.code); else excluded.add(row.code);
  if (!on) delete values[row.key];
  else if (!Object.hasOwn(base.value.values ?? {}, row.key)) values[row.key] = row.value;
  void save({ values, excluded: [...excluded], enabled: true }, owner);
}
</script>

<template>
  <section class="card">
    <h3>{{ effective?.title === 'States' ? t('States') : effective?.title || name }}</h3>
    <div class="structure-add">
      <label class="field"><span class="field-label">{{ t("Title") }}</span>
        <input :value="effective?.title || name" :disabled="readonly" @change="save({ title: ($event.target as HTMLInputElement).value })" />
      </label>
      <label class="field"><span class="field-label">{{ t("Structure type") }}</span>
        <select :value="effective?.kind" :disabled="readonly || (isDevice && !!bus.structures?.[name])"
                @change="save({ kind: ($event.target as HTMLSelectElement).value as 'enum' | 'bitmask' })">
          <option value="enum">{{ t("Enumeration") }}</option><option value="bitmask">{{ t("Bit mask") }}</option>
        </select>
      </label>
    </div>
    <p class="muted">{{ t("Bus entries are inherited. Devices may exclude unlocked entries; locked entries are mandatory.") }}</p>
    <p v-if="name === 'states'" class="muted">{{ t("CANopen NMT states (CiA 301). Select the states used by your devices.") }}</p>
    <p v-if="name === 'eec'" class="muted">{{ t("16-bit EMCY error codes (CiA 301). Add device-specific codes as needed.") }}</p>
    <div class="od-scroll">
      <table class="list structure-values">
        <thead><tr><th>{{ t("Include in the map") }}</th><th>{{ t("Value") }}</th><th>{{ t("Name") }}</th><th>{{ t("Description") }}</th><th>{{ t("Locked") }}</th>
          <template v-if="!isDevice"><th v-for="(d, di) in bus.devices ?? []" :key="di">{{ deviceLabel(d, lang) }}</th></template>
        </tr></thead>
        <tbody><tr v-for="row in rows" :key="row.key">
          <td><input type="checkbox" :checked="row.selected" :disabled="readonly || (isDevice && row.locked)" :aria-label="t('Include {name} in the map', { name: row.name })"
                     @change="toggle(row, ($event.target as HTMLInputElement).checked)" /></td>
          <td class="mono">{{ hex(row.code, name === 'eec' ? 4 : 2) }}</td>
          <td><input :value="row.name" :aria-label="t('Name')" :disabled="readonly || !row.selected || (isDevice && row.locked)" @change="rename(row, 'name', $event)" /></td>
          <td><input :value="row.description" :aria-label="t('Description')" :disabled="readonly || !row.selected || (isDevice && row.locked)" @change="rename(row, 'description', $event)" /></td>
          <td><input type="checkbox" :checked="row.locked" :aria-label="t('Locked')" :disabled="readonly || isDevice || !row.selected" @change="lock(row, ($event.target as HTMLInputElement).checked)" /></td>
          <template v-if="!isDevice"><td v-for="(d, di) in bus.devices ?? []" :key="di">
            <input type="checkbox" :checked="deviceSelected(Number(di), row.key)" :disabled="readonly || row.locked"
                   :aria-label="deviceLabel(d, lang)" @change="toggleDevice(Number(di), row, ($event.target as HTMLInputElement).checked)" />
          </td></template>
        </tr></tbody>
      </table>
    </div>
    <form v-if="!readonly" class="structure-add" @submit.prevent="add">
      <input v-model="code" :aria-label="t('Value')" :placeholder="t('Value')" required />
      <input v-model="newName" :aria-label="t('Name')" :placeholder="t('Name')" required />
      <input v-model="newDescription" :aria-label="t('Description')" :placeholder="t('Description')" />
      <button type="submit">+ {{ t("Value") }}</button>
    </form>
  </section>
</template>
