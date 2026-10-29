<script setup lang="ts">
// Flags of a bit field: bit, length, name, description. Flags ticked in the first column move together by a bit (#150).
import { computed, ref, watch } from "vue";
import { actions, toast } from "../store";
import { parseInteger } from "@mapcan/forms";
import { addFlag } from "../edit";
import { pathKey, shiftedFlags, startsWith, txt } from "../model";
import type { Diagnostic, Path } from "../types";
import { t } from "../i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
const props = defineProps<{
  path: Path;                // path of the signal
  flags: any[] | undefined;
  readonly?: boolean;
  diags: Diagnostic[];
  /** Length of the field, bits (null: not known, the flags are not shifted). */
  fieldLength?: number | null;
}>();

const picked = ref(new Set<number>());
watch(() => pathKey(props.path), () => { picked.value = new Set(); });
const count = computed(() => props.flags?.length ?? 0);
const allPicked = computed(() => count.value > 0 && picked.value.size === count.value);

function pick(i: number, on: boolean) {
  const s = new Set(picked.value);
  if (on) s.add(i);
  else s.delete(i);
  picked.value = s;
}

function pickAll(on: boolean) {
  picked.value = new Set(on ? Array.from({ length: count.value }, (_, i) => i) : []);
}

/** Move the ticked flags by `delta` bits, all in one step; nothing moves if one would not fit. */
function shift(delta: number) {
  const which = [...picked.value].filter((i) => i < count.value).sort((a, b) => a - b);
  if (!which.length || props.fieldLength == null) return;
  const bits = shiftedFlags(props.flags ?? [], which, delta, props.fieldLength);
  if (!bits) {
    toast(t("The flags do not move: one would leave the field or land on another flag"));
    return;
  }
  void actions.apply(which.map((i, k) => ({ op: "set" as const, path: [...props.path, "flags", i, "bit"], value: bits[k] })));
}

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
      <span v-if="!readonly && fieldLength != null && flags?.length" class="flag-shift">
        <span class="muted">{{ t("Shift the ticked flags:") }}</span>
        <button class="small" :disabled="!picked.size" :title="t('One bit lower')" @click="shift(-1)">{{ t("bit −1") }}</button>
        <button class="small" :disabled="!picked.size" :title="t('One bit higher')" @click="shift(1)">{{ t("bit +1") }}</button>
      </span>
      <button v-if="!readonly" class="small" @click="addFlag(path)">{{ t("+ Field") }}</button>
    </header>
    <table v-if="flags?.length">
      <thead><tr><th v-if="!readonly" class="pick"><input type="checkbox" :checked="allPicked" :aria-label="t('Tick all flags')"
                                                          @change="pickAll(($event.target as HTMLInputElement).checked)" /></th>
        <th class="num">{{ t("Bit") }}</th><th class="num">{{ t("Length") }}</th><th>{{ t("Name") }}</th><th>{{ t("Description") }}</th><th></th></tr></thead>
      <tbody>
        <tr v-for="(f, i) in flags" :key="i" :class="rowDiags(i)[0]?.level">
          <td v-if="!readonly" class="pick"><input type="checkbox" :checked="picked.has(i)" :aria-label="t('Tick flag {name}', { name: f.name })"
                                                   @change="pick(i, ($event.target as HTMLInputElement).checked)" /></td>
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
