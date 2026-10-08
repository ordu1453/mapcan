<script setup lang="ts">
// A "?" circle with the field's help: the text shows on hover and stays on click (Esc / a click elsewhere closes it).
import { onBeforeUnmount, ref, watch } from "vue";
import { t } from "../i18n";

defineProps<{ text: string }>();

const open = ref(false);
const flip = ref(false);    // at the right edge of the window: open to the left
const root = ref<HTMLElement | null>(null);

function place() {
  const r = root.value?.getBoundingClientRect();
  if (r) flip.value = r.left + 330 > window.innerWidth;
}

function onDoc(e: Event) {
  if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.value?.contains(e.target as Node)) open.value = false;
}
watch(open, (v) => {
  const fn = v ? document.addEventListener : document.removeEventListener;
  fn.call(document, "mousedown", onDoc);
  fn.call(document, "keydown", onDoc);
});
onBeforeUnmount(() => {
  document.removeEventListener("mousedown", onDoc);
  document.removeEventListener("keydown", onDoc);
});
</script>

<template>
  <!-- Inside a <label>: a click must not move the focus to the input -->
  <span ref="root" class="help-tip" :class="{ open, flip }" role="button" tabindex="0" :aria-label="t('Help')"
        :aria-expanded="open" @mouseenter="place" @mousedown.prevent @click.prevent.stop="place(); open = !open"
        @keydown.enter.prevent.stop="place(); open = !open">
    ?
    <span class="help-pop" role="tooltip">{{ t(text) }}</span>
  </span>
</template>
