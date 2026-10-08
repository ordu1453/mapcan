<script setup lang="ts">
// Одно поле формы. Значение фиксируется по Enter / потере фокуса (событие change) — одна правка = один шаг undo.
import { computed, nextTick, ref, watch } from "vue";
import { formatValue, parseInput, ParseError, selectValue } from "../form/input";
import type { FieldDef, Option } from "../form/spec";
import { samePath, startsWith } from "../model";
import type { Diagnostic, Path } from "../types";
import { t } from "../i18n";
import { lang as docLang, store } from "../store";
import HelpTip from "./HelpTip.vue";

const props = defineProps<{
  def: FieldDef;
  value: unknown;
  /** Options of a select or a set of devices, computed for the node. */
  options?: Option[];
  diags?: Diagnostic[];
  readonly?: boolean;
  placeholder?: string;
  lang?: string;
  /** Полный путь поля в карте — для перехода к полю из панели «Проверка». */
  path?: Path;
  required?: boolean;
}>();
const emit = defineEmits<{ commit: [value: unknown] }>();

const error = ref("");
const draft = ref("");

// Текст на нескольких языках правится на языке документа; переводы на другие языки сохраняются как есть
const locMap = computed(() => (props.value && typeof props.value === "object" && !Array.isArray(props.value)
  ? props.value as Record<string, string> : null));
/** Текст на другом языке — подсказка в пустом поле, если на языке документа его ещё нет. */
const locFallback = computed(() => (locMap.value ? Object.values(locMap.value).find((x) => x) ?? "" : ""));

function syncFromValue() {
  error.value = "";
  const v = props.value;
  if (props.def.type === "loc") draft.value = locMap.value ? locMap.value[docLang.value] ?? "" : (v as string) ?? "";
  else draft.value = formatValue(props.def.type, v);
}
watch([() => props.value, docLang], syncFromValue, { immediate: true, deep: true });

