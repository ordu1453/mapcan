<script setup lang="ts">
// Editing the whole YAML. Text without syntax errors is applied while typing (the tree and validation
// update right away), Ctrl+Enter or the button applies it immediately; validation is the same as in the CLI.
// A map with included files shows one file at a time: the one the node selected in the tree is written in.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { api } from "../api";
import { actions, diagnostics as diags, store, tree, yamlLine, yamlLocal as local } from "../store";
import { localPath, mergedPath, samePath, type TreeNode } from "../model";
import { highlight, keyEdit, nodeAtLine, nodeLines, type TextEdit } from "../yamltext";
import { complete, type CompletionList, type Schema } from "../yamlcomplete";
import { t } from "../i18n";

// The draft lives in the store: going to another tab does not lose it but applies it.
const text = computed({
  get: () => store.yaml.draft
    ?? (store.yamlFile === null ? store.state?.text : store.state?.parts?.[store.yamlFile]) ?? "",
  set: (v: string) => { store.yaml.draft = v; },
});

// The map and its included files, for the file switch
const files = computed(() => Object.keys(store.state?.parts ?? {}));

// Path of the selected node in the shown file; null if it is written in another file.
const shownPath = computed(() => {
  const l = localPath(store.state?.included, store.selected);
  return l.file === store.yamlFile ? l.path : null;
});
const ta = ref<HTMLTextAreaElement | null>(null);
const gutter = ref<HTMLDivElement | null>(null);
const code = ref<HTMLPreElement | null>(null);
const box = ref<HTMLDivElement | null>(null);
const scrollTop = ref(0);
const scrollLeft = ref(0);
const LINE = 20;

const lines = computed(() => text.value.split("\n").length);
const html = computed(() => highlight(text.value).join("\n") + "\n");

// Lines of the node selected in the tree.
const range = computed(() => (store.state?.data && shownPath.value ? nodeLines(text.value, shownPath.value) : null));
const inRange = (n: number) => !!range.value && n >= range.value.first && n <= range.value.last;

// On a selection in the tree, scroll to the node if it is outside the visible area.
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

// The other way: the cursor in the text selects the tree node the line belongs to (the paths of the tree nodes
// written in the shown file, as they are in it).
const treePaths = computed(() => {
  const out: TreeNode["path"][] = [];
  const walk = (ns: TreeNode[]) => ns.forEach((n) => {
    const l = localPath(store.state?.included, n.path);
    if (l.file === store.yamlFile) out.push(l.path);
    walk(n.children);
  });
  walk(tree.value);
  return out;
});

function selectAtCursor() {
  const el = ta.value;
  if (!el || !store.state?.data) return;
  const line = text.value.slice(0, el.selectionStart).split("\n").length;
  const local = nodeAtLine(text.value, line, treePaths.value);
  const p = local && mergedPath(store.state.included, store.yamlFile, local);
  if (p && !samePath(p, store.selected)) actions.select(p);
}

function showFile(e: Event) {
  void actions.openYaml((e.target as HTMLSelectElement).value || null);
}

function onKeyUp(e: KeyboardEvent) {
  if (/^(Arrow|Page|Home|End)/.test(e.key) && !(hint.value && /^Arrow(Up|Down)$/.test(e.key))) {
    hint.value = null;
    selectAtCursor();
  }
}

// ---- suggestions of keys and values from the format's schema (Ctrl+Space shows them by hand)
let schema: Schema | null = null;
const hint = ref<CompletionList | null>(null);
const hintIdx = ref(0);
const charWidth = ref(8);

onMounted(async () => {
  if (ta.value) {
    const ctx = document.createElement("canvas").getContext("2d");
    if (ctx) {
      ctx.font = getComputedStyle(ta.value).font;
      charWidth.value = ctx.measureText("0".repeat(20)).width / 20;
    }
  }
  try {
    schema = await api.schema();
  } catch {
    /* no schema, no suggestions */
  }
});

