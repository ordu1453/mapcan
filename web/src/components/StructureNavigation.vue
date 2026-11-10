<script setup lang="ts">
import { computed, ref } from "vue";
import { actions, store, viewData, toast } from "../store";
import { getAt, isCanopen } from "../model";
import { effectiveStructure, structureNames, TEMPLATES } from "../structures";
import { withSdo } from "../od";
import type { Op, Path } from "../types";
import { t } from "../i18n";

const props = defineProps<{ owner: Path; active: string }>();
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
  const ops: Op[] = [{ op: "set", path, value: false }];
  if (await actions.apply(n === "objects" ? withSdo(viewData.value, props.owner.slice(0, 2), ops) : ops) && props.active === n) emit("select", "");
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
  if (await actions.apply(n === "objects" ? withSdo(viewData.value, props.owner.slice(0, 2), [op]) : [op])) { adding.value = false; name.value = ""; emit("select", n); }
}
</script>

<template>
  <!-- Tabs as in Windows: Properties on the left, then "+" and the structures on the right; the active tab joins the card below -->
  <div class="structure-nav">
    <nav class="structure-tabs" role="tablist" :aria-label="t('Structures')">
      <span class="tab" :class="{ active: !active }">
        <button class="tab-label" role="tab" :aria-selected="!active" @click="emit('select', '')">{{ t("Properties") }}</button>
      </span>
      <span class="spacer" />
      <button v-if="!readonly" class="tab-add" :class="{ active: adding }" :aria-label="t('Add structure')"
              :title="t('Add structure')" @click="adding = !adding">+</button>
      <span v-for="n in names" :key="n" class="tab" :class="{ active: active === n }">
        <button class="tab-label" role="tab" :aria-selected="active === n" @click="emit('select', n)">{{ title(n) }}</button>
        <button v-if="!readonly" class="tab-close" :disabled="locked(n)"
                :title="locked(n) ? t('Unlock the bus entries before removing this structure.') : t('Remove structure')"
                :aria-label="t('Remove structure')" @click.stop="remove(n)">×</button>
      </span>
    </nav>
    <form v-if="adding" class="structure-add" @submit.prevent="add">
      <input v-model="name" :aria-label="t('Identifier')" :placeholder="t('Identifier')" list="structure-presets" />
      <datalist id="structure-presets"><option v-for="n in (isCanopen(bus) ? ['states', 'eec', 'objects', 'warnings', 'fault', 'mode'] : [])" :key="n" :value="n" /></datalist>
      <select v-model="kind" :aria-label="t('Structure type')"><option value="enum">{{ t("Enumeration") }}</option><option value="bitmask">{{ t("Bit mask") }}</option></select>
      <button type="submit">{{ t("Add") }}</button>
    </form>
  </div>
</template>
