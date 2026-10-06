<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import { i18n, LANGUAGES, N_, t } from "../i18n";
import BrandMark from "./BrandMark.vue";

const emit = defineEmits<{ preview: [fmt: "html" | "pdf" | "md"]; diff: [] }>();

const menu = ref<"file" | "export" | null>(null);
const theme = ref<string>(localStorage.getItem("mapcan-theme") ?? "auto");
const hasMap = computed(() => !!store.state);
const pdfTitle = computed(() => store.pdfTemplates.find((x) => x.name === store.pdfTemplate)?.title ?? "");

function applyTheme() {
  const root = document.documentElement;
  if (theme.value === "auto") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme.value);
  try {
    localStorage.setItem("mapcan-theme", theme.value);
  } catch {
    /* хранилище недоступно */
  }
}
function cycleTheme() {
  theme.value = theme.value === "auto" ? "light" : theme.value === "light" ? "dark" : "auto";
  applyTheme();
}
applyTheme();
const THEME_NAMES: Record<string, string> = { auto: N_("как в системе"), light: N_("светлая"), dark: N_("тёмная") };

const DOWNLOADS: Array<[string, string]> = [
  ["xlsx", "Excel (.xlsx)"], ["md", "Markdown"], ["html", "HTML"],
  ["dbc", "DBC (.zip)"], ["c", N_("C-код (.zip)")], ["py", N_("Python-модуль (.zip)")],
];

const initials = computed(() => {
  const n = store.meta?.user.name.trim() ?? "";
  if (!n) return "?";
  return n.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
});

function toggle(m: "file" | "export") {
  menu.value = menu.value === m ? null : m;
}
function closeMenu(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest(".menu")) menu.value = null;
}
onMounted(() => window.addEventListener("click", closeMenu));
onBeforeUnmount(() => window.removeEventListener("click", closeMenu));
</script>

<template>
  <header class="topbar">
    <div class="brand" :title="`mapcan ${store.meta?.version ?? ''}`">
      <BrandMark /> <span class="version mono">v{{ store.meta?.version }}</span>
    </div>

    <div class="menu">
      <button @click.stop="toggle('file')">{{ t("Файл ▾") }}</button>
      <div v-if="menu === 'file'" class="dropdown left" @click="menu = null">
        <button :disabled="store.meta?.readonly" @click="store.dialog = 'new'">{{ t("Новая карта…") }}</button>
        <button @click="store.dialog = 'open'">{{ t("Открыть…") }} <kbd>Ctrl+O</kbd></button>
        <template v-if="store.meta?.recent.length">
          <div class="dd-title">{{ t("Недавние") }}</div>
          <button v-for="r in store.meta.recent.slice(0, 6)" :key="r.path" :disabled="!r.exists" :title="r.path"
                  @click="actions.openFile(r.path)">{{ r.name }} <span class="muted dd-dir">{{ r.dir }}</span></button>
        </template>
        <div class="dd-sep" />
        <button :disabled="!hasMap || !store.state?.dirty || store.state?.readonly" @click="actions.save()">{{ t("Сохранить") }} <kbd>Ctrl+S</kbd></button>
        <button :disabled="!hasMap || store.meta?.readonly" @click="store.dialog = 'saveas'">{{ t("Сохранить как…") }} <kbd>Ctrl+Shift+S</kbd></button>
        <button :disabled="!hasMap" @click="actions.reload()">{{ t("Перечитать с диска") }}</button>
        <button :disabled="!hasMap" @click="actions.closeFile()">{{ t("Закрыть карту") }}</button>
      </div>
    </div>

    <div v-if="hasMap" class="file" :title="store.state?.path">
      <span class="mono">{{ store.state?.file }}</span>
      <span v-if="store.state?.dirty" class="dirty" :title="t('Есть несохранённые изменения')">●</span>
      <span v-if="store.state?.readonly" class="badge">{{ t("только просмотр") }}</span>
    </div>
    <span v-if="!store.online" class="badge warning" :title="t('Нет связи с сервером mapcan')">{{ t("нет связи") }}</span>

    <nav v-if="hasMap" class="tabs">
      <button :class="{ active: store.tab === 'editor' }" :disabled="!store.state?.data" @click="store.tab = 'editor'">{{ t("Редактор") }}</button>
      <button :class="{ active: store.tab === 'yaml' }" @click="store.tab = 'yaml'">YAML</button>
    </nav>

    <span class="spacer" />

    <template v-if="hasMap">
      <button class="icon" :title="t('Отменить (Ctrl+Z)')" :disabled="!store.state?.can_undo || store.busy" @click="actions.undo">↶</button>
      <button class="icon" :title="t('Повторить (Ctrl+Y)')" :disabled="!store.state?.can_redo || store.busy" @click="actions.redo">↷</button>
      <button @click="emit('diff')">{{ t("Сравнить версии") }}</button>

      <div class="menu">
        <button @click.stop="toggle('export')">{{ t("Экспорт ▾") }}</button>
        <div v-if="menu === 'export'" class="dropdown" @click="menu = null">
          <div class="dd-title">{{ t("Предпросмотр") }}</div>
          <button @click="emit('preview', 'html')">HTML</button>
          <button @click="emit('preview', 'pdf')">PDF… <span class="muted dd-dir">{{ pdfTitle }}</span></button>
          <button @click="emit('preview', 'md')">Markdown</button>
          <div class="dd-title">{{ t("Скачать PDF") }}</div>
          <a v-for="t in store.pdfTemplates" :key="t.name" :href="api.exportUrl('pdf', true, t.name)" :title="t.description"
             @click="actions.setPdfTemplate(t.name)">{{ t.title }}</a>
          <div class="dd-title">{{ t("Скачать") }}</div>
          <a v-for="[f, l] in DOWNLOADS" :key="f" :href="api.exportUrl(f, true)">{{ l }}</a>
        </div>
      </div>

      <button class="primary" :title="t('Сохранить (Ctrl+S)')" :disabled="!store.state?.dirty || store.state?.readonly || store.busy"
              @click="actions.save()">{{ t("Сохранить") }}</button>
    </template>

    <button class="user-chip" :class="{ empty: !store.meta?.user.name }"
            :title="store.meta?.user.name ? t('Профиль: {name}', { name: store.meta.user.name + (store.meta.user.github ? ' (@' + store.meta.user.github + ')' : '') }) : t('Заполнить профиль автора')"
            @click="store.dialog = 'profile'">
      <span class="avatar">{{ initials }}</span>
      <span class="uname">{{ store.meta?.user.name || t("Профиль") }}</span>
    </button>
    <select class="lang-pick" :value="i18n.lang" :title="t('Язык интерфейса')"
            @change="actions.setLanguage(($event.target as HTMLSelectElement).value)">
      <option v-for="[code, label] in LANGUAGES" :key="code" :value="code">{{ label }}</option>
    </select>
    <button class="icon" :title="t('Тема: {name}', { name: t(THEME_NAMES[theme]) })" @click="cycleTheme">{{ theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐" }}</button>
  </header>
</template>
