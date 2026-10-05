<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";

const emit = defineEmits<{ preview: [fmt: "html" | "pdf" | "md"]; diff: [] }>();

const menu = ref(false);
const theme = ref<string>(localStorage.getItem("canmap-theme") ?? "auto");

function applyTheme() {
  const root = document.documentElement;
  if (theme.value === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme.value);
  try {
    localStorage.setItem("canmap-theme", theme.value);
  } catch {
    /* хранилище недоступно */
  }
}
function cycleTheme() {
  theme.value = theme.value === "auto" ? "light" : theme.value === "light" ? "dark" : "auto";
  applyTheme();
}
applyTheme();

const DOWNLOADS: Array<[string, string]> = [
  ["xlsx", "Excel (.xlsx)"], ["pdf", "PDF"], ["md", "Markdown"], ["html", "HTML"],
  ["dbc", "DBC (.zip)"], ["c", "C-код (.zip)"], ["py", "Python-модуль (.zip)"],
];

function closeMenu(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest(".export-menu")) menu.value = false;
}
onMounted(() => window.addEventListener("click", closeMenu));
onBeforeUnmount(() => window.removeEventListener("click", closeMenu));
</script>

<template>
  <header class="topbar">
    <div class="brand">canmap</div>
    <div class="file" :title="store.state?.path">
      <span class="mono">{{ store.state?.file }}</span>
      <span v-if="store.state?.dirty" class="dirty" title="Есть несохранённые изменения">●</span>
      <span v-if="store.state?.readonly" class="badge">только просмотр</span>
      <span v-if="!store.online" class="badge warning" title="Нет связи с сервером canmap">нет связи</span>
    </div>

    <nav class="tabs">
      <button :class="{ active: store.tab === 'editor' }" :disabled="!store.state?.data" @click="store.tab = 'editor'">Редактор</button>
      <button :class="{ active: store.tab === 'yaml' }" @click="store.tab = 'yaml'">YAML</button>
    </nav>

    <span class="spacer" />

    <button class="icon" title="Отменить (Ctrl+Z)" :disabled="!store.state?.can_undo || store.busy" @click="actions.undo">↶</button>
    <button class="icon" title="Повторить (Ctrl+Y)" :disabled="!store.state?.can_redo || store.busy" @click="actions.redo">↷</button>
    <button @click="emit('diff')">Сравнить версии</button>

    <div class="export-menu">
      <button @click.stop="menu = !menu">Экспорт ▾</button>
      <div v-if="menu" class="dropdown" @click="menu = false">
        <div class="dd-title">Предпросмотр</div>
        <button @click="emit('preview', 'html')">HTML</button>
        <button @click="emit('preview', 'pdf')">PDF</button>
        <button @click="emit('preview', 'md')">Markdown</button>
        <div class="dd-title">Скачать</div>
        <a v-for="[f, l] in DOWNLOADS" :key="f" :href="api.exportUrl(f, true)">{{ l }}</a>
      </div>
    </div>

    <button class="primary" title="Сохранить (Ctrl+S)" :disabled="!store.state?.dirty || store.state?.readonly || store.busy"
            @click="actions.save()">Сохранить</button>
    <button class="icon" :title="`Тема: ${theme}`" @click="cycleTheme">{{ theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐" }}</button>
  </header>
</template>
