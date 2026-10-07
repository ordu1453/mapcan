<script setup lang="ts">
// Правка YAML целиком. Текст без синтаксических ошибок применяется по ходу ввода (дерево и проверка
// обновляются сразу), Ctrl+Enter или кнопка — применить немедленно; проверка та же, что в CLI.
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { api } from "../api";
import { actions, diagnostics as diags, store, tree, yamlLocal as local } from "../store";
import { samePath, type TreeNode } from "../model";
import { highlight, keyEdit, nodeAtLine, nodeLines, type TextEdit } from "../yamltext";
import { t } from "../i18n";

// Черновик живёт в store: при переходе на другую вкладку он не теряется, а применяется.
const text = computed({
  get: () => store.yaml.draft ?? store.state?.text ?? "",
  set: (v: string) => { store.yaml.draft = v; },
});
const ta = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const code = ref<HTMLPreElement | null>(null);
const scrollTop = ref(0);
const LINE = 20;

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

// Обратно: курсор в тексте выбирает в дереве узел, которому принадлежит строка.
const treePaths = computed(() => {
  const out: TreeNode["path"][] = [];
  const walk = (ns: TreeNode[]) => ns.forEach((n) => { out.push(n.path); walk(n.children); });
  walk(tree.value);
  return out;
});

function selectAtCursor() {
  const el = ta.value;
  if (!el || !store.state?.data) return;
  const line = text.value.slice(0, el.selectionStart).split("\n").length;
  const p = nodeAtLine(text.value, line, treePaths.value);
  if (p && !samePath(p, store.selected)) actions.select(p);
}

function onKeyUp(e: KeyboardEvent) {
  if (/^(Arrow|Page|Home|End)/.test(e.key)) selectAtCursor();
}

// Живая проверка: неприменённый текст проверяется на сервере с задержкой после ввода
// и, если он разбирается, применяется (одним шагом отмены на всю серию ввода). Результат проверки
// лежит в store — его показывает и панель «Проверка».
let checkTimer: ReturnType<typeof setTimeout> | undefined;
let checkSeq = 0;
watch(text, (value) => {
  clearTimeout(checkTimer);
  if (!local.value) {
    store.yaml.diags = null;
    return;
  }
  const seq = ++checkSeq;
  checkTimer = setTimeout(async () => {
    try {
      const r = await api.check(value);
      if (seq !== checkSeq) return;
      if (store.yaml.draft === value) store.yaml.diags = r.diagnostics;
      if (!store.state?.readonly && !r.diagnostics.some((d) => d.code === "yaml")) await actions.setText(value, true);
    } catch {
      /* нет связи — пометки остаются прежними */
    }
  }, 400);
});

onBeforeUnmount(() => clearTimeout(checkTimer));

const draftErrors = computed(() => (local.value ? (store.yaml.diags ?? []).filter((d) => d.level === "error") : []));

const marks = computed(() => {
  const m = new Map<number, string>();
  for (const d of diags.value) {
    if (d.line == null) continue;
    const cur = m.get(d.line);
    if (cur !== "error") m.set(d.line, d.level === "error" ? "error" : cur ?? d.level);
  }
  return m;
});

const lineMessages = computed(() => {
  const m = new Map<number, string>();
  for (const d of diags.value) {
    if (d.line == null) continue;
    m.set(d.line, (m.has(d.line) ? m.get(d.line) + "\n" : "") + `${d.level}[${d.code}]: ${d.message}`);
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
  if (store.yaml.draft === null) return;
  const el = ta.value;
  const sel = el && [el.selectionStart, el.selectionEnd, el.scrollTop];
  clearTimeout(checkTimer);
  checkSeq++;
  await actions.flushYaml();
  // Поле перешло на текст сервера — курсор и прокрутка остаются на месте.
  await nextTick();
  if (el && sel && document.activeElement === el) {
    el.setSelectionRange(sel[0], sel[1]);
    el.scrollTop = sel[2];
    syncScroll();
  }
}

// Отменить ввод, ещё не применённый на сервере.
function revert() {
  store.yaml = { draft: null, applied: null, diags: null };
}

// Правка через execCommand попадает в историю отмены textarea (Ctrl+Z); присваивание text — нет.
function replace(el: HTMLTextAreaElement, ed: TextEdit) {
  el.setSelectionRange(ed.from, ed.to);
  const ok = ed.insert ? document.execCommand("insertText", false, ed.insert)
    : ed.from === ed.to || document.execCommand("delete");
  if (!ok) {
    el.setRangeText(ed.insert, ed.from, ed.to, "end");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }
  el.setSelectionRange(ed.selStart, ed.selEnd);
}

// После Esc клавиша Tab уводит фокус из поля, как в обычной форме.
let tabLeaves = false;

function onKey(e: KeyboardEvent) {
  const el = e.target as HTMLTextAreaElement;
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    void apply();
    return;
  }
  if (e.key === "Escape") {
    tabLeaves = true;
    return;
  }
  const leave = tabLeaves;
  tabLeaves = false;
  if (el.readOnly || e.ctrlKey || e.metaKey || e.altKey || e.isComposing || (e.key === "Tab" && leave)) return;
  const ed = keyEdit(text.value, el.selectionStart, el.selectionEnd, e.key, e.shiftKey);
  if (!ed) return;
  e.preventDefault();
  replace(el, ed);
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
    <div v-if="draftErrors.length" class="yaml-problems">
      <button v-for="(d, i) in draftErrors.slice(0, 3)" :key="i" class="link" @click="reveal(d.line)">
        <b>{{ t("Строка {line}", { line: d.line ?? "?" }) }}:</b> {{ d.message }}
      </button>
      <span v-if="draftErrors.length > 3" class="muted">{{ t("и ещё {count}", { count: draftErrors.length - 3 }) }}</span>
    </div>
    <div class="yaml-body">
      <div ref="gutter" class="gutter mono">
        <div v-for="n in lines" :key="n" :class="[marks.get(n), { 'in-node': inRange(n) }]" :title="lineMessages.get(n)"
             :style="{ height: LINE + 'px' }">{{ n }}</div>
      </div>
      <div class="yaml-code">
        <!-- Подсветка — слои под прозрачным текстом textarea; прокрутка синхронизируется. -->
        <div v-if="range" class="yaml-node" :style="{ top: 6 + (range.first - 1) * LINE - scrollTop + 'px',
             height: (range.last - range.first + 1) * LINE + 'px' }" />
        <pre ref="code" class="yaml-hl mono" aria-hidden="true" :style="{ lineHeight: LINE + 'px' }"><code v-html="html" /></pre>
        <textarea ref="ta" v-model="text" class="mono" spellcheck="false" :readonly="store.state?.readonly"
                  :style="{ lineHeight: LINE + 'px' }" @scroll="syncScroll" @keydown="onKey"
                  @keyup="onKeyUp" @mouseup="selectAtCursor" />
      </div>
    </div>
  </div>
</template>
