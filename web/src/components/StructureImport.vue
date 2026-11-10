<script setup lang="ts">
// "Import from structure": a button with the list of the structures whose values a signal or a flag can take. The
// choice binds the node to the structure (values: structure:<name>), its values then come from there.
import { onBeforeUnmount, ref } from "vue";
import { t } from "../i18n";

defineProps<{ options: { name: string; title: string }[] }>();
const emit = defineEmits<{ pick: [name: string] }>();
const open = ref(false);
const root = ref<HTMLElement | null>(null);
const close = (e: MouseEvent) => { if (!root.value?.contains(e.target as Node)) setOpen(false); };
function setOpen(v: boolean) {
  open.value = v;
  if (v) document.addEventListener("mousedown", close);
  else document.removeEventListener("mousedown", close);
}
function pick(name: string) {
  setOpen(false);
  emit("pick", name);
}
onBeforeUnmount(() => document.removeEventListener("mousedown", close));
</script>

<template>
  <span ref="root" class="structure-import">
    <button class="small" :disabled="!options.length" :aria-expanded="open"
            :title="options.length ? '' : t('No structures: add one on the bus or the device')" @click="setOpen(!open)">
      {{ t("Import from structure") }} ▾</button>
    <span v-if="open" class="structure-import-menu" role="menu">
      <button v-for="o in options" :key="o.name" role="menuitem" @click="pick(o.name)">
        {{ o.title }}<span v-if="o.title !== o.name" class="muted mono"> {{ o.name }}</span></button>
    </span>
  </span>
</template>
