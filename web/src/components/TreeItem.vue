<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { canRename } from "../edit";
import { getAt, pathKey, samePath, startsWith, txt, worst, type TreeNode } from "../model";
import { actions, diagsByNode, lang, store, viewData } from "../store";
import InlineRename from "./InlineRename.vue";
import TreeIcon from "./TreeIcon.vue";
import { N_, t } from "../i18n";

const props = defineProps<{
  node: TreeNode;
  depth: number;
  expanded: Set<string>;
  visible: Set<string> | null; // null: no filter
  query: string;
}>();
const emit = defineEmits<{ toggle: [key: string] }>();

const DIR_TITLE: Record<string, string> = { tx: N_("TX — sent by the device"), rx: N_("RX — received by the device (command)") };

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
// A frame selected through a link is highlighted only in the link, not at its sender (and the other way round)
const selected = computed(() => samePath(store.selected, props.node.path)
  && (store.selectedVia ?? undefined) === props.node.receiver);
const onPath = computed(() => !selected.value && startsWith(store.selected, props.node.path));
const match = computed(() => props.query !== "" && props.node.search.includes(props.query));

// The tree shows titles for people, not identifiers: a double click edits what is visible.
// A device is labeled "short · title", each part edited with its own double click; flags and SDO have no title, so the name is edited.
type Part = "name" | "short" | "title";
const renaming = ref<Part | null>(null);
const nodeData = computed(() => (viewData.value ? getAt(viewData.value, props.node.path) : null));
const titled = computed(() => ["bus", "device", "frame", "signal"].includes(props.node.kind));
const title = computed(() => txt(nodeData.value?.title, lang.value));
// No title yet: the edit field opens with the identifier the tree shows now
const partValue = (p: Part) => (p === "title" ? title.value || nodeData.value?.name || "" : nodeData.value?.[p] ?? "");
function startRename(field: Part) {
  if (props.node.from === undefined && canRename(props.node.path)) renaming.value = field;
}

// A new bus or device: open the title for editing right away (it is required and filled in by default)
watch(() => store.renameRequest, (p) => {
  if (p && props.node.from === undefined && samePath(p, props.node.path)) {
    store.renameRequest = null;
    startRename("title");
  }
}, { immediate: true });

function click() {
  actions.select(props.node.path, props.node.receiver ?? null);
  if (!props.expanded.has(props.node.key) && props.node.children.length) emit("toggle", props.node.key);
}
</script>

<template>
  <li>
    <!-- A link to another device's frame has its own data-key: scrolling to the selected frame goes to the original -->
    <div class="tree-row" :class="{ selected, 'on-path': onPath, match, link: node.from !== undefined, included: !!node.file }"
         :style="{ paddingLeft: depth * 14 + 6 + 'px' }"
         :data-key="node.from !== undefined ? node.key : pathKey(node.path)" @click="click"
         :title="node.from !== undefined ? t('Receives the frame from {sender}', { sender: node.from || t('outside the map') }) : undefined">
      <span class="twisty" :class="{ hidden: !node.children.length }" @click.stop="emit('toggle', node.key)">
        {{ open ? "▾" : "▸" }}
      </span>
      <TreeIcon :kind="node.kind" :dir="node.dir"
                :hint="node.kind === 'frame' ? (node.dir ? t(DIR_TITLE[node.dir]) : t('broadcast')) : undefined" />
      <InlineRename v-if="renaming" :path="node.path" :field="renaming" :value="partValue(renaming)"
                    @done="renaming = null" />
      <span v-else-if="node.kind === 'device' && nodeData?.short" class="tlabel">
        <span @dblclick.stop="startRename('short')">{{ nodeData.short }}</span> · <span
          @dblclick.stop="startRename('title')">{{ title || nodeData.name }}</span>
      </span>
      <span v-else class="tlabel" @dblclick.stop="startRename(titled ? 'title' : 'name')">{{ node.label }}</span>
      <span v-if="node.sub" class="tsub mono">{{ node.sub }}</span>
      <span v-if="node.from !== undefined" class="tsub link-mark">↪</span>
      <span v-if="node.fileRoot" class="tsub include-mark"
            :title="t('From the included file {file}, read-only', { file: node.file })">🔗 {{ node.file }}</span>
      <span v-if="own" class="dot" :class="own" :title="own" />
      <span v-else-if="nested" class="dot ring" :class="nested" />
    </div>
    <ul v-if="open && kids.length">
      <TreeItem v-for="c in kids" :key="c.key" :node="c" :depth="depth + 1" :expanded="expanded" :visible="visible"
                :query="query" @toggle="emit('toggle', $event)" />
    </ul>
  </li>
</template>
