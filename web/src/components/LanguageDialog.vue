<script setup lang="ts">
// Выбор языка интерфейса при первом запуске. Заголовок — на обоих языках: пользователь ещё не выбрал.
import { LANGUAGES } from "../i18n";
import { actions } from "../store";
import Modal from "./Modal.vue";

const emit = defineEmits<{ close: [] }>();

async function choose(lang: string) {
  await actions.setLanguage(lang);
  emit("close");
}
</script>

<template>
  <Modal title="Language · Язык" @close="choose('en')">
    <p class="muted">Choose the interface language. You can change it later in the top bar.</p>
    <p class="muted">Выберите язык интерфейса. Его можно сменить позже на верхней панели.</p>
    <div class="lang-choice">
      <button v-for="[code, label] in LANGUAGES" :key="code" class="primary" @click="choose(code)">{{ label }}</button>
    </div>
  </Modal>
</template>
