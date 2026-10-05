<script setup lang="ts">
import { computed } from "vue";
import { pathKey, samePath, startsWith, worst, type TreeNode } from "../model";
import { actions, diagsByNode, store } from "../store";

const props = defineProps<{
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  visible: Set<string> | null; // null — фильтра нет
  query: string;
}>();
const emit = defineEmits<{ toggle: [key: string] }>();

const ICON: Record<string, string> = {
  document: "▤", bus: "≡", device: "▣", frame: "▭", signal: "∿", flag: "⚑", sdo: "⇄", unknown: "·",
};

const open = computed(() => props.query !== "" || props.expanded.has(props.node.key));
const kids = computed(() =>
  props.visible ? props.node.children.filter((c) => props.visible!.has(c.key)) : props.node.children,
);
const own = computed(() => worst(diagsByNode.value.get(props.node.key)));
const nested = computed(() => {
  if (open.value && kids.value.length) return null;
  let lvl: string | null = null;
  for (const [k, ds] of diagsByNode.value) {
    if (k !== props.node.key && k.startsWith(props.node.key + "/")) {
      const w = worst(ds);
      if (w === "error") return "error";
      if (w === "warning") lvl = "warning";
    }
  }
  return lvl;
});
const selected = computed(() => samePath(store.selected, props.node.path));
const onPath = computed(() => !selected.value && startsWith(store.selected, props.node.path));
const match = computed(() => props.query !== "" && props.node.search.includes(props.query));

function click() {
  actions.select(props.node.path);
  if (!props.expanded.has(props.node.key) && props.node.children.length) emit("toggle", props.node.key);
}
</script>

<template>
  <li>
    <div class="tree-row" :class="{ selected, 'on-path': onPath, match }" :style="{ paddingLeft: depth * 14 + 6 + 'px' }"
         :data-key="pathKey(node.path)" @click="click">
      <span class="twisty" :class="{ hidden: !node.children.length }" @click.stop="emit('toggle', node.key)">
        {{ open ? "▾" : "▸" }}
      </span>
      <span class="ticon" :class="node.kind">{{ ICON[node.kind] }}</span>
      <span class="tlabel">{{ node.label }}</span>
      <span v-if="node.sub" class="tsub mono">{{ node.sub }}</span>
      <span v-if="own" class="dot" :class="own" :title="own" />
      <span v-else-if="nested" class="dot ring" :class="nested" />
    </div>
    <ul v-if="open && kids.length">
      <TreeItem v-for="c in kids" :key="c.key" :node="c" :depth="depth + 1" :expanded="expanded" :visible="visible"
                :query="query" @toggle="emit('toggle', $event)" />
    </ul>
  </li>
</template>
