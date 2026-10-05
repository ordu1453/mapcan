<script setup lang="ts">
// Предпросмотр документов из текущего (в т.ч. несохранённого) состояния карты.
// Для PDF — выбор шаблона оформления (canmap, ЕСКД, ЕСПД, ГОСТ 7.32).
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import Modal from "./Modal.vue";

const props = defineProps<{ fmt: "html" | "pdf" | "md" }>();
const emit = defineEmits<{ close: [] }>();

const TITLES = { html: "Предпросмотр HTML", pdf: "Предпросмотр PDF", md: "Markdown" };
const md = ref("");
const error = ref("");
const loading = ref(props.fmt === "md");
const frameLoading = ref(props.fmt !== "md");

const template = computed(() => (props.fmt === "pdf" ? store.pdfTemplate : undefined));
const current = computed(() => store.pdfTemplates.find((t) => t.name === store.pdfTemplate));
// Метка версии в URL, чтобы браузер не показывал старый документ из кэша.
const src = computed(() => {
  const url = api.exportUrl(props.fmt, false, template.value);
  return `${url}${url.includes("?") ? "&" : "?"}v=${store.state?.version ?? 0}`;
});

function pick(e: Event) {
  actions.setPdfTemplate((e.target as HTMLSelectElement).value);
  frameLoading.value = true;
}

onMounted(async () => {
  if (props.fmt !== "md") return;
  try {
    md.value = await api.exportText("md");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
});

async function copy() {
  await navigator.clipboard.writeText(md.value);
}
</script>

<template>
  <Modal :title="TITLES[fmt]" wide @close="emit('close')">
    <template #actions>
      <label v-if="fmt === 'pdf'" class="tpl-pick">
        Шаблон
        <select :value="store.pdfTemplate" @change="pick">
          <option v-for="t in store.pdfTemplates" :key="t.name" :value="t.name">{{ t.title }}</option>
        </select>
      </label>
      <button v-if="fmt === 'md' && md" class="small" @click="copy">Копировать</button>
      <a class="button small primary-link" :href="api.exportUrl(fmt, true, template)">Скачать</a>
    </template>
    <p v-if="fmt === 'pdf' && current" class="muted tpl-desc">{{ current.description }}</p>
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Формирование…</p>
    <pre v-else-if="fmt === 'md'" class="md-preview mono">{{ md }}</pre>
    <div v-else class="preview-wrap">
      <div v-if="frameLoading" class="preview-loading muted">Формирование документа…</div>
      <iframe :key="src" class="preview-frame" :src="src" :title="TITLES[fmt]" @load="frameLoading = false" />
    </div>
  </Modal>
</template>
