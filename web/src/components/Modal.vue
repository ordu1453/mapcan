<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { t } from "../i18n";

defineProps<{ title: string; wide?: boolean }>();
const emit = defineEmits<{ close: [] }>();

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="emit('close')">
    <div class="modal" :class="{ wide }" role="dialog" :aria-label="title">
      <header>
        <h3>{{ title }}</h3>
        <slot name="actions" />
        <button class="icon" :title="t('Close (Esc)')" @click="emit('close')">✕</button>
      </header>
      <div class="modal-body"><slot /></div>
    </div>
  </div>
</template>
