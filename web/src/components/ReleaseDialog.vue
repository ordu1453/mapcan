<script setup lang="ts">
// Выпуск версии одним действием: запись в истории изменений (document.history), версия и дата документа,
// сохранение, коммит карты и тег v<версия>. Изменения подставляются из различий с прошлым выпуском.
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { store, toast } from "../store";
import type { ReleaseDraft } from "../types";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const emit = defineEmits<{ close: [] }>();

const draft = ref<ReleaseDraft | null>(null);
const version = ref("");
const changes = ref("");
const error = ref("");
const allTags = ref<string[]>([]);

const tag = computed(() => `v${version.value.trim()}`);
const tagTaken = computed(() => !!version.value.trim() && allTags.value.includes(tag.value));
const lines = computed(() => changes.value.split("\n").map((s) => s.trim()).filter(Boolean));
const canSubmit = computed(() => !store.busy && !!draft.value && !!version.value.trim() && !tagTaken.value);

onMounted(async () => {
  try {
    const [d, revs] = await Promise.all([api.gitReleaseDraft(), api.gitRevs().catch(() => null)]);
    allTags.value = revs?.all_tags ?? [];
    draft.value = d;
    version.value = d.version;
    changes.value = d.changes.join("\n");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});

async function submit() {
  if (!canSubmit.value) return;
  store.busy = true;
  try {
    const r = await api.gitRelease(version.value.trim(), lines.value);
    store.git = r.git;
    toast(t("Версия {version} выпущена: коммит и тег {tag}", { version: version.value.trim(), tag: r.tag }), "info");
    emit("close");
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e));
  } finally {
    store.busy = false;
  }
}
</script>

<template>
  <Modal :title="t('Выпустить версию')" @close="emit('close')">
    <p class="muted">
      {{ t("Запись добавится в историю изменений, версия и дата документа обновятся, карта сохранится и будет закоммичена с тегом версии.") }}
    </p>
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="!draft" class="muted">{{ t("Сравнение…") }}</p>
    <template v-else>
      <p v-if="draft.recorded" class="banner info">
        {{ t("Запись версии {version} уже есть в истории изменений — новая не добавится.", { version: draft.version }) }}
      </p>
      <div class="form-grid">
        <label class="field">
          <span class="field-label">{{ t("Новая версия") }}</span>
          <input v-model="version" class="mono" @keydown.enter="submit" />
          <span v-if="tagTaken" class="field-hint git-warn">{{ t("Такой тег уже есть.") }}</span>
          <span v-else class="field-hint">{{ t("Тег: {tag}", { tag }) }}</span>
        </label>
        <label class="field wide">
          <span class="field-label">
            {{ t("Изменения (по строке)") }}
            <span v-if="draft.base" class="muted">· {{ t("с {base}", { base: draft.base }) }}</span>
          </span>
          <textarea v-model="changes" rows="8" :readonly="draft.recorded" />
        </label>
      </div>
      <p class="muted">
        {{ t("Автор:") }}
        <template v-if="store.meta?.user.name">
          <b>{{ store.meta.user.name }}</b>
          <span v-if="store.meta.user.github" class="mono">@{{ store.meta.user.github }}</span>
        </template>
        <template v-else>{{ t("не указан —") }}</template>
        <button class="link" @click="store.dialog = 'profile'">{{ store.meta?.user.name ? t("изменить") : t("заполнить профиль") }}</button>
      </p>
    </template>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="primary" :disabled="!canSubmit" @click="submit">{{ t("Выпустить") }}</button>
    </div>
  </Modal>
</template>
