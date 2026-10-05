<script setup lang="ts">
// История изменений (document.history): список записей или изменения одной записи.
import { computed, ref } from "vue";
import { addRevision } from "../edit";
import type { FieldDef } from "../fields";
import { getAt, HISTORY_PATH, txt } from "../model";
import { actions, lang, store } from "../store";
import type { Path } from "../types";
import FieldInput from "./FieldInput.vue";

const props = defineProps<{ path: Path }>();

const readonly = computed(() => !!store.state?.readonly);
const diags = computed(() => store.state?.diagnostics ?? []);
const history = computed<any[]>(() => store.state?.data?.document?.history ?? []);
const isEntry = computed(() => props.path.length === 3);
const entry = computed(() => (isEntry.value ? getAt(store.state?.data, props.path) : null));
const changes = computed<unknown[]>(() => entry.value?.changes ?? []);

const changeDef = (i: number): FieldDef => ({ key: String(i), label: `${i + 1}.`, type: "loc", wide: true });
const changeDiags = (i: number) => {
  const p = [...props.path, "changes", i];
  return diags.value.filter((d) => d.node.length >= p.length && p.every((x, k) => String(x) === String(d.node[k])));
};

function setChange(i: number, value: unknown) {
  const p = [...props.path, "changes", i];
  // Пустая строка — удалить пункт, а не оставлять пустое изменение в документе.
  void actions.apply([value == null ? { op: "remove", path: p } : { op: "set", path: p, value }]);
}

function removeChange(i: number) {
  void actions.apply([{ op: "remove", path: [...props.path, "changes", i] }]);
}

function moveChange(i: number, delta: number) {
  const to = i + delta;
  if (to < 0 || to >= changes.value.length) return;
  void actions.apply([{ op: "move", path: [...props.path, "changes", i], to }]);
}

const draft = ref("");
async function addChange() {
  const text = draft.value.trim();
  if (!text) return;
  if (await actions.apply([{ op: "insert", path: [...props.path, "changes"], value: text }])) draft.value = "";
}
</script>

<template>
  <!-- Одна запись: список изменений -->
  <section v-if="isEntry" class="card">
    <h3>Изменения <span class="muted">{{ changes.length }}</span></h3>
    <div class="history-changes">
      <div v-for="(c, i) in changes" :key="i" class="history-change">
        <FieldInput :def="changeDef(i)" :value="c" :diags="changeDiags(i)" :readonly="readonly"
                    @commit="setChange(i, $event)" />
        <span v-if="!readonly" class="history-change-act">
          <button class="icon" title="Выше" :disabled="i === 0" @click="moveChange(i, -1)">↑</button>
          <button class="icon" title="Ниже" :disabled="i === changes.length - 1" @click="moveChange(i, 1)">↓</button>
          <button class="icon danger" title="Удалить пункт" @click="removeChange(i)">✕</button>
        </span>
      </div>
      <p v-if="!changes.length" class="muted">Изменений пока нет.</p>
      <div v-if="!readonly" class="history-add">
        <input v-model="draft" placeholder="Новое изменение — Enter, чтобы добавить" @keydown.enter="addChange" />
        <button :disabled="!draft.trim()" @click="addChange">Добавить</button>
      </div>
    </div>
  </section>

  <!-- Вся история -->
  <section v-else class="card">
    <h3>Записи <span class="muted">{{ history.length }}</span></h3>
    <table v-if="history.length" class="list">
      <thead><tr><th>Версия</th><th>Дата</th><th>Автор</th><th>Изменения</th></tr></thead>
      <tbody>
        <tr v-for="(h, i) in history" :key="i" class="clickable" @click="actions.select([...HISTORY_PATH, i])">
          <td class="mono">{{ h.version }}</td><td>{{ h.date }}</td>
          <td>
            {{ h.author }}
            <a v-if="h.github" class="mono gh" :href="`https://github.com/${h.github}`" target="_blank" rel="noopener"
               @click.stop>@{{ h.github }}</a>
          </td>
          <td><ul class="plain"><li v-for="(c, k) in h.changes ?? []" :key="k">{{ txt(c, lang) }}</li></ul></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">Записей пока нет.</p>
    <p v-if="!readonly" class="muted">
      Добавьте запись кнопкой «+ Запись» или сформируйте её из различий в «Сравнить версии» → «Добавить в историю».
    </p>
    <button v-if="!readonly && !history.length" class="primary" @click="addRevision">+ Первая запись</button>
  </section>
</template>
