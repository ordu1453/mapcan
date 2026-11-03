<script setup lang="ts">
import { computed, ref } from "vue";
import { N_, t } from "../i18n";
import { SDO_COMMANDS } from "../od";
import BitGrid from "./BitGrid.vue";
import type { ResolvedFrame, ResolvedSignal } from "../types";

const props = defineProps<{ direction: string; frame: ResolvedFrame; palette: string[] }>();
const fields = [
  { name: "sdo_command", byte: 0, length: 1, description: N_("The SDO command specifies the operation and the size of the data.") },
  { name: "index", byte: 1, length: 2, description: N_("The 16-bit index identifies an object in the dictionary. The low byte is transmitted first.") },
  { name: "subindex", byte: 3, length: 1, description: N_("The 8-bit subindex identifies an entry of an object. For a variable it is zero.") },
  { name: "value", byte: 4, length: 4, description: N_("The four-byte data area carries the value or an abort code, depending on the command. The command determines how many bytes contain data.") },
];
const selected = ref<string | null>(null);
const field = computed(() => fields.find((f) => f.name === selected.value));
const commands = computed(() => SDO_COMMANDS[props.direction] ?? {});
const layout = computed<ResolvedFrame>(() => ({
  ...props.frame, length: 8,
  signals: fields.map((f, i): ResolvedSignal => ({
    name: f.name, index: null, path: [...props.frame.path, "sdo_structure", i], ref: null,
    encoding: "number", start_bit: f.byte * 8, bit_length: f.length * 8,
    byte_order: "little_endian", signed: false, multiplexer: false, mux: null,
    occupied: Array.from({ length: f.length * 8 }, (_, bit) => f.byte * 8 + bit),
    flags: [], values: [], synthetic: true,
  })),
}));
</script>

<template>
  <div class="sdo-structure">
    <BitGrid :frame="layout" :selected="frame.path" :palette="palette" :mux-value="null"
             :synthetic="selected" readonly locked objects @synthetic="selected = $event" />
    <p class="muted">{{ t("Standard format: cannot be changed") }}. {{ t("Click a field to view its description.") }}</p>
    <p class="muted">{{ t("SDO transfers the objects described in the object dictionary: it reads and writes their values by index and subindex.") }}</p>
    <div v-if="field" class="sdo-details">
      <h4>{{ field.name }}</h4>
      <p>{{ t(field.description) }}</p>
      <table v-if="field.name === 'sdo_command'" class="list">
        <thead><tr><th>{{ t("Command") }}</th><th>{{ t("Name") }}</th></tr></thead>
        <tbody><tr v-for="(name, code) in commands" :key="code"><td class="mono">{{ code }}</td><td class="mono">{{ name }}</td></tr></tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.sdo-details { margin-top: 16px; }
</style>
