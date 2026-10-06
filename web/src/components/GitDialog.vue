<script setup lang="ts">
// Коммит карты в git (с необязательным тегом версии) или отдельный тег на текущий коммит.
import { computed, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const props = defineProps<{ mode: "commit" | "tag" }>();
const emit = defineEmits<{ close: [] }>();

const message = ref("");
const tag = ref("");

const canSubmit = computed(() => !store.busy && (props.mode === "commit" ? !!message.value.trim() : !!tag.value.trim()));

async function submit() {
  if (!canSubmit.value) return;
  const ok = props.mode === "commit"
    ? await actions.git(() => api.gitCommit(message.value, tag.value.trim()), t("Коммит создан"))
    : await actions.git(() => api.gitTag(tag.value.trim(), message.value), t("Тег создан"));
  if (ok) emit("close");
}
</script>

<template>
  <Modal :title="mode === 'commit' ? t('Коммит в git') : t('Тег версии')" @close="emit('close')">
    <p v-if="mode === 'commit'" class="muted">
      {{ t("В коммит попадут только файл карты и её логотип; остальные изменения в репозитории не затрагиваются.") }}
    </p>
    <p v-else class="muted">
      {{ t("Тег ставится на последний коммит ветки {branch}.", { branch: store.git?.branch ?? "HEAD" }) }}
    </p>
    <div class="form-grid">
      <label v-if="mode === 'tag'" class="field wide">
        <span class="field-label">{{ t("Имя тега") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
      </label>
      <label class="field wide">
        <span class="field-label">{{ mode === "commit" ? t("Описание коммита") : t("Описание тега") }}</span>
        <textarea v-model="message" rows="3" @keydown.ctrl.enter="submit" />
        <span v-if="mode === 'tag'" class="field-hint">{{ t("Необязательно. С описанием создаётся аннотированный тег.") }}</span>
      </label>
      <label v-if="mode === 'commit'" class="field wide">
        <span class="field-label">{{ t("Тег версии") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
        <span class="field-hint">{{ t("Необязательно.") }}</span>
      </label>
    </div>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="primary" :disabled="!canSubmit" @click="submit">
        {{ mode === "commit" ? t("Закоммитить") : t("Создать тег") }}
      </button>
    </div>
  </Modal>
</template>
