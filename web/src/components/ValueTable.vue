<script setup lang="ts">
// Таблица значений enum: значение, имя, описание. Пишет values[ключ] операциями set/rename_key.
import { computed } from "vue";
import { actions } from "../store";
import { parseInteger } from "../fields";
import { nextFreeKey, startsWith, txt } from "../model";
import type { Diagnostic, Op, Path } from "../types";
import { t } from "../i18n";

const props = defineProps<{
  path: Path;                       // путь сигнала или флага
  values: Record<string, unknown> | undefined;
  hex?: boolean;
  readonly?: boolean;
  diags: Diagnostic[];
  title?: string;
}>();

interface Row {
  key: string;
  num: number;
  name: string;
  description: string;
  raw: unknown;
}

const rows = computed<Row[]>(() =>
  Object.entries(props.values ?? {})
    .map(([key, raw]) => {
      const o = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
      return {
        key, num: Number(key), raw,
        name: o ? String(o.name ?? "") : String(raw ?? ""),
        description: o ? txt(o.description) : "",
      };
    })
    .sort((a, b) => a.num - b.num),
);

const fmt = (n: number) => (props.hex && n >= 0 ? "0x" + n.toString(16).toUpperCase().padStart(2, "0") : String(n));

function rowDiags(r: Row) {
  return props.diags.filter((d) => startsWith(d.node, [...props.path, "values"]) && String(d.node[props.path.length + 1]) === r.key);
}

function apply(ops: Op[]) {
  void actions.apply(ops);
}

function setValue(r: Row, e: Event) {
  const s = (e.target as HTMLInputElement).value.trim();
  let n = NaN;
  try { n = parseInteger(s); } catch { /* ниже вернём прежнее значение */ }
  if (!Number.isInteger(n)) {
    (e.target as HTMLInputElement).value = fmt(r.num);
    return;
  }
  if (n === r.num) return;
  if (rows.value.some((x) => x.num === n)) {
    alert(t("Значение {n} уже есть в таблице", { n }));
    (e.target as HTMLInputElement).value = fmt(r.num);
    return;
  }
  apply([{ op: "rename_key", path: [...props.path, "values", r.key], new_key: String(n) }]);
}

function setEntry(r: Row, field: "name" | "description", e: Event) {
  const v = (e.target as HTMLInputElement).value.trim();
  const name = field === "name" ? v : r.name;
  const description = field === "description" ? v : r.description;
  if (name === r.name && description === r.description) return;
  const old = r.raw && typeof r.raw === "object" ? { ...(r.raw as Record<string, unknown>) } : {};
  let value: unknown;
  if (description || (old.description && typeof old.description === "object")) {
    const desc = old.description && typeof old.description === "object"
      ? { ...(old.description as Record<string, string>), ru: description }
      : description;
    value = { ...old, name, description: desc || undefined };
  } else {
    value = Object.keys(old).some((k) => k !== "name" && k !== "description") ? { ...old, name } : name;
  }
  apply([{ op: "set", path: [...props.path, "values", r.key], value }]);
}

function add() {
  const k = nextFreeKey(props.values);
  if (!props.values) apply([{ op: "set", path: [...props.path, "values"], value: { [k]: `VALUE_${k}` } }]);
  else apply([{ op: "set", path: [...props.path, "values", String(k)], value: `VALUE_${k}` }]);
}

function remove(r: Row) {
  if (rows.value.length === 1) apply([{ op: "remove", path: [...props.path, "values"] }]);
  else apply([{ op: "remove", path: [...props.path, "values", r.key] }]);
}
</script>

<template>
  <section class="subtable">
    <header>
      <h4>{{ title ?? t("Значения") }}</h4>
      <button v-if="!readonly" class="small" @click="add">{{ t("+ Значение") }}</button>
    </header>
    <table v-if="rows.length">
      <thead><tr><th class="num">{{ t("Значение") }}</th><th>{{ t("Имя") }}</th><th>{{ t("Описание") }}</th><th v-if="!readonly"></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.key" :class="rowDiags(r)[0]?.level">
          <td class="num"><input class="mono" :value="fmt(r.num)" :readonly="readonly" @change="setValue(r, $event)" /></td>
          <td>
            <input class="mono" :value="r.name" :readonly="readonly" @change="setEntry(r, 'name', $event)" />
            <div v-for="d in rowDiags(r)" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</div>
          </td>
          <td><input :value="r.description" :readonly="readonly" @change="setEntry(r, 'description', $event)" /></td>
          <td v-if="!readonly" class="act"><button class="icon" :title="t('Удалить')" @click="remove(r)">✕</button></td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">{{ t("Таблица значений пуста.") }}</p>
  </section>
</template>
