<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { t } from "../i18n";

defineProps<{ title: string; wide?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const root = ref<HTMLElement | null>(null);

function onKey(e: KeyboardEvent) {
  if (e.key !== "Escape") return;
  // Only the topmost dialog closes (a question asked over another dialog)
  const all = document.querySelectorAll(".modal-backdrop");
  if (all[all.length - 1] === root.value) emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <!-- A click on the backdrop does not close the dialog: it would lose what was typed in it (Esc and ✕ do) -->
  <div ref="root" class="modal-backdrop">
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
