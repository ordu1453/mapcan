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
    toast(t("Version {version} released: commit and tag {tag}", { version: version.value.trim(), tag: r.tag }), "info");
    emit("close");
  } catch (e) {
    toast(e instanceof Error ? e.message : String(e));
  } finally {
    store.busy = false;
  }
}
</script>

<template>
  <Modal :title="t('Release version')" @close="emit('close')">
    <p class="muted">
      {{ t("An entry is added to the revision history, the document's version and date are updated, and the map is saved and committed with a version tag.") }}
    </p>
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="!draft" class="muted">{{ t("Comparing…") }}</p>
    <template v-else>
      <p v-if="draft.recorded" class="banner info">
        {{ t("The revision history already has an entry for version {version}; no new entry is added.", { version: draft.version }) }}
      </p>
      <div class="form-grid">
        <label class="field">
          <span class="field-label">{{ t("New version") }}</span>
          <input v-model="version" class="mono" @keydown.enter="submit" />
          <span v-if="tagTaken" class="field-hint git-warn">{{ t("This tag already exists.") }}</span>
          <span v-else class="field-hint">{{ t("Tag: {tag}", { tag }) }}</span>
        </label>
        <label class="field wide">
          <span class="field-label">
            {{ t("Changes (one per line)") }}
            <span v-if="draft.base" class="muted">· {{ t("since {base}", { base: draft.base }) }}</span>
          </span>
          <textarea v-model="changes" rows="8" :readonly="draft.recorded" />
        </label>
      </div>
      <p class="muted">
        {{ t("Author:") }}
        <template v-if="store.meta?.user.name">
          <b>{{ store.meta.user.name }}</b>
          <span v-if="store.meta.user.github" class="mono">@{{ store.meta.user.github }}</span>
        </template>
        <template v-else>{{ t("not set —") }}</template>
        <button class="link" @click="store.dialog = 'profile'">{{ store.meta?.user.name ? t("edit") : t("fill in profile") }}</button>
      </p>
    </template>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Cancel") }}</button>
      <button class="primary" :disabled="!canSubmit" @click="submit">{{ t("Release") }}</button>
    </div>
  </Modal>
</template>
