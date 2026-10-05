<script setup lang="ts">
// Экран, когда карта не открыта: создать, открыть, недавние, профиль.
import { actions, store } from "../store";
</script>

<template>
  <div class="start">
    <div class="start-card">
      <h1>canmap <span class="muted start-ver">{{ store.meta?.version }}</span></h1>
      <p class="muted">YAML-карта сигналов CAN: редактор, проверка, документы и код.</p>

      <div class="start-actions">
        <button class="primary" :disabled="store.meta?.readonly" @click="store.dialog = 'new'">Новая карта…</button>
        <button @click="store.dialog = 'open'">Открыть…</button>
      </div>

      <section v-if="store.meta?.recent.length">
        <h3>Недавние</h3>
        <ul class="start-recent">
          <li v-for="r in store.meta.recent" :key="r.path">
            <button class="link" :disabled="!r.exists" :title="r.path" @click="actions.openFile(r.path)">{{ r.name }}</button>
            <span class="muted mono">{{ r.exists ? r.dir : "не найден" }}</span>
          </li>
        </ul>
      </section>

      <section class="start-user">
        <template v-if="store.meta?.user.name">
          Вы работаете как <b>{{ store.meta.user.name }}</b>
          <a v-if="store.meta.user.github_url" :href="store.meta.user.github_url" target="_blank" rel="noopener">@{{ store.meta.user.github }}</a>.
          <button class="link" @click="store.dialog = 'profile'">Изменить</button>
        </template>
        <template v-else>
          Укажите своё имя и GitHub, чтобы изменения в истории карты были подписаны.
          <button class="small" @click="store.dialog = 'profile'">Заполнить профиль</button>
        </template>
      </section>
      <p class="muted start-hint">Ctrl+O — открыть, Ctrl+S — сохранить, Ctrl+Shift+S — сохранить как, Ctrl+Z / Ctrl+Y — отменить / повторить, Delete — удалить выбранный узел.</p>
    </div>
  </div>
</template>
