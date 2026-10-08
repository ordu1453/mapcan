<script setup lang="ts">
// Кружок «?» со справкой по полю: текст показывается при наведении, по клику закрепляется (Esc / клик мимо — закрыть).
import { onBeforeUnmount, ref, watch } from "vue";
import { t } from "../i18n";

defineProps<{ text: string }>();

const open = ref(false);
const flip = ref(false);    // у правого края окна — открывать влево
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
  <!-- Внутри <label>: клик не должен переводить фокус в поле ввода -->
  <span ref="root" class="help-tip" :class="{ open, flip }" role="button" tabindex="0" :aria-label="t('Help')"
        :aria-expanded="open" @mouseenter="place" @mousedown.prevent @click.prevent.stop="place(); open = !open"
        @keydown.enter.prevent.stop="place(); open = !open">
    ?
    <span class="help-pop" role="tooltip">{{ t(text) }}</span>
  </span>
</template>
