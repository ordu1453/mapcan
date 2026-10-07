<script setup lang="ts">
// Журнал версий карты в git: коммиты с этим файлом и их теги; сравнение с текущей картой и открытие версии.
import { onMounted, ref } from "vue";
import { api } from "../api";
import { actions, store } from "../store";
import type { GitRevs } from "../types";
import Modal from "./Modal.vue";
import { t } from "../i18n";

const emit = defineEmits<{ close: []; compare: [rev: string] }>();

const revs = ref<GitRevs | null>(null);
const error = ref("");

onMounted(async () => {
  try {
    revs.value = await api.gitRevs();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
});

async function open(rev: string) {
  if (await actions.restoreRevision(rev)) emit("close");
}
</script>

<template>
  <Modal :title="t('Журнал версий')" wide @close="emit('close')">
    <p v-if="error" class="banner error">{{ error }}</p>
    <p v-else-if="!revs" class="muted">{{ t("Загрузка…") }}</p>
    <p v-else-if="!revs.available" class="banner info">{{ t("Файл карты ещё не закоммичен в git — версий нет.") }}</p>
    <template v-else>
      <p class="muted">
        {{ t("Коммиты, в которых менялась карта (последние {n}). «Открыть» загружает версию в редактор как несохранённую правку.", { n: revs.commits.length }) }}
      </p>
      <table class="git-log">
        <tbody>
          <tr v-for="c in revs.commits" :key="c.rev">
            <td class="mono muted">{{ c.rev }}</td>
            <td class="muted nowrap">{{ c.date }}</td>
            <td class="git-log-subject" :title="c.subject">
              <span v-for="tg in c.tags" :key="tg" class="badge mono">{{ tg }}</span> {{ c.subject }}
              <div class="muted">{{ c.author }}</div>
            </td>
            <td class="nowrap">
              <button @click="emit('compare', c.rev)">{{ t("Сравнить") }}</button>
              <button v-if="!store.state?.readonly" :disabled="store.busy" @click="open(c.rev)">{{ t("Открыть") }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </template>
    <div class="fd-actions">
      <span class="spacer" />
      <button @click="emit('close')">{{ t("Закрыть") }}</button>
    </div>
  </Modal>
</template>
