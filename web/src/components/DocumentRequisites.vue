<script setup lang="ts">
// Styling and requisites of the document: logo, designation, signatures (the ESKD title block),
// "APPROVED" / "AGREED". All of them but the organization are print details, in document.print.
import { computed, ref } from "vue";
import { api } from "../api";
import type { FieldDef } from "../form/spec";
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
  { key: "print.designation", label: N_("Document designation"), type: "text", hint: N_("e.g. АБВГ.468332.001 Д1") },
  { key: "print.litera", label: N_("Letter"), type: "text", hint: N_("ESKD: Э, Т, О, О1, А…") },
  { key: "organization", label: N_("Organization"), type: "text" },
  { key: "print.city", label: N_("City"), type: "text", hint: N_("for the title page") },
];
const SIGNS: FieldDef[] = [
  { key: "print.signatures.developed", label: N_("Developed by"), type: "text" },
  { key: "print.signatures.checked", label: N_("Checked by"), type: "text" },
  { key: "print.signatures.tech_control", label: N_("Technical control"), type: "text" },
  { key: "print.signatures.norm_control", label: N_("Standards control"), type: "text" },
  { key: "print.signatures.approved", label: N_("Approved by"), type: "text" },
];
const APPROVE: FieldDef[] = [
  { key: "print.approve.position", label: N_("APPROVED: position"), type: "text" },
  { key: "print.approve.name", label: N_("APPROVED: full name"), type: "text" },
];

const value = (def: FieldDef) => getAt(doc.value, def.key.split("."));
const fieldDiags = (def: FieldDef) =>
  diags.value.filter((d) => startsWith(d.node, ["document", ...def.key.split(".")]));

const present = (x: unknown) => x !== null && x !== undefined && x !== "";

/** The key at ``parts`` of the document cleared: a group left empty (signatures, approve, print) is removed as a
 * whole, so as not to leave "approve: {}". */
function clearOp(parts: (string | number)[]): any {
  let path = parts;
  for (let d = parts.length - 1; d >= 1; d--) {
    const group = { ...(getAt(doc.value, parts.slice(0, d)) ?? {}) };
    delete group[parts[d]];
    if (Object.values(group).some(present)) break;
    path = parts.slice(0, d);
  }
  return { op: "set", path: ["document", ...path], value: null };
}

function commit(def: FieldDef, v: unknown) {
  const parts = def.key.split(".");
  void actions.apply([present(v) ? { op: "set", path: ["document", ...parts], value: v } : clearOp(parts)]);
}

// ------------------------------------------------------------------ logo

const fileInput = ref<HTMLInputElement | null>(null);
const logoBroken = ref(false);
const logo = computed<string | undefined>(() => doc.value.print?.logo);
const logoUrl = computed(() => (logo.value ? api.logoUrl(store.state?.version ?? 0) : ""));
const logoDiags = computed(() => diags.value.filter((d) => startsWith(d.node, ["document", "print", "logo"])));

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
  void actions.apply([clearOp(["print", "logo"])]);
}

// ------------------------------------------------------------------ AGREED

const agree = computed<any[]>(() => doc.value.print?.agree ?? []);

function setAgree(i: number, key: "position" | "name", e: Event) {
  const v = (e.target as HTMLInputElement).value.trim();
  if (key === "name" && !v) return;
  void actions.apply([{ op: "set", path: ["document", "print", "agree", i, key], value: v || null }]);
}
function addAgree() {
  void actions.apply([{ op: "insert", path: ["document", "print", "agree"], value: { position: t("Job title"), name: t("Initials and surname") } }]);
}
function removeAgree(i: number) {
  if (agree.value.length === 1) void actions.apply([clearOp(["print", "agree"])]);
  else void actions.apply([{ op: "remove", path: ["document", "print", "agree", i] }]);
}
</script>

<template>
  <section class="card">
    <h3>{{ t("Layout and document details") }} <span class="muted">{{ t("ESKD PDF template") }}</span></h3>

    <div class="logo-row">
      <div class="logo-box" :class="{ empty: !logo }">
        <img v-if="logo && !logoBroken" :src="logoUrl" :alt="t('Logo')" @error="logoBroken = true" />
        <span v-else-if="logo" class="muted">{{ t("file not found") }}</span>
        <span v-else class="muted">{{ t("No logo set") }}</span>
      </div>
      <div class="logo-actions">
        <b>{{ t("Company logo") }}</b>
        <span class="muted">{{ t("PNG, JPG or SVG. Appears on the title page, in the ESKD title block, and in HTML and Excel output.") }}</span>
        <span v-if="logo" class="mono muted">{{ logo }}</span>
        <span v-for="d in logoDiags" :key="d.message" class="field-msg" :class="d.level">{{ d.message }}</span>
        <div v-if="!readonly" class="row-actions">
          <button class="small" @click="fileInput?.click()">{{ logo ? t("Replace…") : t("Upload…") }}</button>
          <button v-if="logo" class="small" @click="removeLogo">{{ t("Delete") }}</button>
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
