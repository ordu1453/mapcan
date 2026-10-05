<script setup lang="ts">
// Предпросмотр документов из текущего (в т.ч. несохранённого) состояния карты.
import { onMounted, ref } from "vue";
import { api } from "../api";
import { store } from "../store";
import Modal from "./Modal.vue";

const props = defineProps<{ fmt: "html" | "pdf" | "md" }>();
const emit = defineEmits<{ close: [] }>();

const TITLES = { html: "Предпросмотр HTML", pdf: "Предпросмотр PDF", md: "Markdown" };
const md = ref("");
const error = ref("");
const loading = ref(props.fmt === "md");
// Метка версии в URL, чтобы браузер не показывал старый документ из кэша.
const src = `${api.exportUrl(props.fmt)}?v=${store.state?.version ?? 0}`;

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
      <button v-if="fmt === 'md' && md" class="small" @click="copy">Копировать</button>
      <a class="button small" :href="api.exportUrl(fmt, true)">Скачать</a>
    </template>
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="loading" class="muted">Формирование…</p>
    <pre v-else-if="fmt === 'md'" class="md-preview mono">{{ md }}</pre>
    <iframe v-else class="preview-frame" :src="src" :title="TITLES[fmt]" />
  </Modal>
</template>
