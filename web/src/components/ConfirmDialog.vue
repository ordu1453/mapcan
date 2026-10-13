<script setup lang="ts">
// The question of askUser() (store.ts): a message and explicit buttons instead of the browser's confirm().
import { onMounted, ref } from "vue";
import { answerAsk, store } from "../store";
import Modal from "./Modal.vue";

const first = ref<HTMLButtonElement[] | null>(null);
// The default answer gets the focus, so Enter picks it and Esc (in Modal) cancels
onMounted(() => first.value?.find((b) => b.classList.contains("primary"))?.focus());
</script>

<template>
  <Modal v-if="store.ask" :title="store.ask.title" @close="answerAsk(null)">
    <p class="ask-message">{{ store.ask.message }}</p>
    <div class="fd-actions">
      <span class="spacer" />
      <button v-for="b in store.ask.buttons" :key="b.value" ref="first"
              :class="b.kind" @click="answerAsk(b.value)">{{ b.label }}</button>
    </div>
  </Modal>
</template>

<style scoped>
.ask-message { white-space: pre-line; margin: 0 0 16px; max-width: 480px; }
</style>
