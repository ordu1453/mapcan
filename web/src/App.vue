<script setup lang="ts">
import { onMounted, ref } from "vue";
import { actions, store } from "./store";
import DiagnosticsPanel from "./components/DiagnosticsPanel.vue";
import DiffDialog from "./components/DiffDialog.vue";
import MapTree from "./components/MapTree.vue";
import NodeEditor from "./components/NodeEditor.vue";
import PreviewDialog from "./components/PreviewDialog.vue";
import TopBar from "./components/TopBar.vue";
import YamlEditor from "./components/YamlEditor.vue";

const preview = ref<"html" | "pdf" | "md" | null>(null);
const diffOpen = ref(false);

onMounted(async () => {
  await actions.load();
  if (store.state && !store.state.data) store.tab = "yaml";
});

function keepMine() {
  store.fileChangedBanner = false;
}
</script>

<template>
  <div class="app">
    <TopBar @preview="preview = $event" @diff="diffOpen = true" />

    <div v-if="store.fileChangedBanner" class="disk-banner">
      Файл <b class="mono">{{ store.state?.file }}</b> изменён на диске другой программой.
      <button @click="actions.reload()">Перечитать с диска</button>
      <button @click="keepMine">Оставить мою версию</button>
      <span v-if="store.state?.dirty" class="muted">Несохранённые правки при перечитывании будут потеряны.</span>
    </div>

    <div v-if="!store.state" class="loading">Загрузка…</div>
    <main v-else class="workspace" :class="{ 'no-tree': store.tab === 'yaml' && !store.state.data }">
      <MapTree v-if="store.state.data" />
      <div class="content">
        <NodeEditor v-if="store.tab === 'editor'" />
        <YamlEditor v-else />
      </div>
    </main>
    <DiagnosticsPanel v-if="store.state" />

    <PreviewDialog v-if="preview" :fmt="preview" @close="preview = null" />
    <DiffDialog v-if="diffOpen" @close="diffOpen = false" />

    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">{{ t.text }}</div>
    </div>
  </div>
</template>
