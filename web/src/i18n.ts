// Язык интерфейса. Строки в коде — русские и служат ключами; английские переводы — в locale/en.json.
// Язык выбирается при первом запуске и хранится в настройках пользователя на сервере (общих с CLI).

import { reactive } from "vue";
import en from "./locale/en.json";

export type Lang = "en" | "ru";

export const LANGUAGES: Array<[Lang, string]> = [["en", "English"], ["ru", "Русский"]];

export const i18n = reactive({ lang: "en" as Lang });

const EN = en as Record<string, string>;

/** Перевести строку; {name} заменяются значениями из params. */
export function t(key: string, params?: Record<string, unknown>): string {
  const s = i18n.lang === "ru" ? key : EN[key] ?? key;
  return params ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : s;
}

/** Пометить строку для перевода без перевода сейчас (статические таблицы; переводится через t при выводе). */
export const N_ = (key: string): string => key;

export function setLang(lang: string | undefined | null): void {
  i18n.lang = lang === "ru" ? "ru" : "en";
  document.documentElement.lang = i18n.lang;
  document.title = t("mapcan — редактор карты");
}
