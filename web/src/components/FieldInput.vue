<script setup lang="ts">
// Одно поле формы. Значение фиксируется по Enter / потере фокуса (событие change) — одна правка = один шаг undo.
import { computed, ref, watch } from "vue";
import { formatValue, parseInput, ParseError, type FieldDef } from "../fields";
import type { Diagnostic } from "../types";
import { i18n, t } from "../i18n";
import { store } from "../store";
import HelpTip from "./HelpTip.vue";

const props = defineProps<{
  def: FieldDef;
  value: unknown;
  diags?: Diagnostic[];
  readonly?: boolean;
  placeholder?: string;
  lang?: string;
}>();
const emit = defineEmits<{ commit: [value: unknown] }>();

const error = ref("");
const draft = ref("");
const draftEn = ref("");

function syncFromValue() {
  error.value = "";
  const v = props.value;
  if (props.def.type === "loc") {
    if (v && typeof v === "object") {
      const o = v as Record<string, string>;
      draft.value = o.ru ?? "";
      draftEn.value = o.en ?? "";
    } else {
      draft.value = (v as string) ?? "";
      draftEn.value = "";
    }
  } else {
    draft.value = formatValue(props.def.type, v);
  }
}
watch(() => props.value, syncFromValue, { immediate: true, deep: true });

const showEn = ref(false);
watch(() => draftEn.value, (v) => { if (v) showEn.value = true; }, { immediate: true });

function commit() {
  try {
    if (props.def.type === "loc") {
      const ru = draft.value.trim();
      const en = draftEn.value.trim();
      const old = props.value;
      const extra = old && typeof old === "object" ? { ...(old as Record<string, string>) } : {};
      let next: unknown;
      if (en) next = { ...extra, ru, en };
      else if (Object.keys(extra).some((k) => k !== "ru" && k !== "en")) next = { ...extra, ru, en: undefined };
      else next = ru || null;
      if (JSON.stringify(next ?? null) !== JSON.stringify(old ?? null)) emit("commit", next);
      return;
    }
    const next = parseInput(props.def.type, draft.value);
    const old = props.value ?? null;
    if (JSON.stringify(next) !== JSON.stringify(old)) emit("commit", next);
    // Нормализуем ввод сразу («1,5» → «1.5»): если значение не изменилось, обновления с сервера не будет
    draft.value = formatValue(props.def.type, next);
    error.value = "";
  } catch (e) {
    error.value = e instanceof ParseError ? e.message : String(e);
  }
}

function onSelect(e: Event) {
  const v = (e.target as HTMLSelectElement).value;
  let next: unknown = v === "" ? null : v;
  if (props.def.key.endsWith("bit_length") && v) next = Number(v);
  emit("commit", next);
}

function onBool(e: Event) {
  emit("commit", (e.target as HTMLInputElement).checked ? true : null);
}

// Подсказки единиц: обозначение на языке интерфейса, перевод — во всплывающей подписи.
// Свой список вместо <datalist>: тот не стилизуется (слишком высокий) и при заполненном поле показывает только совпадения.
const suggestions = computed<Array<[string, string]>>(() => {
  if (props.def.suggest !== "units") return [];
  const en = i18n.lang === "en";
  return (store.state?.units ?? []).map(([ru, e]) => (en ? [e, ru] : [ru, e]) as [string, string]);
});
const listOpen = ref(false);
const filter = ref("");          // текст, набранный после открытия; пусто — показываем всё
const shown = computed(() => {
  const q = filter.value.trim().toLowerCase();
  return q ? suggestions.value.filter(([v, o]) => v.toLowerCase().includes(q) || o.toLowerCase().includes(q))
    : suggestions.value;
});

function toggleList() {
  filter.value = "";
  listOpen.value = !listOpen.value;
}

function onType() {
  if (!suggestions.value.length) return;
  filter.value = draft.value;
  listOpen.value = true;
}

function pick(v: string) {
  draft.value = v;
  listOpen.value = false;
  commit();
}

function onBlur() {
  listOpen.value = false;
}

const level = computed(() => {
  const ds = props.diags ?? [];
  if (ds.some((d) => d.level === "error")) return "error";
  if (ds.some((d) => d.level === "warning")) return "warning";
  return "";
});
</script>

<template>
  <label class="field" :class="[{ wide: def.wide }, level]">
    <span class="field-label"><HelpTip v-if="def.help" :text="def.help" />{{ t(def.label) }}</span>

    <select v-if="def.type === 'select'" :value="value ?? ''" :disabled="readonly" @change="onSelect">
      <option v-for="[v, l] in def.options" :key="v" :value="v">{{ t(l) }}</option>
      <option v-if="value != null && !def.options?.some(([v]) => v === String(value))" :value="String(value)">
        {{ value }}
      </option>
    </select>

    <span v-else-if="def.type === 'bool'" class="checkbox">
      <input type="checkbox" :checked="!!value" :disabled="readonly" @change="onBool" />
    </span>

    <span v-else-if="def.type === 'loc'" class="loc">
      <input v-model="draft" :readonly="readonly" :placeholder="placeholder" @change="commit" />
      <input v-if="showEn" v-model="draftEn" class="en" :readonly="readonly" placeholder="English"
             @change="commit" />
      <button v-else-if="!readonly" type="button" class="link" :title="t('Добавить перевод')" @click="showEn = true">en</button>
    </span>

    <span v-else-if="suggestions.length" class="suggest">
      <input v-model="draft" :readonly="readonly" :placeholder="placeholder"
             @change="commit" @input="onType" @blur="onBlur" @keydown.esc="listOpen = false" />
      <button v-if="!readonly" type="button" class="suggest-toggle" :title="t('Выбрать из списка')"
              @mousedown.prevent @click.prevent="toggleList">▾</button>
      <span v-if="listOpen && shown.length" class="suggest-list" @mousedown.prevent>
        <button v-for="[v, other] in shown" :key="v" type="button" :class="{ current: v === draft }"
                :title="v === other ? undefined : other" @click.prevent="pick(v)">{{ v }}</button>
      </span>
    </span>

    <input v-else :type="def.type === 'date' ? 'date' : 'text'" v-model="draft" :readonly="readonly"
           :placeholder="placeholder" :class="{ mono: ['hex', 'int', 'float', 'intlist', 'strlist'].includes(def.type) }"
           @change="commit" />

    <span v-if="error" class="field-msg error">{{ error }}</span>
    <span v-for="d in diags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
    <span v-if="def.hint && !error && !diags?.length" class="field-hint">{{ t(def.hint) }}</span>
  </label>
</template>
