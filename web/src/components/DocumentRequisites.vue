<script setup lang="ts">
// Оформление и реквизиты документа: логотип, обозначение, подписи (основная надпись ЕСКД),
// «УТВЕРЖДАЮ» / «СОГЛАСОВАНО».
import { computed, ref } from "vue";
import { api } from "../api";
import type { FieldDef } from "../fields";
import { getAt, startsWith } from "../model";
import { actions, store, toast } from "../store";
import type { State } from "../types";
import FieldInput from "./FieldInput.vue";
import { N_, t } from "../i18n";

/* eslint-disable @typescript-eslint/no-explicit-any */
const doc = computed<any>(() => store.state?.data?.document ?? {});
const readonly = computed(() => !!store.state?.readonly);
const diags = computed(() => store.state?.diagnostics ?? []);

const MAIN: FieldDef[] = [
  { key: "designation", label: N_("Document designation"), type: "text", hint: N_("e.g. АБВГ.468332.001 Д1") },
  { key: "litera", label: N_("Letter"), type: "text", hint: N_("ESKD: Э, Т, О, О1, А…") },
  { key: "organization", label: N_("Organization"), type: "text" },
  { key: "city", label: N_("City"), type: "text", hint: N_("for the title page") },
];
const SIGNS: FieldDef[] = [
  { key: "signatures.developed", label: N_("Developed by"), type: "text" },
  { key: "signatures.checked", label: N_("Checked by"), type: "text" },
  { key: "signatures.tech_control", label: N_("Technical control"), type: "text" },
  { key: "signatures.norm_control", label: N_("Standards control"), type: "text" },
  { key: "signatures.approved", label: N_("Approved by"), type: "text" },
];
const APPROVE: FieldDef[] = [
  { key: "approve.position", label: N_("APPROVED: position"), type: "text" },
  { key: "approve.name", label: N_("APPROVED: full name"), type: "text" },
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
    toast(t("Logo uploaded"), "info");
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
  void actions.apply([{ op: "insert", path: ["document", "agree"], value: { position: t("Job title"), name: t("Initials and surname") } }]);
}
function removeAgree(i: number) {
  if (agree.value.length === 1) void actions.apply([{ op: "remove", path: ["document", "agree"] }]);
  else void actions.apply([{ op: "remove", path: ["document", "agree", i] }]);
}
</script>

<template>
  <section class="card">
    <h3>{{ t("Layout and document details") }} <span class="muted">{{ t("ESKD PDF template") }}</span></h3>

    <div class="logo-row">
      <div class="logo-box" :class="{ empty: !doc.logo }">
        <img v-if="doc.logo && !logoBroken" :src="logoUrl" :alt="t('Logo')" @error="logoBroken = true" />
        <span v-else-if="doc.logo" class="muted">{{ t("file not found") }}</span>
        <span v-else class="muted">{{ t("No logo set") }}</span>
      </div>
      <div class="logo-actions">
        <b>{{ t("Company logo") }}</b>
        <span class="muted">{{ t("PNG, JPG or SVG. Appears on the title page, in the ESKD title block, and in HTML and Excel output.") }}</span>
        <span v-if="doc.logo" class="mono muted">{{ doc.logo }}</span>
        <span v-for="d in logoDiags" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
        <div v-if="!readonly" class="row-actions">
          <button class="small" @click="fileInput?.click()">{{ doc.logo ? t("Replace…") : t("Upload…") }}</button>
          <button v-if="doc.logo" class="small" @click="removeLogo">{{ t("Delete") }}</button>
          <input ref="fileInput" type="file" accept=".png,.jpg,.jpeg,.svg,.gif,.webp" hidden @change="upload" />
        </div>
      </div>
    </div>

    <div class="form-grid">
      <FieldInput v-for="def in MAIN" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" @commit="commit(def, $event)" />
    </div>

    <h4 class="sub-h">{{ t("Title block and approval sheet signatures") }}</h4>
    <div class="form-grid sign-grid">
      <FieldInput v-for="def in SIGNS" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" :placeholder="t('Surname')" @commit="commit(def, $event)" />
    </div>

    <h4 class="sub-h">{{ t("Title page") }}</h4>
    <div class="form-grid">
      <FieldInput v-for="def in APPROVE" :key="def.key" :def="def" :value="value(def)" :diags="fieldDiags(def)"
                  :readonly="readonly" @commit="commit(def, $event)" />
    </div>
    <div class="subtable agree">
      <header>
        <span class="field-label">{{ t("AGREED") }}</span>
        <button v-if="!readonly" class="small" @click="addAgree">{{ t("+ Approver") }}</button>
      </header>
      <table v-if="agree.length">
        <thead><tr><th>{{ t("Job title") }}</th><th>{{ t("Initials and surname") }}</th><th v-if="!readonly"></th></tr></thead>
        <tbody>
          <tr v-for="(p, i) in agree" :key="i">
            <td><input :value="p.position ?? ''" :readonly="readonly" @change="setAgree(i, 'position', $event)" /></td>
            <td><input :value="p.name" :readonly="readonly" @change="setAgree(i, 'name', $event)" /></td>
            <td v-if="!readonly" class="act"><button class="icon" :title="t('Delete')" @click="removeAgree(i)">✕</button></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
