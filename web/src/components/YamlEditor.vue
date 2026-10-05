<script setup lang="ts">
// Правка YAML целиком. Применение — Ctrl+Enter или кнопка; проверка та же, что в CLI.
import { computed, nextTick, ref, watch } from "vue";
import { actions, store } from "../store";
import { highlight, nodeLines } from "../yamltext";
import { t } from "../i18n";

const text = ref(store.state?.text ?? "");
const ta = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const code = ref<HTMLPreElement | null>(null);
const scrollTop = ref(0);
const LINE = 20;

const local = computed(() => text.value !== (store.state?.text ?? ""));

// Новое состояние с сервера (правка формой, undo) — подхватываем, если нет своих правок.
watch(() => store.state?.text, (t) => {
  if (!local.value || t === text.value) text.value = t ?? "";
});

const lines = computed(() => text.value.split("\n").length);
const html = computed(() => highlight(text.value).join("\n") + "\n");

// Строки узла, выбранного в дереве.
const range = computed(() => (store.state?.data ? nodeLines(text.value, store.selected) : null));
const inRange = (n: number) => !!range.value && n >= range.value.first && n <= range.value.last;

// При выборе в дереве — прокрутить к узлу, если он вне видимой области.
watch(() => store.selected, async () => {
  await nextTick();
  const r = range.value;
  const el = ta.value;
  if (!r || !el) return;
  const top = (r.first - 1) * LINE;
  const bottom = r.last * LINE;
  if (top < el.scrollTop || bottom > el.scrollTop + el.clientHeight) {
    el.scrollTop = Math.max(0, bottom - top > el.clientHeight ? top : top - (el.clientHeight - (bottom - top)) / 3);
    syncScroll();
  }
}, { immediate: true });

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
  if (!ta.value) return;
  scrollTop.value = ta.value.scrollTop;
  if (gutter.value) gutter.value.scrollTop = ta.value.scrollTop;
  if (code.value) {
    code.value.scrollTop = ta.value.scrollTop;
    code.value.scrollLeft = ta.value.scrollLeft;
  }
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
      <span class="muted">{{ t("Правка YAML целиком. Комментарии сохраняются как есть.") }}</span>
      <span class="spacer" />
      <span v-if="local" class="badge warning">{{ t("не применено") }}</span>
      <button :disabled="!local || store.state?.readonly" @click="revert">{{ t("Сбросить изменения") }}</button>
      <button class="primary" :disabled="!local || store.state?.readonly" title="Ctrl+Enter" @click="apply">{{ t("Применить") }}</button>
    </div>
    <div class="yaml-body">
      <div ref="gutter" class="gutter mono">
        <div v-for="n in lines" :key="n" :class="[marks.get(n), { 'in-node': inRange(n) }]"
             :style="{ height: LINE + 'px' }">{{ n }}</div>
      </div>
      <div class="yaml-code">
        <!-- Подсветка — слои под прозрачным текстом textarea; прокрутка синхронизируется. -->
        <div v-if="range" class="yaml-node" :style="{ top: 6 + (range.first - 1) * LINE - scrollTop + 'px',
             height: (range.last - range.first + 1) * LINE + 'px' }" />
        <pre ref="code" class="yaml-hl mono" aria-hidden="true" :style="{ lineHeight: LINE + 'px' }"><code v-html="html" /></pre>
        <textarea ref="ta" v-model="text" class="mono" spellcheck="false" :readonly="store.state?.readonly"
                  :style="{ lineHeight: LINE + 'px' }" @scroll="syncScroll" @keydown="onKey" />
      </div>
    </div>
  </div>
</template>
