<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { actions, exportLang, lang, store } from "../store";
import { docLanguages, N_, t } from "../i18n";
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
    /* storage is not available */
  }
}
function cycleTheme() {
  theme.value = theme.value === "auto" ? "light" : theme.value === "light" ? "dark" : "auto";
  applyTheme();
}
applyTheme();
const THEME_NAMES: Record<string, string> = { auto: N_("system"), light: N_("light"), dark: N_("dark") };

// Export: one row per format. Documents open in the preview (the PDF template is chosen there),
// ↓ on the right downloads right away; the other formats are only downloaded.
interface ExportItem { fmt: string; label: string; hint?: string; preview?: "html" | "pdf" | "md" }
const DOCUMENTS: ExportItem[] = [
  { fmt: "pdf", label: "PDF", preview: "pdf" },
  { fmt: "html", label: "HTML", preview: "html" },
  { fmt: "md", label: "Markdown", preview: "md" },
  { fmt: "xlsx", label: "Excel", hint: ".xlsx" },
];
const DEV: ExportItem[] = [
  { fmt: "dbc", label: "DBC", hint: ".zip" },
  { fmt: "eds", label: "EDS", hint: ".zip" },
  { fmt: "c", label: N_("C code"), hint: ".zip" },
  { fmt: "py", label: N_("Python module"), hint: ".zip" },
];
function downloadUrl(it: ExportItem) {
  const doc = DOCUMENTS.includes(it);
  return api.exportUrl(it.fmt, true, it.fmt === "pdf" ? store.pdfTemplate : undefined, doc ? exportLang(it.fmt) : undefined);
}

