<script setup lang="ts">
// The question of askUser() (store.ts): a message and explicit buttons instead of the browser's confirm().
// askText() adds a field: Enter in it picks the default answer.
import { onMounted, ref } from "vue";
import { answerAsk, store } from "../store";
import Modal from "./Modal.vue";

const first = ref<HTMLButtonElement[] | null>(null);
const field = ref<HTMLInputElement | null>(null);
// The field, or the default answer, gets the focus, so Enter picks it and Esc (in Modal) cancels
onMounted(() => {
  if (field.value) {
    // The file name without the folder and the extension is selected, to be typed over
    const v = field.value.value;
    field.value.focus();
    field.value.setSelectionRange(v.lastIndexOf("/") + 1, v.includes(".") ? v.lastIndexOf(".") : v.length);
  } else {
    first.value?.find((b) => b.classList.contains("primary"))?.focus();
  }
});

function enter(): void {
  const primary = store.ask?.buttons.find((b) => b.kind === "primary");
  if (primary) answerAsk(primary.value);
}
</script>

<template>
  <Modal v-if="store.ask" :title="store.ask.title" @close="answerAsk(null)">
    <p class="ask-message">{{ store.ask.message }}</p>
    <input v-if="store.ask.input !== undefined" ref="field" v-model="store.ask.input" class="ask-input mono"
           :aria-label="store.ask.title" @keydown.enter.prevent="enter" />
    <div class="fd-actions">
      <span class="spacer" />
      <button v-for="b in store.ask.buttons" :key="b.value" ref="first"
              :class="b.kind" @click="answerAsk(b.value)">{{ b.label }}</button>
    </div>
  </Modal>
</template>

<style scoped>
.ask-message { white-space: pre-line; margin: 0 0 16px; max-width: 480px; }
.ask-input { display: block; width: 100%; box-sizing: border-box; margin: 0 0 16px; }
</style>