function showHint(force = false) {
  const el = ta.value;
  hint.value = el && schema && !el.readOnly && el.selectionStart === el.selectionEnd
    ? complete(el.value, el.selectionStart, schema, force) : null;
  hintIdx.value = 0;
}

function onInput(e: Event) {
  const kind = (e as InputEvent).inputType ?? "";
  const el = ta.value;
  // A new list item "- ", an opening "{" or the next key after ", ": fields right away
  const lineHead = el ? el.value.slice(el.value.lastIndexOf("\n", el.selectionStart - 1) + 1, el.selectionStart) : "";
  if (kind === "insertText" && (/^\s*-\s$/.test(lineHead) || /(\{|,\s)$/.test(lineHead))) showHint(true);
  else if (kind.startsWith("insert") && kind !== "insertFromPaste") showHint();
  else if (hint.value && kind.startsWith("delete")) showHint();
  else hint.value = null;
}

function acceptHint(i: number) {
  const c = hint.value?.items[i];
  const el = ta.value;
  hint.value = null;
  if (!c || !el) return;
  replace(el, c.edit);
  if (c.chain) showHint(true);
}

// The list goes below the cursor's line at the start of the word; at the bottom edge, above the line.
const hintStyle = computed(() => {
  const h = hint.value;
  if (!h) return {};
  const left = 10 + h.col * charWidth.value - scrollLeft.value;
  const top = 6 + (h.line + 1) * LINE - scrollTop.value;
  const height = box.value?.clientHeight ?? 0;
  return top + 230 > height && top - LINE > 230
    ? { left: left + "px", bottom: height - (top - LINE) + "px" }
    : { left: left + "px", top: top + "px" };
});

watch(hintIdx, async () => {
  await nextTick();
  box.value?.querySelector(".yaml-suggest li.active")?.scrollIntoView({ block: "nearest" });
});

// Live validation: the unapplied text is validated on the server with a delay after typing
// and, if it parses, applied (one undo step for the whole series of typing). The result of the validation
// is in the store, and the Validation panel shows it too.
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
      const r = await api.check(value, store.yamlFile);
      if (seq !== checkSeq) return;
      if (store.yaml.draft === value) store.yaml.diags = r.diagnostics;
      if (!store.state?.readonly && !r.diagnostics.some((d) => d.code === "yaml")) await actions.setText(value, true);
    } catch {
      /* no connection: the marks stay as they were */
    }
  }, 400);
});

onBeforeUnmount(() => clearTimeout(checkTimer));

// Syntax errors of the draft are a line in the toolbar (the height does not change, the editor does not move).
// Other messages are in the line gutter and in the Validation panel.
const syntaxErrors = computed(() => (local.value ? (store.yaml.diags ?? []).filter((d) => d.code === "yaml") : []));

const marks = computed(() => {
  const m = new Map<number, string>();
  for (const d of diags.value) {
    const line = yamlLine(d);
    if (line == null) continue;
    const cur = m.get(line);
    if (cur !== "error") m.set(line, d.level === "error" ? "error" : cur ?? d.level);
  }
  return m;
});

const lineMessages = computed(() => {
  const m = new Map<number, string>();
  for (const d of diags.value) {
    const line = yamlLine(d);
    if (line == null) continue;
    m.set(line, (m.has(line) ? m.get(line) + "\n" : "") + `${d.level}[${d.code}]: ${d.message}`);
  }
  return m;
});

function syncScroll() {
  if (!ta.value) return;
  scrollTop.value = ta.value.scrollTop;
  scrollLeft.value = ta.value.scrollLeft;
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
  // The field switched to the server's text: the cursor and the scroll stay in place.
  await nextTick();
  if (el && sel && document.activeElement === el) {
    el.setSelectionRange(sel[0], sel[1]);
    el.scrollTop = sel[2];
    syncScroll();
  }
}

// Cancel the input not applied on the server yet.
function revert() {
  store.yaml = { draft: null, applied: null, diags: null };
}

