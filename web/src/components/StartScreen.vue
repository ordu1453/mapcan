<script setup lang="ts">
// Экран, когда карта не открыта: создать, открыть, несколько недавних, примеры.
import { computed } from "vue";
import { actions, store } from "../store";
import { t } from "../i18n";
import BrandMark from "./BrandMark.vue";

const RECENT_LIMIT = 3;
const recent = computed(() => (store.meta?.recent ?? []).filter((r) => r.exists).slice(0, RECENT_LIMIT));
const examples = computed(() => (store.meta?.readonly ? [] : store.meta?.examples ?? []));

function openExample(name: string) {
  store.example = name;
  store.dialog = "example";
}
</script>

<template>
  <div class="start">
    <div class="start-card">
      <h1><BrandMark :size="28" /></h1>

      <div class="start-actions">
        <button class="primary" :disabled="store.meta?.readonly" @click="store.dialog = 'new'">{{ t("New map…") }}</button>
        <button @click="store.dialog = 'open'">{{ t("Open…") }}</button>
      </div>

      <section v-if="recent.length">
        <h3>{{ t("Recent") }}</h3>
        <ul class="start-recent">
          <li v-for="r in recent" :key="r.path">
            <button class="link" :title="r.path" @click="actions.openFile(r.path)">{{ r.name }}</button>
          </li>
        </ul>
      </section>

      <section v-if="examples.length">
        <h3>{{ t("Examples") }}</h3>
        <ul class="start-recent">
          <li v-for="e in examples" :key="e.name">
            <button class="link" :title="t('Save a copy and open it')" @click="openExample(e.name)">{{ e.title }}</button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
