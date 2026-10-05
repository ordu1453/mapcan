<script setup lang="ts">
import { onMounted, ref } from "vue";
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
import YamlEditor from "./components/YamlEditor.vue";

const preview = ref<"html" | "pdf" | "md" | null>(null);
const diffOpen = ref(false);

onMounted(async () => {
  await actions.load();
  if (store.state && !store.state.data) store.tab = "yaml";
  // Первый запуск: предложить заполнить профиль автора.
  try {
    if (store.meta && !store.meta.user.name && !localStorage.getItem("canmap-profile-asked")) {
      localStorage.setItem("canmap-profile-asked", "1");
      store.dialog = "profile";
    }
  } catch {
    /* хранилище недоступно */
  }
});

function keepMine() {
  store.fileChangedBanner = false;
}
</script>

<template>
  <div class="app">
    <TopBar @preview="preview = $event" @diff="diffOpen = true" />

    <div v-if="store.fileChangedBanner && store.state" class="disk-banner">
      Файл <b class="mono">{{ store.state.file }}</b> изменён на диске другой программой.
      <button @click="actions.reload()">Перечитать с диска</button>
      <button @click="keepMine">Оставить мою версию</button>
      <span v-if="store.state.dirty" class="muted">Несохранённые правки при перечитывании будут потеряны.</span>
    </div>

    <div v-if="!store.meta" class="loading">Загрузка…</div>
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
    <FileDialog v-if="store.dialog === 'open' || store.dialog === 'new' || store.dialog === 'saveas'"
                :key="store.dialog" :mode="store.dialog" @close="store.dialog = null" />
    <ProfileDialog v-if="store.dialog === 'profile'" @close="store.dialog = null" />

    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
    </div>
  </div>
</template>
