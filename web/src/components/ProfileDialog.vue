<script setup lang="ts">
// Профиль автора: имя и GitHub. Подставляется в записи истории изменений.
import { ref } from "vue";
import { api } from "../api";
import { store, toast } from "../store";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const emit = defineEmits<{ close: [] }>();

const name = ref(store.meta?.user.name ?? "");
const github = ref(store.meta?.user.github ?? "");
const error = ref("");
const saving = ref(false);

async function save() {
  if (!name.value.trim()) {
    error.value = t("Укажите имя");
    return;
  }
  saving.value = true;
  try {
    const u = await api.setUser({ name: name.value.trim(), github: github.value.trim() || null });
    if (store.meta) store.meta.user = u;
    toast(t("Профиль сохранён"), "info");
    emit("close");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal :title="t('Профиль автора')" @close="emit('close')">
    <p class="muted">
      {{ t("Имя и GitHub будут указаны в записях истории изменений карты.") }}
    </p>
    <div class="form-grid">
      <label class="field wide">
        <span class="field-label">{{ t("Имя") }}</span>
        <input v-model="name" :placeholder="t('Иван Петров')" @keydown.enter="save" />
      </label>
      <label class="field wide">
        <span class="field-label">GitHub</span>
        <input v-model="github" class="mono" placeholder="username" @keydown.enter="save" />
        <span class="field-hint">{{ t("Необязательно.") }}</span>
      </label>
    </div>
    <p v-if="error" class="banner error">{{ error }}</p>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="primary" :disabled="saving" @click="save">{{ t("Сохранить") }}</button>
    </div>
  </Modal>
</template>
