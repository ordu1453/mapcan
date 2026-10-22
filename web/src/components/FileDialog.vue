<script setup lang="ts">
// Open / create / save as: browsing folders, recent files, typing a path by hand.
import { computed, nextTick, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store, toast } from "../store";
import type { FsEntry, FsList } from "../types";
import Modal from "./Modal.vue";
import { DOC_LANGUAGES, N_, t } from "../i18n";
import { hasNativeDialog, nativePick } from "../native";

const props = defineProps<{ mode: "open" | "new" | "saveas" | "example" | "import" }>();
const emit = defineEmits<{ close: [] }>();

const TITLES = { open: N_("Open map"), new: N_("New map"), saveas: N_("Save as"),
                 example: N_("Save a copy of the example"), import: N_("Import DBC") };
const ACTION = { open: N_("Open"), new: N_("Create"), saveas: N_("Save"), example: N_("Create"), import: N_("Import") };
// The import lists DBC files; the map is written next to the chosen one
const kind = props.mode === "import" ? "dbc" : "yaml";

const listing = ref<FsList | null>(null);
const dirInput = ref("");
const name = ref("");
const title = ref("");
const template = ref("canopen");
const docLang = ref("en");
const error = ref("");
const loading = ref(false);
const nameEl = ref<HTMLInputElement | null>(null);

const sep = computed(() => listing.value?.sep ?? "/");

function dirOf(p: string | null | undefined): string {
  if (!p) return "";
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i > 0 ? p.slice(0, i) : p;
}

async function go(dir: string) {
  loading.value = true;
  try {
    listing.value = await api.list(dir, kind);
    dirInput.value = listing.value.dir;
    error.value = "";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  const start = store.meta?.file ? dirOf(store.meta.file) : store.meta?.cwd ?? "";
  await go(start);
  if (props.mode === "saveas" && store.meta?.file) {
    const f = store.meta.file;
    name.value = f.slice(Math.max(f.lastIndexOf("/"), f.lastIndexOf("\\")) + 1).replace(/(\.ya?ml)$/i, "_copy$1");
  }
  if (props.mode === "new") name.value = "mapcan.yaml";
  if (props.mode === "example") name.value = `${store.example}.yaml`;
  await nextTick();
  nameEl.value?.focus();
  nameEl.value?.select();
});

const fullPath = computed(() => {
  const n = name.value.trim();
  if (!n) return "";
  if (/^([a-zA-Z]:[\\/]|[\\/]|~)/.test(n)) return n;   // a full path was typed
  const d = listing.value?.dir ?? "";
  return d.endsWith(sep.value) ? d + n : d + sep.value + n;
});

function pick(e: FsEntry) {
  if (e.is_dir) void go(e.path);
  else name.value = e.name;
}

async function activate(e: FsEntry) {
  if (e.is_dir) return go(e.path);
  name.value = e.name;
  await submit();
}

async function submit() {
  const p = fullPath.value;
  if (!p) {
    toast(t("Enter a file name"));
    return;
  }
  let ok = false;
  if (props.mode === "open") ok = await actions.openFile(p);
  else if (props.mode === "new") ok = await actions.newFile(p, template.value, title.value.trim(), docLang.value);
  else if (props.mode === "example") ok = await actions.newFromExample(store.example ?? "", p);
  else if (props.mode === "import") ok = await actions.importDbc(p, docLang.value);
  else ok = await actions.saveAs(p);
  if (ok) emit("close");
}

const canBrowse = hasNativeDialog();