function commit() {
  try {
    if (props.def.type === "loc") {
      const text = draft.value.trim();
      const old = props.value;
      let next: unknown = text || null;
      if (locMap.value) {
        const rest = Object.fromEntries(Object.entries(locMap.value).filter(([k, x]) => k !== docLang.value && x));
        next = Object.keys(rest).length ? (text ? { ...locMap.value, [docLang.value]: text } : rest) : next;
      }
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
  emit("commit", selectValue((e.target as HTMLSelectElement).value, props.def.numeric));
}

// Набор устройств: варианты в порядке options, неизвестные имена из карты — в конце (их можно снять)
const chosen = computed<string[]>(() => (Array.isArray(props.value) ? props.value.map(String) : []));
const chips = computed<Array<[string, string, boolean]>>(() => {
  const opts = props.options ?? [];
  const known = new Set(opts.map(([v]) => v));
  return [...opts.map(([v, l]) => [v, l, true] as [string, string, boolean]),
    ...chosen.value.filter((v) => !known.has(v)).map((v) => [v, v, false] as [string, string, boolean])];
});

function toggle(v: string) {
  const set = new Set(chosen.value);
  if (set.has(v)) set.delete(v); else set.add(v);
  const next = chips.value.map(([x]) => x).filter((x) => set.has(x));
  emit("commit", next.length ? next : null);
}

function onBool(e: Event) {
  emit("commit", (e.target as HTMLInputElement).checked ? true : null);
}

// Подсказки единиц: обозначение на языке документов карты, перевод — во всплывающей подписи.
// Свой список вместо <datalist>: тот не стилизуется (слишком высокий) и при заполненном поле показывает только совпадения.
const suggestions = computed<Array<[string, string]>>(() => {
  if (props.def.type !== "unit") return [];
  const en = docLang.value === "en";
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

const empty = computed(() => {
  const v = props.value;
  if (v == null || v === "") return true;
  if (typeof v === "object" && !Array.isArray(v)) return !Object.values(v as Record<string, unknown>).some((x) => x);
  return Array.isArray(v) && !v.length;
});
const missing = computed(() => !!props.required && empty.value && !props.readonly);

const level = computed(() => {
  const ds = props.diags ?? [];
  if (ds.some((d) => d.level === "error")) return "error";
  if (ds.some((d) => d.level === "warning")) return "warning";
  return missing.value ? "missing" : "";
});

// Переход из панели «Проверка»: прокрутить к полю, поставить фокус и коротко подсветить
const root = ref<HTMLElement | null>(null);
const flash = ref(false);
watch(() => store.focusPath, async (fp) => {
  if (!fp || !props.path || !(samePath(fp, props.path) || startsWith(fp, props.path))) return;
  store.focusPath = null;
  await nextTick();
  root.value?.scrollIntoView({ block: "center", behavior: "smooth" });
  root.value?.querySelector<HTMLElement>("input, select")?.focus({ preventScroll: true });
  flash.value = false;
  await nextTick();
  flash.value = true;
  setTimeout(() => { flash.value = false; }, 1600);
}, { immediate: true });
</script>

<template>
  <!-- Переключатели — не внутри label: щелчок по подписи нажимал бы первую кнопку -->
  <component :is="def.type === 'devices' ? 'div' : 'label'" ref="root" class="field" :class="[{ wide: def.wide, flash }, level]">
    <span class="field-label"><HelpTip v-if="def.help" :text="def.help" />{{ t(def.label) }}<span
      v-if="required" class="req" :title="t('Required field')">*</span></span>

    <select v-if="def.type === 'select'" :value="value ?? ''" :disabled="readonly" @change="onSelect">
      <option v-for="[v, l, off] in options" :key="v" :value="v" :disabled="!!off && v !== String(value ?? '')">{{ l }}</option>
      <option v-if="value != null && !options?.some(([v]) => v === String(value))" :value="String(value)">
        {{ value }}
      </option>
    </select>

    <span v-else-if="def.type === 'devices'" class="chips">
      <button v-for="[v, l, known] in chips" :key="v" type="button" class="dev-chip"
              :class="{ on: chosen.includes(v), unknown: !known }" :disabled="readonly"
              :title="known ? undefined : t('Device is not defined on the bus')" @click="toggle(v)">{{ l }}</button>
      <span v-if="!chips.length" class="field-hint">{{ t("There are no other devices on the bus") }}</span>
    </span>

    <span v-else-if="def.type === 'bool'" class="checkbox">
      <input type="checkbox" :checked="!!value" :disabled="readonly" @change="onBool" />
    </span>

    <input v-else-if="def.type === 'loc'" v-model="draft" :readonly="readonly"
           :placeholder="draft ? placeholder : locFallback || placeholder" @change="commit" />

    <span v-else-if="suggestions.length" class="suggest">
      <input v-model="draft" :readonly="readonly" :placeholder="placeholder"
             @change="commit" @input="onType" @blur="onBlur" @keydown.esc="listOpen = false" />
      <button v-if="!readonly" type="button" class="suggest-toggle" :title="t('Pick from the list')"
              @mousedown.prevent @click.prevent="toggleList">▾</button>
      <span v-if="listOpen && shown.length" class="suggest-list" @mousedown.prevent>
        <button v-for="[v, other] in shown" :key="v" type="button" :class="{ current: v === draft }"
                :title="v === other ? undefined : other" @click.prevent="pick(v)">{{ v }}</button>
      </span>
    </span>

    <input v-else :type="def.type === 'date' ? 'date' : 'text'" v-model="draft" :readonly="readonly"
           :placeholder="placeholder" :class="{ mono: def.mono || ['hex', 'int', 'float', 'intlist', 'strlist'].includes(def.type) }"
           @change="commit" />

    <span v-if="error" class="field-msg error">{{ error }}</span>
    <span v-for="d in diags" :key="d.code + d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
    <span v-if="missing && !error && !diags?.length" class="field-msg missing">{{ t("Required field") }}</span>
    <span v-else-if="def.hint && !error && !diags?.length" class="field-hint">{{ t(def.hint) }}</span>
  </component>
</template>