// An edit through execCommand goes into the textarea's undo history (Ctrl+Z); assigning text does not.
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

// After Esc, Tab moves the focus out of the field, as in an ordinary form.
let tabLeaves = false;

function onKey(e: KeyboardEvent) {
  const el = e.target as HTMLTextAreaElement;
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    void apply();
    return;
  }
  if (hint.value && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const n = hint.value.items.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      hintIdx.value = (hintIdx.value + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      return;
    }
    if ((e.key === "Enter" || e.key === "Tab") && !e.shiftKey) {
      e.preventDefault();
      acceptHint(hintIdx.value);
      return;
    }
    if (e.key === "Escape") {
      hint.value = null;
      return;
    }
  }
  if (e.ctrlKey && e.code === "Space") {
    e.preventDefault();
    showHint(true);
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
      <select v-if="files.length" class="yaml-file" :value="store.yamlFile ?? ''"
              :title="t('The file of the map shown: a node selected in the tree opens its file')" @change="showFile">
        <option value="">{{ store.state?.file }}</option>
        <option v-for="f in files" :key="f" :value="f">🔗 {{ f }}{{ store.state?.dirty_files?.includes(f) ? " •" : "" }}</option>
      </select>
      <span v-if="syntaxErrors.length" class="yaml-problem">
        <button class="link" :title="syntaxErrors[0].message" @click="reveal(yamlLine(syntaxErrors[0]))">
          <b>{{ t("Line {line}", { line: yamlLine(syntaxErrors[0]) ?? "?" }) }}:</b> {{ syntaxErrors[0].message }}
        </button>
        <span v-if="syntaxErrors.length > 1" class="muted">{{ t("and {count} more", { count: syntaxErrors.length - 1 }) }}</span>
      </span>
      <span v-else class="muted yaml-hint">{{ t("") }}</span>
      <span v-if="local" class="badge warning">{{ t("not applied") }}</span>
      <button :disabled="!local || store.state?.readonly" @click="revert">{{ t("Discard changes") }}</button>
      <button class="primary" :disabled="!local || store.state?.readonly" title="Ctrl+Enter" @click="apply">{{ t("Apply") }}</button>
    </div>
    <div class="yaml-body">
      <div ref="gutter" class="gutter mono">
        <div v-for="n in lines" :key="n" :class="[marks.get(n), { 'in-node': inRange(n) }]" :title="lineMessages.get(n)"
             :style="{ height: LINE + 'px' }">{{ n }}</div>
      </div>
      <div ref="box" class="yaml-code">
        <!-- Highlighting is layers under the transparent text of the textarea; scrolling is synchronized. -->
        <div v-if="range" class="yaml-node" :style="{ top: 6 + (range.first - 1) * LINE - scrollTop + 'px',
             height: (range.last - range.first + 1) * LINE + 'px' }" />
        <pre ref="code" class="yaml-hl mono" aria-hidden="true" :style="{ lineHeight: LINE + 'px' }"><code v-html="html" /></pre>
        <textarea ref="ta" v-model="text" class="mono" spellcheck="false" :readonly="store.state?.readonly"
                  :style="{ lineHeight: LINE + 'px' }" @scroll="syncScroll" @keydown="onKey" @input="onInput"
                  @keyup="onKeyUp" @mouseup="hint = null; selectAtCursor()" @blur="hint = null" />
        <div v-if="hint" class="yaml-suggest" :style="hintStyle" @mousedown.prevent>
          <ul>
            <li v-for="(c, i) in hint.items" :key="c.label" :class="{ active: i === hintIdx }"
                @mouseenter="hintIdx = i" @click="acceptHint(i)">
              <span class="mono">{{ c.label }}</span><span class="muted">{{ c.detail }}</span>
            </li>
          </ul>
          <div v-if="hint.items[hintIdx]?.doc" class="yaml-suggest-doc">{{ hint.items[hintIdx].doc }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