// The OS file dialog. A choice in it is already a confirmation (the dialog itself asks about overwriting),
// except for a new map: it also needs a template and a title.
async function browse() {
  const base = name.value.trim().split(/[\\/]/).pop() ?? "";
  const open = props.mode === "open" || props.mode === "import";
  const p = await nativePick(open ? "open" : "save", listing.value?.dir ?? "", base, kind);
  if (!p) return;
  let ok = false;
  if (props.mode === "open") ok = await actions.openFile(p);
  else if (props.mode === "import") ok = await actions.importDbc(p, docLang.value);
  else if (props.mode === "saveas") ok = await actions.saveAs(p, true);
  else if (props.mode === "example") ok = await actions.newFromExample(store.example ?? "", p, true);
  else {
    await go(dirOf(p));
    name.value = p.slice(Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\")) + 1);
    nameEl.value?.focus();
  }
  if (ok) emit("close");
}

async function openRecent(path: string) {
  if (await actions.openFile(path)) emit("close");
}

const importTarget = computed(() => fullPath.value.replace(/(\.dbc)?$/i, ".yaml"));

const fmtSize = (n: number | null) => (n == null ? "" : n < 1024 ? t("{n} B", { n }) : t("{n} KB", { n: (n / 1024).toFixed(1) }));
const fmtDate = (s: number) => new Date(s * 1000).toLocaleString("en-US", { dateStyle: "short", timeStyle: "short" });
</script>

<template>
  <Modal :title="t(TITLES[mode])" wide @close="emit('close')">
    <div class="fd">
      <aside v-if="mode === 'open' && store.meta?.recent.length" class="fd-recent">
        <h4>{{ t("Recent") }}</h4>
        <button v-for="r in store.meta.recent" :key="r.path" class="fd-recent-item" :disabled="!r.exists"
                :title="r.path" @click="openRecent(r.path)">
          <b>{{ r.name }}</b><span class="muted">{{ r.exists ? r.dir : t("file not found") }}</span>
        </button>
      </aside>

      <section class="fd-main">
        <div class="fd-nav">
          <button class="icon" :title="t('Up')" :disabled="!listing?.parent" @click="go(listing!.parent!)">↑</button>
          <select v-if="listing?.drives.length" class="fd-drive" @change="go(($event.target as HTMLSelectElement).value)">
            <option v-for="d in listing.drives" :key="d" :value="d" :selected="listing.dir.toUpperCase().startsWith(d)">{{ d }}</option>
          </select>
          <input v-model="dirInput" class="mono fd-path" @keydown.enter="go(dirInput)" />
          <button class="small" :title="t('Folder mapcan serve was started in')" @click="go(store.meta?.cwd ?? '')">{{ t("Working folder") }}</button>
          <button class="small" @click="go(store.meta?.home ?? '')">{{ t("Home folder") }}</button>
        </div>

        <p v-if="error" class="banner error">{{ error }}</p>
        <div class="fd-list">
          <p v-if="loading" class="muted">{{ t("Loading…") }}</p>
          <template v-else-if="listing">
            <div v-for="e in listing.entries" :key="e.path" class="fd-row" :class="{ dir: e.is_dir, sel: !e.is_dir && e.name === name }"
                 @click="pick(e)" @dblclick="activate(e)">
              <svg class="fd-ico" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
                   stroke-width="1.3" stroke-linejoin="round" aria-hidden="true">
                <path v-if="e.is_dir" d="M1.5 4.5v8.5h13V5.5H8L6.5 3.5h-5z" />
                <template v-else><path d="M4 1.5h5.5L12.5 4.5v10h-8.5z" /><path d="M9.5 1.5v3h3" /></template>
              </svg>
              <span class="fd-name">{{ e.name }}</span>
              <span class="muted mono">{{ fmtSize(e.size) }}</span>
              <span class="muted">{{ fmtDate(e.mtime) }}</span>
            </div>
            <p v-if="!listing.entries.length" class="muted">{{ mode === "import"
              ? t("This folder contains no DBC files or subfolders.")
              : t("This folder contains no YAML files or subfolders.") }}</p>
          </template>
        </div>

        <div class="form-grid fd-form">
          <label class="field" :class="{ wide: mode !== 'new' && mode !== 'import' }">
            <span class="field-label">{{ mode === "open" || mode === "import" ? t("File") : t("File name") }}</span>
            <input ref="nameEl" v-model="name" class="mono"
                   :placeholder="mode === 'import' ? t('bus.dbc or a full path') : t('mapcan.yaml or a full path')"
                   @keydown.enter="submit" />
          </label>
          <template v-if="mode === 'import'">
            <label class="field">
              <span class="field-label">{{ t("Document language") }}</span>
              <select v-model="docLang">
                <option v-for="[code, label] in DOC_LANGUAGES" :key="code" :value="code">{{ t(label) }}</option>
              </select>
            </label>
            <p class="field wide muted">{{ t("The map is written next to the DBC file, with its name.") }}</p>
          </template>
          <template v-if="mode === 'new'">
            <label class="field">
              <span class="field-label">{{ t("Map title") }}</span>
              <input v-model="title" :placeholder="t('from the file name')" @keydown.enter="submit" />
            </label>
            <label class="field">
              <span class="field-label">{{ t("Template") }}</span>
              <select v-model="template">
                <option v-for="(label, key) in store.meta?.templates" :key="key" :value="key">{{ label }}</option>
              </select>
            </label>
            <label class="field">
              <span class="field-label">{{ t("Document language") }}</span>
              <select v-model="docLang">
                <option v-for="[code, label] in DOC_LANGUAGES" :key="code" :value="code">{{ t(label) }}</option>
              </select>
            </label>
            <p v-if="!store.meta?.user.name" class="field wide muted">
              {{ t("The new map will have no author. To fix this,") }}
              <a href="#" @click.prevent="store.dialog = 'profile'">{{ t("fill in your profile") }}</a>.
            </p>
          </template>
        </div>
        <div class="fd-actions">
          <span class="muted mono fd-target">{{ mode === "import" && name.trim() ? importTarget : fullPath }}</span>
          <button v-if="canBrowse" :disabled="store.busy" :title="t('Choose with the system file dialog')" @click="browse">{{ t("Browse…") }}</button>
          <button @click="emit('close')">{{ t("Cancel") }}</button>
          <button class="primary" :disabled="!name.trim() || store.busy" @click="submit">{{ t(ACTION[mode]) }}</button>
        </div>
      </section>
    </div>
  </Modal>
</template>
