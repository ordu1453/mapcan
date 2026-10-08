<script setup lang="ts">
// Сравнение текущей карты с версией из git или загруженным файлом; запись в историю изменений.
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store, toast } from "../store";
import type { DiffResult, GitRevs } from "../types";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const props = defineProps<{ rev?: string }>();
const emit = defineEmits<{ close: [] }>();

const revs = ref<GitRevs | null>(null);
const rev = ref(props.rev || "HEAD");
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
    revs.value = { available: false, tags: [], all_tags: [], branches: [], commits: [] };
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

async function openRevision() {
  if (await actions.restoreRevision(rev.value)) emit("close");
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

const gitHint = computed(() => {
  switch (revs.value?.reason) {
    case "no-git": return t("Git not found, so comparing with versions from git is unavailable.");
    case "no-repo": return t("The map file is not in a git repository.");
    case "untracked": return t("The map file hasn't been committed to git yet, so there's nothing to compare with.");
    default: return "";
  }
});

const groups = computed(() => {
  const g = new Map<string, string[]>();
  for (const line of result.value?.lines ?? []) {
    const m = /^(0x[0-9A-F]+ \S+): (.*)$/.exec(line);
    const key = m ? m[1] : t("General");
    if (!g.has(key)) g.set(key, []);
    g.get(key)!.push(m ? m[2] : line);
  }
  return [...g.entries()];
});

async function addToHistory() {
  const lines = changes.value.split("\n").map((s) => s.trim()).filter(Boolean);
  if (!version.value.trim() || !lines.length) {
    toast(t("Enter a version and at least one change"));
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
    toast(t("Entry added to the revision history"), "info");
    actions.select(["document"]);
    emit("close");
  }
}
</script>

<template>
  <Modal :title="t('Compare versions')" wide @close="emit('close')">
    <div class="diff-source">
      <template v-if="revs?.available">
        <label>{{ t("Compare with git version:") }}
          <select v-model="rev">
            <option value="HEAD">{{ t("HEAD — latest commit") }}</option>
            <optgroup v-if="revs.tags.length" :label="t('Tags')">
              <option v-for="t in revs.tags" :key="t" :value="t">{{ t }}</option>
            </optgroup>
            <optgroup v-if="revs.branches.length" :label="t('Branches')">
              <option v-for="b in revs.branches" :key="b" :value="b">{{ b }}</option>
            </optgroup>
            <optgroup v-if="revs.commits.length" :label="t('Commits with this file')">
              <option v-for="c in revs.commits" :key="c.rev" :value="c.rev">{{ c.rev }} · {{ c.date }} · {{ c.author }} · {{ c.subject }}</option>
            </optgroup>
          </select>
        </label>
        <button :disabled="loading" @click="compareGit">{{ t("Compare") }}</button>
        <button v-if="!store.state?.readonly" :disabled="loading || store.busy"
                :title="t('Load this version into the editor in place of the current one (can be undone)')"
                @click="openRevision">{{ t("Open this version") }}</button>
        <span class="muted">{{ t("or") }}</span>
      </template>
      <label class="button">{{ t("Choose file…") }} <input type="file" accept=".yaml,.yml" hidden @change="compareFile" /></label>
    </div>

    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="loading" class="muted">{{ t("Comparing…") }}</p>
    <p v-else-if="!result && gitHint" class="banner info">{{ gitHint }} {{ t("Choose a YAML file with an earlier version of the map to compare against.") }}</p>

    <template v-if="result && !loading">
      <p class="muted">
        {{ t("{label} (version {old}) → current map (version {new}): {n} changes", {
          label: result.label, old: result.old_version, new: result.new_version, n: result.lines.length }) }}
      </p>
      <div v-if="result.lines.length" class="diff-list">
        <section v-for="[k, items] in groups" :key="k">
          <h4 class="mono">{{ k }}</h4>
          <ul><li v-for="(x, i) in items" :key="i">{{ x }}</li></ul>
        </section>
      </div>
      <p v-else class="ok">{{ t("No differences.") }}</p>

      <section v-if="result.lines.length && !store.state?.readonly" class="history-form">
        <h4>{{ t("Add to revision history") }}</h4>
        <div class="form-grid">
          <label class="field"><span class="field-label">{{ t("New version") }}</span><input v-model="version" class="mono" /></label>
          <label class="field"><span class="field-label">{{ t("Date") }}</span><input v-model="date" type="date" /></label>
          <label class="field wide"><span class="field-label">{{ t("Changes (one per line)") }}</span>
            <textarea v-model="changes" rows="6" /></label>
        </div>
        <p class="muted">
          {{ t("Author:") }}
          <template v-if="store.meta?.user.name">
            <b>{{ store.meta.user.name }}</b>
            <span v-if="store.meta.user.github" class="mono">@{{ store.meta.user.github }}</span>
          </template>
          <template v-else>{{ t("not set —") }}</template>
          <button class="link" @click="store.dialog = 'profile'">{{ store.meta?.user.name ? t("edit") : t("fill in profile") }}</button>
        </p>
        <button class="primary" @click="addToHistory">{{ t("Add to history") }}</button>
      </section>
    </template>
  </Modal>
</template>
