<script setup lang="ts">
// Открыть / создать / сохранить как: обзор папок, недавние файлы, ввод пути вручную.
import { computed, nextTick, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store, toast } from "../store";
import type { FsEntry, FsList } from "../types";
import Modal from "./Modal.vue";

const props = defineProps<{ mode: "open" | "new" | "saveas" }>();
const emit = defineEmits<{ close: [] }>();

const TITLES = { open: "Открыть карту", new: "Новая карта", saveas: "Сохранить как" };
const ACTION = { open: "Открыть", new: "Создать", saveas: "Сохранить" };

const listing = ref<FsList | null>(null);
const dirInput = ref("");
const name = ref("");
const title = ref("");
const template = ref("canopen");
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
    listing.value = await api.list(dir);
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
  if (props.mode === "new") name.value = "canmap.yaml";
  await nextTick();
  nameEl.value?.focus();
  nameEl.value?.select();
});

const fullPath = computed(() => {
  const n = name.value.trim();
  if (!n) return "";
  if (/^([a-zA-Z]:[\\/]|[\\/]|~)/.test(n)) return n;   // введён полный путь
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
    toast("Укажите имя файла");
    return;
  }
  let ok = false;
  if (props.mode === "open") ok = await actions.openFile(p);
  else if (props.mode === "new") ok = await actions.newFile(p, template.value, title.value.trim());
  else ok = await actions.saveAs(p);
  if (ok) emit("close");
}

async function openRecent(path: string) {
  if (await actions.openFile(path)) emit("close");
}

const fmtSize = (n: number | null) => (n == null ? "" : n < 1024 ? `${n} Б` : `${(n / 1024).toFixed(1)} КБ`);
const fmtDate = (t: number) => new Date(t * 1000).toLocaleString("ru-RU", { dateStyle: "short", timeStyle: "short" });
</script>

<template>
  <Modal :title="TITLES[mode]" wide @close="emit('close')">
    <div class="fd">
      <aside v-if="mode === 'open' && store.meta?.recent.length" class="fd-recent">
        <h4>Недавние</h4>
        <button v-for="r in store.meta.recent" :key="r.path" class="fd-recent-item" :disabled="!r.exists"
                :title="r.path" @click="openRecent(r.path)">
          <b>{{ r.name }}</b><span class="muted">{{ r.exists ? r.dir : "файл не найден" }}</span>
        </button>
      </aside>

      <section class="fd-main">
        <div class="fd-nav">
          <button class="icon" title="Вверх" :disabled="!listing?.parent" @click="go(listing!.parent!)">↑</button>
          <select v-if="listing?.drives.length" class="fd-drive" @change="go(($event.target as HTMLSelectElement).value)">
            <option v-for="d in listing.drives" :key="d" :value="d" :selected="listing.dir.toUpperCase().startsWith(d)">{{ d }}</option>
          </select>
          <input v-model="dirInput" class="mono fd-path" @keydown.enter="go(dirInput)" />
          <button class="small" title="Рабочая папка canmap serve" @click="go(store.meta?.cwd ?? '')">Рабочая папка</button>
          <button class="small" @click="go(store.meta?.home ?? '')">Домашняя папка</button>
        </div>

        <p v-if="error" class="banner error">{{ error }}</p>
        <div class="fd-list">
          <p v-if="loading" class="muted">Загрузка…</p>
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
            <p v-if="!listing.entries.length" class="muted">В папке нет YAML-файлов и подпапок.</p>
          </template>
        </div>

        <div class="form-grid fd-form">
          <label class="field" :class="{ wide: mode !== 'new' }">
            <span class="field-label">{{ mode === "open" ? "Файл" : "Имя файла" }}</span>
            <input ref="nameEl" v-model="name" class="mono" placeholder="canmap.yaml или полный путь" @keydown.enter="submit" />
          </label>
          <template v-if="mode === 'new'">
            <label class="field">
              <span class="field-label">Название карты</span>
              <input v-model="title" placeholder="по имени файла" @keydown.enter="submit" />
            </label>
            <label class="field wide">
              <span class="field-label">Шаблон</span>
              <select v-model="template">
                <option v-for="(label, key) in store.meta?.templates" :key="key" :value="key">{{ label }}</option>
              </select>
            </label>
            <p v-if="!store.meta?.user.name" class="field wide muted">
              Автор новой карты не будет указан —
              <a href="#" @click.prevent="store.dialog = 'profile'">заполните профиль</a>.
            </p>
          </template>
        </div>
        <div class="fd-actions">
          <span class="muted mono fd-target">{{ fullPath }}</span>
          <button @click="emit('close')">Отмена</button>
          <button class="primary" :disabled="!name.trim() || store.busy" @click="submit">{{ ACTION[mode] }}</button>
        </div>
      </section>
    </div>
  </Modal>
</template>
