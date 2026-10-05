<script setup lang="ts">
// Правка YAML целиком. Применение — Ctrl+Enter или кнопка; проверка та же, что в CLI.
import { computed, nextTick, ref, watch } from "vue";
import { actions, store } from "../store";

const text = ref(store.state?.text ?? "");
const ta = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const LINE = 20;

const local = computed(() => text.value !== (store.state?.text ?? ""));

// Новое состояние с сервера (правка формой, undo) — подхватываем, если нет своих правок.
watch(() => store.state?.text, (t) => {
  if (!local.value || t === text.value) text.value = t ?? "";
});

const lines = computed(() => text.value.split("\n").length);

const marks = computed(() => {
  const m = new Map<number, string>();
  for (const d of store.state?.diagnostics ?? []) {
    if (d.line == null) continue;
    const cur = m.get(d.line);
    if (cur !== "error") m.set(d.line, d.level === "error" ? "error" : cur ?? d.level);
  }
  return m;
});

function syncScroll() {
  if (gutter.value && ta.value) gutter.value.scrollTop = ta.value.scrollTop;
}

async function reveal(line: number | null) {
  if (line == null || !ta.value) return;
  await nextTick();
  const el = ta.value;
  const offs = text.value.split("\n").slice(0, line - 1).reduce((a, l) => a + l.length + 1, 0);
  const end = offs + (text.value.split("\n")[line - 1]?.length ?? 0);
  el.focus();
  el.setSelectionRange(offs, end);
  el.scrollTop = Math.max(0, (line - 5) * LINE);
  syncScroll();
}

watch(() => store.revealLine, (l) => {
  void reveal(l);
  store.revealLine = null;
}, { immediate: true });

async function apply() {
  if (!local.value) return;
  await actions.setText(text.value);
}

function revert() {
  text.value = store.state?.text ?? "";
}

function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    void apply();
  } else if (e.key === "Tab") {
    e.preventDefault();
    const el = e.target as HTMLTextAreaElement;
    const s = el.selectionStart;
    text.value = text.value.slice(0, s) + "  " + text.value.slice(el.selectionEnd);
    void nextTick(() => el.setSelectionRange(s + 2, s + 2));
  }
}
</script>

<template>
  <div class="yaml-editor">
    <div class="yaml-bar">
      <span class="muted">Правка YAML целиком. Комментарии сохраняются как есть.</span>
      <span class="spacer" />
      <span v-if="local" class="badge warning">не применено</span>
      <button :disabled="!local || store.state?.readonly" @click="revert">Отменить правку</button>
      <button class="primary" :disabled="!local || store.state?.readonly" title="Ctrl+Enter" @click="apply">Применить</button>
    </div>
    <div class="yaml-body">
      <div ref="gutter" class="gutter mono">
        <div v-for="n in lines" :key="n" :class="marks.get(n)" :style="{ height: LINE + 'px' }">{{ n }}</div>
      </div>
      <textarea ref="ta" v-model="text" class="mono" spellcheck="false" :readonly="store.state?.readonly"
                :style="{ lineHeight: LINE + 'px' }" @scroll="syncScroll" @keydown="onKey" />
    </div>
  </div>
</template>
