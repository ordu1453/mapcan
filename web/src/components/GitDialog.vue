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
      : [t("Version {version}", { version }), ...(changes.length ? ["", ...changes.map((c) => `- ${c}`)] : [])].join("\n");
  }
});

async function submit() {
  if (!canSubmit.value) return;
  const ok = props.mode === "commit"
    ? await actions.git(() => api.gitCommit(message.value, tag.value.trim()), t("Commit created"))
    : await actions.git(() => api.gitTag(tag.value.trim(), message.value), t("Tag created"));
  if (ok) emit("close");
}
</script>

<template>
  <Modal :title="mode === 'commit' ? t('Commit to git') : t('Version tag')" @close="emit('close')">
    <p v-if="mode === 'commit'" class="muted">
      {{ t("Only the map file and its logo are committed; other changes in the repository are not affected.") }}
    </p>
    <p v-else class="muted">
      {{ t("The tag goes on the latest commit of {branch}.", { branch: store.git?.branch ?? "HEAD" }) }}
    </p>
    <p v-if="tagStale" class="banner warning">
      {{ t("The map has uncommitted changes, and the tag will not include them. To tag the current version, commit it with a tag.") }}
    </p>
    <div class="form-grid">
      <label v-if="mode === 'tag'" class="field wide">
        <span class="field-label">{{ t("Tag name") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
        <span v-if="tagTaken" class="field-hint git-warn">{{ t("This tag already exists.") }}</span>
      </label>
      <label class="field wide">
        <span class="field-label">{{ mode === "commit" ? t("Commit message") : t("Tag message") }}</span>
        <textarea v-model="message" rows="4" @keydown.ctrl.enter="submit" />
        <span v-if="mode === 'tag'" class="field-hint">{{ t("Optional.") }}</span>
      </label>
      <label v-if="mode === 'commit'" class="field wide">
        <span class="field-label">{{ t("Version tag") }}</span>
        <input v-model="tag" class="mono" placeholder="v1.0.0" @keydown.enter="submit" />
        <span v-if="tagTaken" class="field-hint git-warn">{{ t("This tag already exists.") }}</span>
        <span v-else class="field-hint">{{ t("Optional.") }}</span>
      </label>
    </div>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Cancel") }}</button>
      <button class="primary" :disabled="!canSubmit" @click="submit">
        {{ mode === "commit" ? t("Commit") : t("Create tag") }}
      </button>
    </div>
  </Modal>
</template>
