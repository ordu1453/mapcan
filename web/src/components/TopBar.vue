<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import { i18n, LANGUAGES, N_, t } from "../i18n";
import BrandMark from "./BrandMark.vue";

const emit = defineEmits<{ preview: [fmt: "html" | "pdf" | "md"]; diff: [] }>();

type Menu = "file" | "export" | "git";
const menu = ref<Menu | null>(null);
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

// Экспорт: одна строка на формат. Документы открываются в предпросмотре (шаблон PDF выбирается там),
// ↓ справа — сразу скачать; остальные форматы только скачиваются.
interface ExportItem { fmt: string; label: string; hint?: string; preview?: "html" | "pdf" | "md" }
const DOCUMENTS: ExportItem[] = [
  { fmt: "pdf", label: "PDF", preview: "pdf" },
  { fmt: "html", label: "HTML", preview: "html" },
  { fmt: "md", label: "Markdown", preview: "md" },
  { fmt: "xlsx", label: "Excel", hint: ".xlsx" },
];
const DEV: ExportItem[] = [
  { fmt: "dbc", label: "DBC", hint: ".zip" },
  { fmt: "c", label: N_("C-код"), hint: ".zip" },
  { fmt: "py", label: N_("Python-модуль"), hint: ".zip" },
];
function downloadUrl(it: ExportItem) {
  return api.exportUrl(it.fmt, true, it.fmt === "pdf" ? store.pdfTemplate : undefined);
}

// ---- git
const git = computed(() => store.git);
const unsaved = computed(() => !!store.state?.dirty);
const FILE_STATE: Record<string, string> = {
  clean: N_("файл закоммичен"), modified: N_("есть незакоммиченные изменения"), untracked: N_("файл не добавлен в git"),
};
const gitPending = computed(() => !!git.value?.available && git.value.file !== "clean");

function gitAction(fn: () => Promise<unknown>) {
  menu.value = null;
  void fn();
}
const gitInit = () => gitAction(() => actions.git(api.gitInit, t("Репозиторий создан")));
const gitPull = () => gitAction(() => actions.git(api.gitPull, t("Изменения получены")));
const gitPush = () => gitAction(() => actions.git(api.gitPush, t("Изменения отправлены")));

watch(() => [store.state?.session_id, store.state?.dirty, store.meta?.readonly], () => void actions.refreshGit(),
      { immediate: true });
const onFocus = () => void actions.refreshGit();

const initials = computed(() => {
  const n = store.meta?.user.name.trim() ?? "";
  if (!n) return "?";
  return n.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
});

function toggle(m: Menu) {
  menu.value = menu.value === m ? null : m;
  if (menu.value === "git") void actions.refreshGit();
}
function closeMenu(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest(".menu")) menu.value = null;
}
onMounted(() => {
  window.addEventListener("click", closeMenu);
  window.addEventListener("focus", onFocus);
});
onBeforeUnmount(() => {
  window.removeEventListener("click", closeMenu);
  window.removeEventListener("focus", onFocus);
});
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
      <!-- Git: сравнение версий карты и работа с репозиторием -->
      <div class="menu">
        <button :title="git?.available ? t(FILE_STATE[git.file ?? 'clean'])
                  : git?.reason === 'no-repo' ? t('Папка карты не в репозитории git') : ''"
                @click.stop="toggle('git')">
          Git<span v-if="gitPending" class="git-dot">●</span><span v-if="git?.ahead" class="git-count">↑{{ git.ahead }}</span> ▾
        </button>
        <div v-if="menu === 'git'" class="dropdown git-menu">
          <button @click="menu = null; emit('diff')">{{ t("Сравнить версии…") }}</button>
          <div class="dd-sep" />
          <template v-if="git?.available">
            <div class="git-head">
              <div><span class="muted">{{ t("Ветка") }}</span> <b class="mono">{{ git.branch ?? t("(не на ветке)") }}</b>
                <span v-if="git.upstream" class="muted mono">→ {{ git.upstream }}</span></div>
              <div :class="{ 'git-warn': gitPending }">{{ t(FILE_STATE[git.file ?? "clean"]) }}</div>
              <div v-if="git.ahead || git.behind" class="muted">
                {{ t("не отправлено: {ahead}, не получено: {behind}", { ahead: git.ahead ?? 0, behind: git.behind ?? 0 }) }}
              </div>
              <div v-if="git.last" class="muted dd-dir git-last" :title="git.last.subject">
                <span class="mono">{{ git.last.rev }}</span> {{ git.last.subject }}
              </div>
            </div>
            <div v-if="unsaved" class="dd-note">{{ t("Сохраните карту, чтобы закоммитить изменения.") }}</div>
            <div class="dd-sep" />
            <button :disabled="unsaved || !gitPending || store.busy" @click="menu = null; store.dialog = 'git-commit'">{{ t("Закоммитить…") }}</button>
            <button :disabled="unsaved || !git.last || store.busy" @click="menu = null; store.dialog = 'git-tag'">{{ t("Поставить тег…") }}</button>
            <div class="dd-sep" />
            <template v-if="git.remote">
              <button :disabled="unsaved || !git.upstream || store.busy"
                      :title="git.upstream ? '' : t('Ветка ещё не отправлена в {remote}', { remote: git.remote })"
                      @click="gitPull">{{ t("Получить изменения (pull)") }}</button>
              <button :disabled="unsaved || !git.last || store.busy" @click="gitPush">
                {{ t("Отправить в {remote} (push)", { remote: git.remote }) }}<span v-if="git.ahead" class="muted">↑{{ git.ahead }}</span>
              </button>
            </template>
            <button v-else :disabled="unsaved || !git.last || store.busy"
                    :title="git.last ? '' : t('Сначала закоммитьте карту')"
                    @click="menu = null; store.dialog = 'gh-publish'">{{ t("Опубликовать на GitHub…") }}</button>
          </template>
          <template v-else-if="git?.reason === 'no-repo'">
            <div class="dd-note">{{ t("Папка карты не в репозитории git. Создайте репозиторий, чтобы хранить версии карты.") }}</div>
            <button :disabled="store.busy" @click="gitInit">{{ t("Создать репозиторий здесь") }}</button>
          </template>
          <div v-else-if="git?.reason === 'error'" class="dd-note">{{ git.error }}</div>
          <div v-else-if="git" class="dd-note">{{ t("git не найден. Установите git, чтобы коммитить и отправлять версии карты.") }}</div>
        </div>
      </div>

      <div class="menu">
        <button @click.stop="toggle('export')">{{ t("Экспорт ▾") }}</button>
        <div v-if="menu === 'export'" class="dropdown export-menu" @click="menu = null">
          <template v-for="[title, items] in ([[t('Документы'), DOCUMENTS], [t('Для разработки'), DEV]] as const)" :key="title">
            <div class="dd-title">{{ title }}</div>
            <div v-for="it in items" :key="it.fmt" class="dd-row">
              <button v-if="it.preview" :title="t('Предпросмотр')" @click="emit('preview', it.preview)">
                {{ t(it.label) }} <span class="muted dd-dir">{{ it.fmt === "pdf" ? pdfTitle : "" }}</span>
              </button>
              <a v-else :href="downloadUrl(it)">{{ t(it.label) }} <span class="muted dd-dir">{{ it.hint }}</span></a>
              <a class="dd-dl" :href="downloadUrl(it)" :title="t('Скачать')">↓</a>
            </div>
          </template>
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
