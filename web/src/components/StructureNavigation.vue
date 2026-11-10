<script setup lang="ts">
import { computed, ref } from "vue";
import { actions, store, viewData, toast } from "../store";
import { getAt, isCanopen } from "../model";
import { effectiveStructure, structureNames, TEMPLATES } from "../structures";
import type { Path } from "../types";
import { t } from "../i18n";

const props = defineProps<{ owner: Path; active: string; management?: boolean }>();
const emit = defineEmits<{ select: [name: string] }>();
const adding = ref(false);
const name = ref("");
const kind = ref("enum");
const bus = computed(() => getAt(viewData.value, props.owner.slice(0, 2)));
const owner = computed(() => getAt(viewData.value, props.owner));
const readonly = computed(() => !!store.state?.readonly);
const names = computed(() => [
  ...(isCanopen(bus.value) && (owner.value?.objects_enabled !== false
    || (props.owner.length === 4 && bus.value?.objects_enabled !== false && (bus.value?.objects ?? []).some((o: { locked?: boolean }) => o.locked))) ? ["objects"] : []),
  ...structureNames(viewData.value, props.owner),
]);
const title = (n: string) => n === "objects" ? t("Objects")
  : effectiveStructure(viewData.value, props.owner, n)?.title === "States" ? t("States")
    : effectiveStructure(viewData.value, props.owner, n)?.title || n;
function locked(n: string) {
  if (n === "objects") return (bus.value?.objects ?? []).some((o: { locked?: boolean }) => o.locked);
  return (bus.value?.structures?.[n]?.locked ?? []).length > 0;
}
async function remove(n: string) {
  if (readonly.value || locked(n)) return;
  const path = n === "objects" ? [...props.owner, "objects_enabled"] : [...props.owner, "structures", n, "enabled"];
  if (await actions.apply([{ op: "set", path, value: false }]) && props.active === n) emit("select", "");
}
async function add() {
  const n = name.value.trim();
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(n)) { toast(t("Use an identifier: letters, digits and underscore.")); return; }
  if (names.value.includes(n)) { toast(t("This structure already exists.")); return; }
  if (n === "objects" && !isCanopen(bus.value)) { toast(t("Objects are available on CANopen buses.")); return; }
  const existing = owner.value?.structures?.[n];
  const value = { kind: TEMPLATES[n]?.kind ?? kind.value, values: {}, ...existing, enabled: true };
  const op = n === "objects" ? { op: "set" as const, path: [...props.owner, "objects_enabled"], value: true }
    : { op: "set" as const, path: [...props.owner, "structures", n], value };
  if (await actions.apply([op])) { adding.value = false; name.value = ""; emit("select", n); }
}
</script>

<template>
  <nav class="structure-tabs" :aria-label="t('Structures')">
    <template v-if="!management">
      <button :class="{ active: !active }" @click="emit('select', '')">{{ t("Properties") }}</button>
      <span class="spacer" />
    </template>
    <span class="muted">{{ t("Structures") }}</span>
    <button v-if="!readonly" :aria-label="t('Add structure')" :title="t('Add structure')" @click="adding = !adding">+</button>
    <span v-for="n in names" :key="n" class="structure-tab">
      <button :class="{ active: active === n }" @click="emit('select', n)">{{ title(n) }}</button>
      <button v-if="!readonly" class="icon" :disabled="locked(n)" :title="locked(n) ? t('Unlock the bus entries before removing this structure.') : t('Remove structure')"
              :aria-label="t('Remove structure')" @click="remove(n)">×</button>
    </span>
    <form v-if="adding" class="structure-add" @submit.prevent="add">
      <input v-model="name" :aria-label="t('Identifier')" :placeholder="t('Identifier')" list="structure-presets" />
      <datalist id="structure-presets"><option v-for="n in (isCanopen(bus) ? ['states', 'eec', 'objects', 'warnings', 'fault', 'mode'] : [])" :key="n" :value="n" /></datalist>
      <select v-model="kind" :aria-label="t('Structure type')"><option value="enum">{{ t("Enumeration") }}</option><option value="bitmask">{{ t("Bit mask") }}</option></select>
      <button type="submit">{{ t("Add") }}</button>
    </form>
  </nav>
</template>
