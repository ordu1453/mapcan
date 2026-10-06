<script setup lang="ts">
import { onMounted, ref } from "vue";
import { api } from "./api";
import { actions, store } from "./store";
import DiagnosticsPanel from "./components/DiagnosticsPanel.vue";
import DiffDialog from "./components/DiffDialog.vue";
import FileDialog from "./components/FileDialog.vue";
import MapTree from "./components/MapTree.vue";
import NodeEditor from "./components/NodeEditor.vue";
import PreviewDialog from "./components/PreviewDialog.vue";
import ProfileDialog from "./components/ProfileDialog.vue";
import StartScreen from "./components/StartScreen.vue";
import TopBar from "./components/TopBar.vue";
import GitDialog from "./components/GitDialog.vue";
import GhPublishDialog from "./components/GhPublishDialog.vue";
import YamlEditor from "./components/YamlEditor.vue";
import { LANGUAGES, t } from "./i18n";

const preview = ref<"html" | "pdf" | "md" | null>(null);
const diffOpen = ref(false);

onMounted(async () => {
  await actions.load();
  if (store.state && !store.state.data) store.tab = "yaml";
  // Первый запуск: язык — по языку браузера (сменить можно на верхней панели), затем — профиль автора.
  if (store.meta && !store.meta.language_chosen) await actions.setLanguage(detectLanguage());
  askProfile();
  void checkUpdate();
});

function askProfile() {
  try {
    if (store.meta && !store.meta.user.name && !localStorage.getItem("mapcan-profile-asked")) {
      localStorage.setItem("mapcan-profile-asked", "1");
      store.dialog = "profile";
    }
  } catch {
    /* хранилище недоступно */
  }
}

function detectLanguage(): string {
  const codes = LANGUAGES.map(([code]) => code);
  for (const tag of navigator.languages?.length ? navigator.languages : [navigator.language]) {
    const code = (tag ?? "").slice(0, 2).toLowerCase();
    if (codes.includes(code as (typeof codes)[number])) return code;
  }
  return "en";
}

const UPDATE_KEY = "mapcan-update-dismissed";

async function checkUpdate() {
  try {
    const u = await api.update();
    let dismissed = "";
    try {
      dismissed = localStorage.getItem(UPDATE_KEY) ?? "";
    } catch {
      /* хранилище недоступно */
    }
    if (u.newer && u.latest !== dismissed) store.update = u;
  } catch {
    /* проверка обновлений не важна для работы */
  }
}

function dismissUpdate() {
  try {
    if (store.update?.latest) localStorage.setItem(UPDATE_KEY, store.update.latest);
  } catch {
    /* хранилище недоступно */
  }
  store.update = null;
}

function keepMine() {
  store.fileChangedBanner = false;
}
</script>

<template>
  <div class="app">
    <TopBar @preview="preview = $event" @diff="diffOpen = true" />

    <div v-if="store.update" class="update-banner">
      {{ t("Доступна новая версия mapcan {latest} (у вас {current}).",
            { latest: store.update.latest, current: store.update.current }) }}
      <a v-if="store.update.installer" class="button small primary-link" :href="store.update.installer"
         target="_blank" rel="noopener">{{ t("Скачать установщик") }}</a>
      <a class="button small" :href="store.update.url" target="_blank" rel="noopener">{{ t("Что нового") }}</a>
      <button class="small" @click="dismissUpdate">{{ t("Скрыть") }}</button>
    </div>

    <div v-if="store.fileChangedBanner && store.state" class="disk-banner">
      {{ t("Файл {file} изменён на диске другой программой.", { file: store.state.file }) }}
      <button @click="actions.reload()">{{ t("Перечитать с диска") }}</button>
      <button @click="keepMine">{{ t("Оставить мою версию") }}</button>
      <span v-if="store.state.dirty" class="muted">{{ t("Несохранённые правки при перечитывании будут потеряны.") }}</span>
    </div>

    <div v-if="!store.meta" class="loading">{{ t("Загрузка…") }}</div>
    <StartScreen v-else-if="!store.state" />
    <main v-else class="workspace" :class="{ 'no-tree': store.tab === 'yaml' && !store.state.data }">
      <MapTree v-if="store.state.data" :key="'t' + store.state.session_id" />
      <div class="content">
        <NodeEditor v-if="store.tab === 'editor'" />
        <YamlEditor v-else :key="'y' + store.state.session_id" />
      </div>
    </main>
    <DiagnosticsPanel v-if="store.state" />

    <PreviewDialog v-if="preview" :fmt="preview" @close="preview = null" />
    <DiffDialog v-if="diffOpen" @close="diffOpen = false" />
    <FileDialog v-if="store.dialog === 'open' || store.dialog === 'new' || store.dialog === 'saveas' || store.dialog === 'example'"
                :key="store.dialog" :mode="store.dialog" @close="store.dialog = null" />
    <ProfileDialog v-if="store.dialog === 'profile'" @close="store.dialog = null" />
    <GitDialog v-if="store.dialog === 'git-commit' || store.dialog === 'git-tag'"
               :mode="store.dialog === 'git-commit' ? 'commit' : 'tag'" @close="store.dialog = null" />
    <GhPublishDialog v-if="store.dialog === 'gh-publish'" @close="store.dialog = null" />

    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
    </div>
  </div>
</template>
