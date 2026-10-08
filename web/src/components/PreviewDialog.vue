<script setup lang="ts">
// Preview of the documents from the current (also unsaved) state of the map.
// For PDF, the choice of the template (mapcan, ESKD); the document language for all
// but the ESKD template (it is Russian only).
import { computed, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { actions, exportLang, lang, store } from "../store";
import Modal from "./Modal.vue";
import { docLanguages, N_, t } from "../i18n";

const props = defineProps<{ fmt: "html" | "pdf" | "md" }>();
const emit = defineEmits<{ close: [] }>();

const TITLES = { html: N_("HTML preview"), pdf: N_("PDF preview"), md: "Markdown" };
const md = ref("");
const error = ref("");
const loading = ref(props.fmt === "md");
const frameLoading = ref(props.fmt !== "md");

const template = computed(() => (props.fmt === "pdf" ? store.pdfTemplate : undefined));
const current = computed(() => store.pdfTemplates.find((t) => t.name === store.pdfTemplate));
const docLang = computed(() => exportLang(props.fmt));
const langFixed = computed(() => props.fmt === "pdf" && !!current.value?.lang);
// A version mark in the URL, so the browser does not show an old document from its cache.
const src = computed(() => {
  const url = api.exportUrl(props.fmt, false, template.value, docLang.value);
  return `${url}${url.includes("?") ? "&" : "?"}v=${store.state?.version ?? 0}`;
});

function pick(e: Event) {
  const prev = src.value;
  actions.setPdfTemplate((e.target as HTMLSelectElement).value);
  if (src.value !== prev) frameLoading.value = true;
}

function pickLang(e: Event) {
  const prev = src.value;
  store.docLang = (e.target as HTMLSelectElement).value;
  if (props.fmt !== "md" && src.value !== prev) frameLoading.value = true;
}

async function loadMd() {
  if (props.fmt !== "md") return;
  loading.value = true;
  error.value = "";
  try {
    md.value = await api.exportText("md", docLang.value);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(loadMd);
watch(docLang, loadMd);

async function copy() {
  await navigator.clipboard.writeText(md.value);
}
</script>

<template>
  <Modal :title="t(TITLES[fmt])" wide @close="emit('close')">
    <template #actions>
      <label v-if="fmt === 'pdf'" class="tpl-pick">
        {{ t("Template") }}
        <select :value="store.pdfTemplate" @change="pick">
          <option v-for="t in store.pdfTemplates" :key="t.name" :value="t.name">{{ t.title }}</option>
        </select>
      </label>
      <label class="tpl-pick" :title="langFixed ? t('GOST documents are always in Russian') : ''">
        {{ t("Language") }}
        <select :value="docLang" :disabled="langFixed" @change="pickLang">
          <option v-for="[code, label] in docLanguages(lang)" :key="code" :value="code">{{ t(label) }}</option>
        </select>
      </label>
      <button v-if="fmt === 'md' && md" class="small" @click="copy">{{ t("Copy") }}</button>
      <a class="button small primary-link" :href="api.exportUrl(fmt, true, template, docLang)">{{ t("Download") }}</a>
    </template>
    <p v-if="fmt === 'pdf' && current" class="muted tpl-desc">{{ current.description }}</p>
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="loading" class="muted">{{ t("Generating…") }}</p>
    <pre v-else-if="fmt === 'md'" class="md-preview mono">{{ md }}</pre>
    <div v-else class="preview-wrap">
      <div v-if="frameLoading" class="preview-loading muted">{{ t("Generating document…") }}</div>
      <iframe :key="src" class="preview-frame" :src="src" :title="t(TITLES[fmt])" @load="frameLoading = false" />
    </div>
  </Modal>
</template>
