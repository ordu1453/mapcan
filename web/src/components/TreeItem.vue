<script setup lang="ts">
import { computed, ref } from "vue";
import { canRename } from "../edit";
import { getAt, pathKey, samePath, startsWith, txt, worst, type TreeNode } from "../model";
import { actions, diagsByNode, lang, store } from "../store";
import InlineRename from "./InlineRename.vue";
import TreeIcon from "./TreeIcon.vue";
import { N_, t } from "../i18n";

const props = defineProps<{
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  visible: Set<string> | null; // null — фильтра нет
  query: string;
}>();
const emit = defineEmits<{ toggle: [key: string] }>();

const DIR_TITLE: Record<string, string> = { tx: N_("TX — передаёт устройство"), rx: N_("RX — команда/приём устройством") };

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

// Двойной щелчок по названию — переименование (у шины в дереве виден title, правится name)
// У устройства подпись «short · name», у шины — название (title) и имя справа: каждая часть правится своим двойным щелчком
type Part = "name" | "short" | "title";
const renaming = ref<Part | null>(null);
const nodeData = computed(() => (store.state?.data ? getAt(store.state.data, props.node.path) : null));
const busTitle = computed(() => (props.node.kind === "bus" ? txt(nodeData.value?.title, lang.value) : ""));
const partValue = (p: Part) => (p === "title" ? busTitle.value : nodeData.value?.[p] ?? "");
function startRename(field: Part = "name") {
  if (canRename(props.node.path)) renaming.value = field;
}

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
      <TreeIcon :kind="node.kind" :dir="node.dir"
                :hint="node.kind === 'frame' ? (node.dir ? t(DIR_TITLE[node.dir]) : t('широковещательный')) : undefined" />
      <InlineRename v-if="renaming" :path="node.path" :field="renaming" :value="partValue(renaming)"
                    @done="renaming = null" />
      <span v-else-if="node.kind === 'device' && nodeData?.short" class="tlabel">
        <span @dblclick.stop="startRename('short')">{{ nodeData.short }}</span> · <span
          @dblclick.stop="startRename('name')">{{ nodeData.name }}</span>
      </span>
      <span v-else class="tlabel" @dblclick.stop="startRename(busTitle ? 'title' : 'name')">{{ node.label }}</span>
      <span v-if="node.sub && !(node.kind === 'bus' && !busTitle)" class="tsub mono"
            @dblclick.stop="node.kind === 'bus' && startRename('name')">{{ node.sub }}</span>
      <span v-if="own" class="dot" :class="own" :title="own" />
      <span v-else-if="nested" class="dot ring" :class="nested" />
    </div>
    <ul v-if="open && kids.length">
      <TreeItem v-for="c in kids" :key="c.key" :node="c" :depth="depth + 1" :expanded="expanded" :visible="visible"
                :query="query" @toggle="emit('toggle', $event)" />
    </ul>
  </li>
</template>