// ---- git
const git = computed(() => store.git);
const unsaved = computed(() => !!store.state?.dirty);
const FILE_STATE: Record<string, string> = {
  clean: N_("file is committed"), modified: N_("uncommitted changes"), untracked: N_("file is not tracked by git"),
  ignored: N_("file is excluded by .gitignore"),
};
const gitPending = computed(() => !!git.value?.available && (git.value.file === "modified" || git.value.file === "untracked"));
const remoteLabel = computed(() => git.value?.remote_url?.replace(/^https?:\/\//, "") ?? "");

function gitAction(fn: () => Promise<unknown>) {
  menu.value = null;
  void fn();
}
const gitInit = () => gitAction(() => actions.git(api.gitInit, t("Repository created")));
const gitPull = () => gitAction(() => actions.git(api.gitPull, t("Changes pulled")));
const gitPush = () => gitAction(() => actions.git(api.gitPush, t("Changes pushed")));
const gitFetch = () => void actions.fetchGit(true);

watch(() => [store.state?.session_id, store.state?.dirty, store.meta?.readonly], () => void actions.refreshGit(),
      { immediate: true });
const onFocus = () => void actions.refreshGit();

const initials = computed(() => {
  const n = store.meta?.user.name.trim() ?? "";
  if (!n) return "?";
  return n.split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "").join("");
});

async function toggle(m: Menu) {
  menu.value = menu.value === m ? null : m;
  if (menu.value === "git") {
    await actions.refreshGit();
    void actions.fetchGit();          // in the background: the "not pulled" counter gets stale without fetch
  }
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
      <button @click.stop="toggle('file')">{{ t("File ▾") }}</button>
      <div v-if="menu === 'file'" class="dropdown left" @click="menu = null">
        <button :disabled="store.meta?.readonly" @click="store.dialog = 'new'">{{ t("New map…") }}</button>
        <button @click="store.dialog = 'open'">{{ t("Open…") }} <kbd>Ctrl+O</kbd></button>
        <template v-if="store.meta?.recent.length">
          <div class="dd-title">{{ t("Recent") }}</div>
          <button v-for="r in store.meta.recent.slice(0, 6)" :key="r.path" :disabled="!r.exists" :title="r.path"
                  @click="actions.openFile(r.path)">{{ r.name }} <span class="muted dd-dir">{{ r.dir }}</span></button>
        </template>
        <div class="dd-sep" />
        <button :disabled="!hasMap || !store.state?.dirty || store.state?.readonly" @click="actions.save()">{{ t("Save") }} <kbd>Ctrl+S</kbd></button>
        <button :disabled="!hasMap || store.meta?.readonly" @click="store.dialog = 'saveas'">{{ t("Save as…") }} <kbd>Ctrl+Shift+S</kbd></button>
        <button :disabled="!hasMap" @click="actions.closeFile()">{{ t("Close map") }}</button>
      </div>
    </div>

    <div v-if="hasMap" class="file" :title="store.state?.path">
      <span class="mono">{{ store.state?.file }}</span>
      <span v-if="store.state?.dirty" class="dirty" :title="t('You have unsaved changes')">●</span>
      <span v-if="store.state?.readonly" class="badge">{{ t("view only") }}</span>
      <button class="icon" :class="{ attention: store.fileChangedBanner }" :disabled="store.busy"
              :title="t('Refresh: reload the file from disk')" @click="actions.reload()">⟳</button>
    </div>
    <span v-if="!store.online" class="badge warning" :title="t('Can\'t reach the mapcan server')">{{ t("offline") }}</span>

    <nav v-if="hasMap" class="tabs">
      <button :class="{ active: store.tab === 'editor' }" :disabled="!store.state?.data" @click="actions.setTab('editor')">{{ t("Editor") }}</button>
      <button :class="{ active: store.tab === 'yaml' }" @click="actions.setTab('yaml')">YAML</button>
    </nav>

    <span class="spacer" />

    <template v-if="hasMap">
      <button class="icon" :title="t('Undo (Ctrl+Z)')" :disabled="!store.state?.can_undo || store.busy" @click="actions.undo">↶</button>
      <button class="icon" :title="t('Redo (Ctrl+Y)')" :disabled="!store.state?.can_redo || store.busy" @click="actions.redo">↷</button>
      <!-- Git: comparing versions of the map and working with the repository -->
      <div class="menu">
        <button :title="git?.available ? t(FILE_STATE[git.file ?? 'clean'])
                  : git?.reason === 'no-repo' ? t('The map folder is not in a git repository') : ''"
                @click.stop="toggle('git')">
          Git<span v-if="gitPending" class="git-dot">●</span><span v-if="git?.ahead" class="git-count">↑{{ git.ahead }}</span><span
            v-if="git?.behind" class="git-count">↓{{ git.behind }}</span> ▾
        </button>
        <div v-if="menu === 'git'" class="dropdown git-menu">
          <button @click="menu = null; emit('diff')">{{ t("Compare versions…") }}</button>
          <div class="dd-sep" />
          <template v-if="git?.available">
            <div class="git-head">
              <div><span class="muted">{{ t("Branch") }}</span> <b class="mono">{{ git.branch ?? t("(detached HEAD)") }}</b>
                <span v-if="git.upstream" class="muted mono">→ {{ git.upstream }}</span></div>
              <div :class="{ 'git-warn': gitPending }">{{ t(FILE_STATE[git.file ?? "clean"]) }}</div>
              <div v-if="git.ahead || git.behind" class="muted">
                {{ t("{ahead} to push, {behind} to pull", { ahead: git.ahead ?? 0, behind: git.behind ?? 0 }) }}
              </div>
              <div v-if="git.last" class="muted dd-dir git-last" :title="git.last.subject">
                <span class="mono">{{ git.last.rev }}</span> {{ git.last.subject }}
              </div>
              <a v-if="git.remote_url" class="mono dd-dir git-last" :href="git.remote_url" target="_blank" rel="noopener"
                 :title="t('Open the repository in a browser')">{{ remoteLabel }} ↗</a>
              <div v-if="store.gitFetching" class="muted">{{ t("Checking the server…") }}</div>
              <div v-else-if="store.gitFetchError" class="git-warn git-last" :title="store.gitFetchError">
                {{ t("Could not reach the server") }}
              </div>
            </div>
            <div v-if="unsaved" class="dd-note">{{ t("Save the map to commit the changes.") }}</div>
            <div class="dd-sep" />
            <button :disabled="unsaved || !gitPending || store.busy" @click="menu = null; store.dialog = 'git-commit'">{{ t("Commit…") }}</button>
            <button :disabled="unsaved || !git.last || store.busy" @click="menu = null; store.dialog = 'git-tag'">{{ t("Create tag…") }}</button>
            <button :disabled="store.busy || store.meta?.readonly || !store.state?.resolved"
                    :title="t('A revision history entry, a new document version, a commit and a version tag')"
                    @click="menu = null; store.dialog = 'git-release'">{{ t("Release version…") }}</button>
            <button :disabled="!git.last" @click="menu = null; store.dialog = 'git-log'">{{ t("Version log…") }}</button>
            <div class="dd-sep" />
            <template v-if="git.remote">
              <button :disabled="unsaved || !git.upstream || store.busy"
                      :title="git.upstream ? '' : t('Branch not pushed to {remote} yet', { remote: git.remote })"
                      @click="gitPull">{{ t("Pull changes") }}<span v-if="git.behind" class="muted">↓{{ git.behind }}</span></button>
              <button :disabled="unsaved || !git.last || store.busy" @click="gitPush">
                {{ t("Push to {remote}", { remote: git.remote }) }}<span v-if="git.ahead" class="muted">↑{{ git.ahead }}</span>
              </button>
              <button v-if="git.upstream" :disabled="store.gitFetching" @click="gitFetch">{{ t("Check the server (fetch)") }}</button>
            </template>
            <button v-else :disabled="unsaved || !git.last || store.busy"
                    :title="git.last ? '' : t('Commit the map first')"
                    @click="menu = null; store.dialog = 'gh-publish'">{{ t("Publish on GitHub…") }}</button>
          </template>
          <template v-else-if="git?.reason === 'no-repo'">
            <div class="dd-note">{{ t("The map folder is not in a git repository. Create one to track map versions.") }}</div>
            <button :disabled="store.busy" @click="gitInit">{{ t("Create a repository here") }}</button>
          </template>
          <div v-else-if="git?.reason === 'error'" class="dd-note">{{ git.error }}</div>
          <div v-else-if="git" class="dd-note">{{ t("Git not found. Install git to commit and push map versions.") }}</div>
        </div>
      </div>

      <div class="menu">
        <button @click.stop="toggle('export')">{{ t("Export ▾") }}</button>
        <div v-if="menu === 'export'" class="dropdown export-menu" @click="menu = null">
          <template v-for="[title, items] in ([[t('Documents'), DOCUMENTS], [t('For developers'), DEV]] as const)" :key="title">
            <div class="dd-title">{{ title }}</div>
            <label v-if="items === DOCUMENTS" class="dd-row dd-lang" @click.stop>
              {{ t("Language") }}
              <select :value="store.docLang || lang" @change="store.docLang = ($event.target as HTMLSelectElement).value">
                <option v-for="[code, label] in docLanguages(lang)" :key="code" :value="code">{{ t(label) }}</option>
              </select>
            </label>
            <div v-for="it in items" :key="it.fmt" class="dd-row">
              <button v-if="it.preview" :title="t('Preview')" @click="emit('preview', it.preview)">
                {{ t(it.label) }} <span class="muted dd-dir">{{ it.fmt === "pdf" ? pdfTitle : "" }}</span>
              </button>
              <a v-else :href="downloadUrl(it)">{{ t(it.label) }} <span class="muted dd-dir">{{ it.hint }}</span></a>
              <a class="dd-dl" :href="downloadUrl(it)" :title="t('Download')">↓</a>
            </div>
          </template>
        </div>
      </div>

      <button class="primary"
              :title="store.state?.dirty_files?.length
                ? t('Save (Ctrl+S): also {files}', { files: store.state.dirty_files.join(', ') }) : t('Save (Ctrl+S)')"
              :disabled="!store.state?.dirty || store.state?.readonly || store.busy"
              @click="actions.save()">{{ t("Save") }}</button>
    </template>

    <button class="user-chip" :class="{ empty: !store.meta?.user.name }"
            :title="store.meta?.user.name ? t('Profile: {name}', { name: store.meta.user.name + (store.meta.user.github ? ' (@' + store.meta.user.github + ')' : '') }) : t('Fill in your author profile')"
            @click="store.dialog = 'profile'">
      <span class="avatar">{{ initials }}</span>
      <span class="uname">{{ store.meta?.user.name || t("Profile") }}</span>
    </button>
    <button class="icon" :title="t('Theme: {name}', { name: t(THEME_NAMES[theme]) })" @click="cycleTheme">{{ theme === "dark" ? "☾" : theme === "light" ? "☀" : "◐" }}</button>
  </header>
</template>
