<script setup lang="ts">
// Коммит карты в git (с необязательным тегом версии) или отдельный тег на текущий коммит.
// Описание и тег подставляются из последней записи истории изменений, если её версия ещё без тега.
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import { txt } from "../model";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const props = defineProps<{ mode: "commit" | "tag" }>();
const emit = defineEmits<{ close: [] }>();

const message = ref("");
const tag = ref("");
const allTags = ref<string[]>([]);

const tagTaken = computed(() => !!tag.value.trim() && allTags.value.includes(tag.value.trim()));
// Тег ставится на последний коммит, а в карте есть изменения после него
const tagStale = computed(() => props.mode === "tag" && !!store.git?.available && store.git.file !== "clean");
const canSubmit = computed(() => !store.busy && !tagTaken.value
  && (props.mode === "commit" ? !!message.value.trim() : !!tag.value.trim()));

onMounted(async () => {
  try {
    allTags.value = (await api.gitRevs()).all_tags ?? [];
  } catch {
    /* без списка тегов просто не подставляем имя */
  }
  const doc = store.state?.data?.document ?? {};
  const version = String(doc.version ?? "").trim();
  if (!version) return;
  const name = `v${version}`;
  if (allTags.value.includes(name) || allTags.value.includes(version)) return;   // эта версия уже помечена
  tag.value = name;
  const entry = (doc.history ?? [])[0];
  if (entry && String(entry.version ?? "").trim() === version) {
    const lang = store.state?.resolved?.language ?? "ru";
    const changes = ((entry.changes ?? []) as unknown[]).map((c) => txt(c, lang).trim()).filter(Boolean);
    message.value = changes.length === 1
      ? `${version}: ${changes[0]}`
      : [t("Версия {version}", { version }), ...(changes.length ? ["", ...changes.map((c) => `- ${c}`)] : [])].join("\n");
  }
});

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
    <p v-if="tagStale" class="banner warning">
      {{ t("В карте есть незакоммиченные изменения — тег их не включит. Чтобы пометить текущую версию, закоммитьте её с тегом.") }}
    </p>
    <div class="form-grid">
      <label v-if="mode === 'tag'" class="field wide">
        <span class="field-label">{{ t("Имя тега") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
        <span v-if="tagTaken" class="field-hint git-warn">{{ t("Такой тег уже есть.") }}</span>
      </label>
      <label class="field wide">
        <span class="field-label">{{ mode === "commit" ? t("Описание коммита") : t("Описание тега") }}</span>
        <textarea v-model="message" rows="4" @keydown.ctrl.enter="submit" />
        <span v-if="mode === 'tag'" class="field-hint">{{ t("Необязательно.") }}</span>
      </label>
      <label v-if="mode === 'commit'" class="field wide">
        <span class="field-label">{{ t("Тег версии") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
        <span v-if="tagTaken" class="field-hint git-warn">{{ t("Такой тег уже есть.") }}</span>
        <span v-else class="field-hint">{{ t("Необязательно.") }}</span>
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
