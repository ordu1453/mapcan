<script setup lang="ts">
// Профиль автора: имя и GitHub. Подставляется в записи истории изменений.
import { ref } from "vue";
import { api } from "../api";
import { store, toast } from "../store";
import Modal from "./Modal.vue";

const emit = defineEmits<{ close: [] }>();

const name = ref(store.meta?.user.name ?? "");
const github = ref(store.meta?.user.github ?? "");
const error = ref("");
const saving = ref(false);

async function save() {
  if (!name.value.trim()) {
    error.value = "Укажите имя";
    return;
  }
  saving.value = true;
  try {
    const u = await api.setUser({ name: name.value.trim(), github: github.value.trim() || null });
    if (store.meta) store.meta.user = u;
    toast("Профиль сохранён", "info");
    emit("close");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Modal title="Профиль автора" @close="emit('close')">
    <p class="muted">
      Имя и GitHub подставляются в записи истории изменений карты («Сравнить версии» → «Добавить в историю»)
      и попадают в Excel, PDF, Markdown и HTML. Профиль хранится на этом компьютере
      (<span class="mono">~/.canmap/config.json</span>).
    </p>
    <div class="form-grid">
      <label class="field wide">
        <span class="field-label">Имя</span>
        <input v-model="name" placeholder="Иван Петров" @keydown.enter="save" />
      </label>
      <label class="field wide">
        <span class="field-label">GitHub</span>
        <input v-model="github" class="mono" placeholder="username или https://github.com/username" @keydown.enter="save" />
        <span class="field-hint">Необязательно. Ссылка на профиль появится рядом с именем в истории.</span>
      </label>
    </div>
    <p v-if="error" class="banner error">{{ error }}</p>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">Отмена</button>
      <button class="primary" :disabled="saving" @click="save">Сохранить</button>
    </div>
  </Modal>
</template>
