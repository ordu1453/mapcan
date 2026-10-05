<script setup lang="ts">
// Оформление и реквизиты документа: логотип, обозначение, подписи (основная надпись ЕСКД,
// листы утверждения ЕСПД, титул ГОСТ 7.32), «УТВЕРЖДАЮ» / «СОГЛАСОВАНО».
import { computed, ref } from "vue";
import { api } from "../api";
import type { FieldDef } from "../fields";
import { getAt, startsWith } from "../model";
import { actions, store, toast } from "../store";
import type { State } from "../types";
import FieldInput from "./FieldInput.vue";

/* eslint-disable @typescript-eslint/no-explicit-any */
const doc = computed<any>(() => store.state?.data?.document ?? {});
const readonly = computed(() => !!store.state?.readonly);
const diags = computed(() => store.state?.diagnostics ?? []);

const MAIN: FieldDef[] = [
  { key: "designation", label: "Обозначение документа", type: "text", hint: "напр. АБВГ.468332.001 Д1 или RU.12345678.00001-01" },
  { key: "litera", label: "Литера", type: "text", hint: "ЕСКД: Э, Т, О, О1, А…" },
  { key: "organization", label: "Организация", type: "text" },
  { key: "city", label: "Город", type: "text", hint: "для титульного листа" },
];
const SIGNS: FieldDef[] = [
  { key: "signatures.developed", label: "Разраб.", type: "text" },
  { key: "signatures.checked", label: "Пров.", type: "text" },
  { key: "signatures.tech_control", label: "Т. контр.", type: "text" },
  { key: "signatures.norm_control", label: "Н. контр.", type: "text" },
  { key: "signatures.approved", label: "Утв.", type: "text" },
];
const APPROVE: FieldDef[] = [
  { key: "approve.position", label: "УТВЕРЖДАЮ: должность", type: "text" },
  { key: "approve.name", label: "УТВЕРЖДАЮ: И. О. Фамилия", type: "text" },
];

const value = (def: FieldDef) => getAt(doc.value, def.key.split("."));
const fieldDiags = (def: FieldDef) =>
  diags.value.filter((d) => startsWith(d.node, ["document", ...def.key.split(".")]));

function commit(def: FieldDef, v: unknown) {
  const parts = def.key.split(".");
  const ops: any[] = [{ op: "set", path: ["document", ...parts], value: v }];
  // Пустая группа (signatures / approve) удаляется целиком, чтобы не оставлять «approve: {}».
  if (parts.length === 2 && (v === null || v === "")) {
    const group = { ...(doc.value[parts[0]] ?? {}) };
    delete group[parts[1]];
    if (!Object.values(group).some((x) => x !== null && x !== "")) {
      ops.splice(0, 1, { op: "set", path: ["document", parts[0]], value: null });
    }
  }
  void actions.apply(ops);
}

// ------------------------------------------------------------------ логотип

const fileInput = ref<HTMLInputElement | null>(null);
const logoBroken = ref(false);
const logoUrl = computed(() => (doc.value.logo ? api.logoUrl(store.state?.version ?? 0) : ""));
const logoDiags = computed(() => diags.value.filter((d) => startsWith(d.node, ["document", "logo"])));

async function upload(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0];
  if (!f) return;
  try {
    const st: State = await api.uploadLogo(f);
    store.state = st;
    logoBroken.value = false;
    toast("Логотип загружен", "info");
  } catch (err) {
    toast(err instanceof Error ? err.message : String(err));
  } finally {
    if (fileInput.value) fileInput.value.value = "";
  }
}

function removeLogo() {
  void actions.apply([{ op: "set", path: ["document", "logo"], value: null }]);
}

// ------------------------------------------------------------------ СОГЛАСОВАНО

const agree = computed<any[]>(() => doc.value.agree ?? []);

function setAgree(i: number, key: "position" | "name", e: Event) {
  const v = (e.target as HTMLInputElement).value.trim();
  if (key === "name" && !v) return;
  void actions.apply([{ op: "set", path: ["document", "agree", i, key], value: v || null }]);
}
function addAgree() {
  void actions.apply([{ op: "insert", path: ["document", "agree"], value: { position: "Должность", name: "И. О. Фамилия" } }]);
}
function removeAgree(i: number) {
  if (agree.value.length === 1) void actions.apply([{ op: "remove", path: ["document", "agree"] }]);
  else void actions.apply([{ op: "remove", path: ["document", "agree", i] }]);
}
</script>

<template>
  <section class="card">
    <h3>Оформление и реквизиты <span class="muted">шаблоны PDF: ЕСКД, ЕСПД, ГОСТ 7.32</span></h3>

    <div class="logo-row">
      <div class="logo-box" :class="{ empty: !doc.logo }">
        <img v-if="doc.logo && !logoBroken" :src="logoUrl" alt="Логотип" @error="logoBroken = true" />
        <span v-else-if="doc.logo" class="muted">файл не найден</span>
        <span v-else class="muted">Логотип не задан</span>
      </div>
      <div class="logo-actions">
        <b>Логотип предприятия</b>
        <span class="muted">PNG, JPG или SVG. Выводится на титульном листе, в основной надписи ЕСКД, в HTML и Excel.</span>
        <span v-if="doc.logo" class="mono muted">{{ doc.logo }}</span>
        <span v-for="d in logoDiags" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
        <div v-if="!readonly" class="row-actions">
          <button class="small" @click="fileInput?.click()">{{ doc.logo ? "Заменить…" : "Загрузить…" }}</button>
          <button v-if="doc.logo" class="small" @click="removeLogo">Убрать</button>
          <input ref="fileInput" type="file" accept=".png,.jpg,.jpeg,.svg,.gif,.webp" hidden @change="upload" />
        </div>
      </div>
    </div>

    <div class="form-grid">
      <FieldInput v-for="def in MAIN" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" @commit="commit(def, $event)" />
    </div>

    <h4 class="sub-h">Подписи основной надписи и листов утверждения</h4>
    <div class="form-grid sign-grid">
      <FieldInput v-for="def in SIGNS" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" placeholder="Фамилия" @commit="commit(def, $event)" />
    </div>

    <h4 class="sub-h">Титульный лист</h4>
    <div class="form-grid">
      <FieldInput v-for="def in APPROVE" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" @commit="commit(def, $event)" />
    </div>
    <div class="subtable agree">
      <header>
        <span class="field-label">СОГЛАСОВАНО</span>
        <button v-if="!readonly" class="small" @click="addAgree">+ согласующий</button>
      </header>
      <table v-if="agree.length">
        <thead><tr><th>Должность</th><th>И. О. Фамилия</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="(p, i) in agree" :key="i">
            <td><input :value="p.position ?? ''" :readonly="readonly" @change="setAgree(i, 'position', $event)" /></td>
            <td><input :value="p.name" :readonly="readonly" @change="setAgree(i, 'name', $event)" /></td>
            <td v-if="!readonly" class="act"><button class="icon" title="Удалить" @click="removeAgree(i)">✕</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
