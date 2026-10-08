<script setup lang="ts">
// Author profile: name and GitHub. Filled into the revision history entries.
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
    error.value = t("Enter a name");
    return;
  }
  saving.value = true;
  try {
    const u = await api.setUser({ name: name.value.trim(), github: github.value.trim() || null });
    if (store.meta) store.meta.user = u;
    toast(t("Profile saved"), "info");
    emit("close");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal :title="t('Author profile')" @close="emit('close')">
    <p class="muted">
      {{ t("Your name and GitHub username will appear in the map's revision history.") }}
    </p>
    <div class="form-grid">
      <label class="field wide">
        <span class="field-label">{{ t("Name") }}</span>
        <input v-model="name" :placeholder="t('Jane Smith')" @keydown.enter="save" />
      </label>
      <label class="field wide">
        <span class="field-label">GitHub</span>
        <input v-model="github" class="mono" placeholder="username" @keydown.enter="save" />
        <span class="field-hint">{{ t("Optional.") }}</span>
      </label>
    </div>
    <p v-if="error" class="banner error">{{ error }}</p>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Cancel") }}</button>
      <button class="primary" :disabled="saving" @click="save">{{ t("Save") }}</button>
    </div>
  </Modal>
</template>
