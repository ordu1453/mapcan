<script setup lang="ts">
// Дерево «документ → история; шина → устройство → кадр → сигнал → флаг» с поиском по имени, ID и описанию.
import { computed, nextTick, ref, watch } from "vue";
import { pathKey, type TreeNode } from "../model";
import { store, tree } from "../store";
import TreeItem from "./TreeItem.vue";
import { t } from "../i18n";

const query = ref("");
const expanded = ref(new Set<string>(["document", "buses/0"]));

const q = computed(() => query.value.trim().toLowerCase());

/** Узлы, которые видны при фильтре: совпавшие и их предки. */
const visible = computed<Set<string> | null>(() => {
  if (!q.value) return null;
  const terms = q.value.split(/\s+/);
  const out = new Set<string>();
  const walk = (n: TreeNode, chain: TreeNode[]): void => {
    if (terms.every((t) => n.search.includes(t) || (t.startsWith("0x") && n.sub.toLowerCase() === t))) {
      out.add(n.key);
      chain.forEach((c) => out.add(c.key));
    }
    n.children.forEach((c) => walk(c, [...chain, n]));
  };
  tree.value.forEach((n) => walk(n, []));
  return out;
});

const roots = computed(() => (visible.value ? tree.value.filter((n) => visible.value!.has(n.key)) : tree.value));
const count = computed(() => (visible.value ? visible.value.size : null));

function toggle(key: string) {
  const s = new Set(expanded.value);
  if (s.has(key)) s.delete(key);
  else s.add(key);
  expanded.value = s;
}

// Раскрыть предков выбранного узла (переход из диагностики, Diff и т.п.) и прокрутить к нему.
watch(
  () => store.selected,
  async (p) => {
    const s = new Set(expanded.value);
    for (let n = 1; n < p.length; n++) s.add(pathKey(p.slice(0, n)));
    expanded.value = s;
    await nextTick();
    // Кадр, выбранный через ссылку, — прокручиваем к ссылке
    (document.querySelector(".tree-row.selected")
      ?? document.querySelector(`.tree-row[data-key="${CSS.escape(pathKey(p))}"]`))?.scrollIntoView({ block: "nearest" });
  },
);
</script>

<template>
  <aside class="tree-panel">
    <div class="tree-search">
      <input v-model="query" type="search" :placeholder="t('Search: name, 0x196, description…')" />
      <span v-if="count !== null" class="muted">{{ count ? t("{n} found", { n: count }) : t("no matches") }}</span>
    </div>
    <ul class="tree">
      <TreeItem v-for="n in roots" :key="n.key" :node="n" :depth="0" :expanded="expanded" :visible="visible"
                :query="q" @toggle="toggle" />
    </ul>
  </aside>
</template>
