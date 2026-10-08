<script setup lang="ts">
// Rename in place (the node's heading, the tree): Enter / losing focus saves, Esc cancels.
// An error (empty or taken name) on Enter shows at the field; on losing focus it shows as a toast and the edit is cancelled.
import { nextTick, onMounted, ref } from "vue";
import { renameNode, setShort, setTitle } from "../edit";
import { toast } from "../store";
import type { Path } from "../types";

// field: name is the node's name (checked for being taken), short the device abbreviation, title the node's title
const props = defineProps<{ path: Path; value: string; field?: "name" | "short" | "title" }>();
const emit = defineEmits<{ done: [] }>();

const draft = ref(props.value);
const error = ref("");
const input = ref<HTMLInputElement | null>(null);
let busy = false;

onMounted(async () => {
  await nextTick();
  input.value?.focus();
  input.value?.select();
});

async function save(fromBlur = false) {
  if (busy) return;
  busy = true;
  // Nothing is written without changes: the title field may open with the identifier while there is no title
  if (draft.value.trim() === props.value.trim()) {
    emit("done");
    return;
  }
  const err = props.field === "short" ? await setShort(props.path, draft.value)
    : props.field === "title" ? await setTitle(props.path, draft.value)
    : await renameNode(props.path, draft.value);
  if (err && fromBlur) {
    toast(err);
    emit("done");
  } else if (err) {
    busy = false;
    error.value = err;
  } else {
    emit("done");
  }
}

function cancel() {
  busy = true;            // blur after Esc must not save
  emit("done");
}
</script>

<template>
  <span class="inline-rename" @click.stop @dblclick.stop>
    <input ref="input" v-model="draft" :class="{ invalid: !!error }" :title="error"
           @keydown.enter.prevent="save()" @keydown.esc.prevent="cancel" @blur="save(true)" @input="error = ''" />
    <span v-if="error" class="field-msg error">{{ error }}</span>
  </span>
</template>
