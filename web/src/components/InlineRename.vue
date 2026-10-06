<script setup lang="ts">
// Поле переименования на месте (заголовок узла, дерево): Enter / потеря фокуса — сохранить, Esc — отмена.
// Ошибка (пустое или занятое имя) по Enter показывается у поля; при потере фокуса — всплывающим сообщением, правка отменяется.
import { nextTick, onMounted, ref } from "vue";
import { renameNode, setShort, setTitle } from "../edit";
import { toast } from "../store";
import type { Path } from "../types";

// field: name — имя узла (с проверкой занятости), short — обозначение устройства, title — название шины
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
  busy = true;            // blur после Esc не должен сохранять
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
