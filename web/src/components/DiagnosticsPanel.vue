<script setup lang="ts">
import { computed, ref } from "vue";
import { ownerPath } from "../model";
import { actions, store } from "../store";
import type { Diagnostic, Level } from "../types";
import { t } from "../i18n";

const open = ref(true);
const show = ref<Record<Level, boolean>>({ error: true, warning: true, info: false });

const all = computed(() => store.state?.diagnostics ?? []);
const counts = computed(() => ({
  error: all.value.filter((d) => d.level === "error").length,
  warning: all.value.filter((d) => d.level === "warning").length,
  info: all.value.filter((d) => d.level === "info").length,
}));
const items = computed(() => all.value.filter((d) => show.value[d.level]));

function go(d: Diagnostic) {
  if (!store.state?.data || !d.node.length) store.tab = "yaml";
  if (store.tab === "yaml") store.revealLine = d.line;
  if (d.node.length && store.state?.data) {
    actions.select(ownerPath(d.node));
    store.focusPath = d.node;
    // Сообщение не на поле формы (на узел или таблицу) — не держим цель, чтобы она не сработала позже
    setTimeout(() => { if (store.focusPath === d.node) store.focusPath = null; }, 500);
  }
}
</script>

<template>
  <section class="diag-panel" :class="{ closed: !open }">
    <header @click="open = !open">
      <span class="twisty">{{ open ? "▾" : "▸" }}</span>
      <b>{{ t("Проверка") }}</b>
      <span v-for="lvl in (['error', 'warning', 'info'] as Level[])" :key="lvl" class="chip" :class="[lvl, { off: !show[lvl] }]"
            @click.stop="show[lvl] = !show[lvl]">
        {{ { error: t("ошибки"), warning: t("предупреждения"), info: t("замечания") }[lvl] }}: {{ counts[lvl] }}
      </span>
      <span v-if="!counts.error && !counts.warning" class="ok">{{ t("✓ карта корректна") }}</span>
    </header>
    <ul v-if="open">
      <li v-for="(d, i) in items" :key="i" :class="d.level" @click="go(d)">
        <span class="lvl">{{ d.level === "error" ? "✖" : d.level === "warning" ? "▲" : "i" }}</span>
        <span class="mono loc">{{ d.line ? t("стр. {line}", { line: d.line }) : "" }}</span>
        <span class="mono code">{{ d.code }}</span>
        <span class="msg">{{ d.message }}</span>
        <span class="mono path muted">{{ d.path }}</span>
      </li>
      <li v-if="!items.length" class="muted empty">{{ t("Нет сообщений выбранных уровней.") }}</li>
    </ul>
  </section>
</template>
