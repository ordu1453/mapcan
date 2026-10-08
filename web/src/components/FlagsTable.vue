<script setup lang="ts">
// Flags of a bit field: bit, length, name, description.
import { actions } from "../store";
import { parseInteger } from "../form/input";
import { addFlag } from "../edit";
import { startsWith, txt } from "../model";
import type { Diagnostic, Path } from "../types";
import { t } from "../i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
const props = defineProps<{
  path: Path;                // path of the signal
  flags: any[] | undefined;
  readonly?: boolean;
  diags: Diagnostic[];
}>();

function rowDiags(i: number) {
  return props.diags.filter((d) => startsWith(d.node, [...props.path, "flags", i]));
}

function setInt(i: number, key: string, e: Event) {
  const el = e.target as HTMLInputElement;
  const s = el.value.trim();
  let n: number | null = null;
  try {
    n = s === "" ? null : parseInteger(s);
    if (n !== null && (key === "bit_length" ? n < 1 || n > 64 : n < 0 || n > 63)) throw new Error();
  } catch {
    el.value = String(props.flags?.[i]?.[key] ?? "");
    return;
  }
  if (key === "bit_length" && n === 1) {
    void actions.apply([{ op: "set", path: [...props.path, "flags", i, key], value: null }]);
    return;
  }
  void actions.apply([{ op: "set", path: [...props.path, "flags", i, key], value: n }]);
}

function setText(i: number, key: string, e: Event) {
  const v = (e.target as HTMLInputElement).value.trim();
  const old = props.flags?.[i]?.[key];
  if (key === "description" && old && typeof old === "object") {
    void actions.apply([{ op: "set", path: [...props.path, "flags", i, key], value: { ...old, ru: v } }]);
  } else {
    void actions.apply([{ op: "set", path: [...props.path, "flags", i, key], value: v || null }]);
  }
}

function remove(i: number) {
  if ((props.flags?.length ?? 0) === 1) void actions.apply([{ op: "remove", path: [...props.path, "flags"] }]);
  else void actions.apply([{ op: "remove", path: [...props.path, "flags", i] }]);
}
</script>

<template>
  <section class="subtable">
    <header>
      <h4>{{ t("Bit field flags") }}</h4>
      <button v-if="!readonly" class="small" @click="addFlag(path)">{{ t("+ Flag") }}</button>
    </header>
    <table v-if="flags?.length">
      <thead><tr><th class="num">{{ t("Bit") }}</th><th class="num">{{ t("Length") }}</th><th>{{ t("Name") }}</th><th>{{ t("Description") }}</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(f, i) in flags" :key="i" :class="rowDiags(i)[0]?.level">
          <td class="num"><input class="mono" :value="f.bit" :readonly="readonly" @change="setInt(i, 'bit', $event)" /></td>
          <td class="num"><input class="mono" :value="f.bit_length ?? 1" :readonly="readonly" @change="setInt(i, 'bit_length', $event)" /></td>
          <td>
            <input class="mono" :value="f.name" :readonly="readonly" @change="setText(i, 'name', $event)" />
            <div v-for="d in rowDiags(i)" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</div>
          </td>
          <td><input :value="txt(f.description)" :readonly="readonly" @change="setText(i, 'description', $event)" /></td>
          <td class="act">
            <button class="icon" :title="t('Open')" @click="actions.select([...path, 'flags', i])">›</button>
            <button v-if="!readonly" class="icon" :title="t('Delete')" @click="remove(i)">✕</button>
          </td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted">{{ t("No flags.") }}</p>
  </section>
</template>
