<script setup lang="ts">
// Публикация репозитория карты на GitHub через GitHub CLI (gh repo create --source --push).
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store, toast } from "../store";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const emit = defineEmits<{ close: [] }>();

const gh = ref<{ installed: boolean; user: string | null } | null>(null);
const folder = (store.state?.path ?? "").split(/[\\/]/).slice(-2, -1)[0] ?? "";
const name = ref(folder.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "mapcan");
const isPrivate = ref(true);
const description = ref(store.state?.data?.document?.title ?? "");

const ready = computed(() => !!gh.value?.user);
const canSubmit = computed(() => ready.value && !!name.value.trim() && !store.busy);

onMounted(async () => {
  try {
    gh.value = await api.ghStatus();
  } catch {
    gh.value = { installed: false, user: null };
  }
});

async function submit() {
  if (!canSubmit.value) return;
  let url: string | null = null;
  const ok = await actions.git(async () => {
    const r = await api.ghCreate({ name: name.value.trim(), private: isPrivate.value, description: description.value });
    url = r.url;
    return r;
  }, t("Репозиторий опубликован на GitHub"));
  if (ok) {
    if (url) toast(url, "info");
    emit("close");
  }
}
</script>

<template>
  <Modal :title="t('Опубликовать на GitHub')" @close="emit('close')">
    <p v-if="!gh" class="muted">{{ t("Проверка GitHub CLI…") }}</p>
    <p v-else-if="!gh.installed" class="banner error">
      {{ t("GitHub CLI (gh) не найден. Установите его с cli.github.com и выполните «gh auth login».") }}
    </p>
    <p v-else-if="!gh.user" class="banner error">
      {{ t("GitHub CLI не авторизован. Выполните в терминале «gh auth login» и откройте это окно снова.") }}
    </p>
    <template v-else>
      <p class="muted">
        {{ t("Будет создан репозиторий на GitHub от имени {user}, он станет remote «origin», и все коммиты будут отправлены.", { user: gh.user }) }}
      </p>
      <div class="form-grid">
        <label class="field wide">
          <span class="field-label">{{ t("Имя репозитория") }}</span>
          <input v-model="name" class="mono" placeholder="repo" @keydown.enter="submit" />
          <span class="field-hint">{{ t("«repo» или «организация/repo».") }}</span>
        </label>
        <label class="field wide">
          <span class="field-label">{{ t("Описание") }}</span>
          <input v-model="description" @keydown.enter="submit" />
        </label>
        <label class="checkbox wide">
          <input v-model="isPrivate" type="checkbox" /> {{ t("Приватный репозиторий") }}
        </label>
      </div>
    </template>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="primary" :disabled="!canSubmit" @click="submit">{{ t("Опубликовать") }}</button>
    </div>
  </Modal>
</template>
