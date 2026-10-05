<script setup lang="ts">
// Сравнение текущей карты с версией из git или загруженным файлом; запись в историю изменений.
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store, toast } from "../store";
import type { DiffResult, GitRevs } from "../types";
import Modal from "./Modal.vue";

const emit = defineEmits<{ close: [] }>();

const revs = ref<GitRevs | null>(null);
const rev = ref("HEAD");
const result = ref<DiffResult | null>(null);
const loading = ref(false);
const error = ref("");

// Форма записи в историю
const version = ref("");
const date = ref(new Date().toISOString().slice(0, 10));
const changes = ref("");

onMounted(async () => {
  try {
    revs.value = await api.gitRevs();
    if (revs.value.available) await compareGit();
  } catch {
    revs.value = { available: false, tags: [], commits: [] };
  }
});

function bump(v: string): string {
  const m = /^(\d+)\.(\d+)\.(\d+)(.*)$/.exec(v ?? "");
  return m ? `${m[1]}.${m[2]}.${Number(m[3]) + 1}` : v || "0.1.0";
}

function accept(r: DiffResult) {
  result.value = r;
  error.value = "";
  const cur = store.state?.data?.document?.version ?? "";
  version.value = r.old_version === cur ? bump(cur) : cur;
  changes.value = r.lines.join("\n");
}

async function compareGit() {
  loading.value = true;
  try {
    accept(await api.diffGit(rev.value));
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

async function compareFile(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  loading.value = true;
  try {
    accept(await api.diffUpload(f));
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

const groups = computed(() => {
  const g = new Map<string, string[]>();
  for (const line of result.value?.lines ?? []) {
    const m = /^(0x[0-9A-F]+ \S+): (.*)$/.exec(line);
    const key = m ? m[1] : "Общее";
    if (!g.has(key)) g.set(key, []);
    g.get(key)!.push(m ? m[2] : line);
  }
  return [...g.entries()];
});

async function addToHistory() {
  const lines = changes.value.split("\n").map((s) => s.trim()).filter(Boolean);
  if (!version.value.trim() || !lines.length) {
    toast("Укажите версию и хотя бы одно изменение");
    return;
  }
  const user = store.meta?.user;
  const entry: Record<string, unknown> = { version: version.value.trim(), date: date.value };
  if (user?.name) entry.author = user.name;
  if (user?.github) entry.github = user.github;
  entry.changes = lines;
  const ok = await actions.apply([
    { op: "insert", path: ["document", "history"], index: 0, value: entry },
    { op: "set", path: ["document", "version"], value: version.value.trim() },
    { op: "set", path: ["document", "date"], value: date.value },
  ]);
  if (ok) {
    toast("Запись добавлена в историю изменений", "info");
    actions.select(["document"]);
    emit("close");
  }
}
</script>

<template>
  <Modal title="Сравнить версии" wide @close="emit('close')">
    <div class="diff-source">
      <template v-if="revs?.available">
        <label>С версией из git:
          <select v-model="rev">
            <option value="HEAD">HEAD — последний коммит</option>
            <optgroup v-if="revs.tags.length" label="Теги">
              <option v-for="t in revs.tags" :key="t" :value="t">{{ t }}</option>
            </optgroup>
            <optgroup v-if="revs.commits.length" label="Коммиты с этим файлом">
              <option v-for="c in revs.commits" :key="c.rev" :value="c.rev">{{ c.rev }} · {{ c.date }} · {{ c.subject }}</option>
            </optgroup>
          </select>
        </label>
        <button :disabled="loading" @click="compareGit">Сравнить</button>
        <span class="muted">или</span>
      </template>
      <label class="button">Выбрать файл… <input type="file" accept=".yaml,.yml" hidden @change="compareFile" /></label>
    </div>

    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Сравнение…</p>

    <template v-if="result && !loading">
      <p class="muted">
        {{ result.label }} (версия {{ result.old_version }}) → текущая карта (версия {{ result.new_version }}):
        изменений — {{ result.lines.length }}
      </p>
      <div v-if="result.lines.length" class="diff-list">
        <section v-for="[k, items] in groups" :key="k">
          <h4 class="mono">{{ k }}</h4>
          <ul><li v-for="(x, i) in items" :key="i">{{ x }}</li></ul>
        </section>
      </div>
      <p v-else class="ok">Отличий нет.</p>

      <section v-if="result.lines.length && !store.state?.readonly" class="history-form">
        <h4>Добавить в историю изменений</h4>
        <div class="form-grid">
          <label class="field"><span class="field-label">Новая версия</span><input v-model="version" class="mono" /></label>
          <label class="field"><span class="field-label">Дата</span><input v-model="date" type="date" /></label>
          <label class="field wide"><span class="field-label">Изменения (по строке)</span>
            <textarea v-model="changes" rows="6" /></label>
        </div>
        <p class="muted">
          Автор:
          <template v-if="store.meta?.user.name">
            <b>{{ store.meta.user.name }}</b>
            <span v-if="store.meta.user.github" class="mono">@{{ store.meta.user.github }}</span>
          </template>
          <template v-else>не указан —</template>
          <button class="link" @click="store.dialog = 'profile'">{{ store.meta?.user.name ? "изменить" : "заполнить профиль" }}</button>
        </p>
        <button class="primary" @click="addToHistory">Добавить в историю</button>
      </section>
    </template>
  </Modal>
</template>
