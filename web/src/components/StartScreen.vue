<script setup lang="ts">
// Экран, когда карта не открыта: создать, открыть, недавние, профиль.
import { actions, store } from "../store";
import { t } from "../i18n";
import BrandMark from "./BrandMark.vue";
</script>

<template>
  <div class="start">
    <div class="start-card">
      <h1><BrandMark :size="28" /> <span class="muted start-ver">{{ store.meta?.version }}</span></h1>
      <p class="muted">{{ t("YAML-карта сигналов CAN: редактор, проверка, документы и код.") }}</p>

      <div class="start-actions">
        <button class="primary" :disabled="store.meta?.readonly" @click="store.dialog = 'new'">{{ t("Новая карта…") }}</button>
        <button @click="store.dialog = 'open'">{{ t("Открыть…") }}</button>
      </div>

      <section v-if="store.meta?.recent.length">
        <h3>{{ t("Недавние") }}</h3>
        <ul class="start-recent">
          <li v-for="r in store.meta.recent" :key="r.path">
            <button class="link" :disabled="!r.exists" :title="r.path" @click="actions.openFile(r.path)">{{ r.name }}</button>
            <span class="muted mono">{{ r.exists ? r.dir : t("не найден") }}</span>
          </li>
        </ul>
      </section>

      <section class="start-user">
        <template v-if="store.meta?.user.name">
          {{ t("Вы работаете как") }} <b>{{ store.meta.user.name }}</b>
          <a v-if="store.meta.user.github_url" :href="store.meta.user.github_url" target="_blank" rel="noopener">@{{ store.meta.user.github }}</a>.
          <button class="link" @click="store.dialog = 'profile'">{{ t("Изменить") }}</button>
        </template>
        <template v-else>
          {{ t("Укажите своё имя и GitHub, чтобы изменения в истории карты были подписаны.") }}
          <button class="small" @click="store.dialog = 'profile'">{{ t("Заполнить профиль") }}</button>
        </template>
      </section>
      <p class="muted start-hint">{{ t("Ctrl+O — открыть, Ctrl+S — сохранить, Ctrl+Shift+S — сохранить как, Ctrl+Z / Ctrl+Y — отменить / повторить, Delete — удалить выбранный узел.") }}</p>
    </div>
  </div>
</template>
