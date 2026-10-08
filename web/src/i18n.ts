// Интерфейс — только на английском. Строки в коде — русские и служат ключами; переводы — в locale/en.json.

import en from "./locale/en.json";

const EN = en as Record<string, string>;

/** Перевести строку; {name} заменяются значениями из params. */
export function t(key: string, params?: Record<string, unknown>): string {
  const s = EN[key] ?? key;
  return params ? s.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : s;
}

/** Пометить строку для перевода без перевода сейчас (статические таблицы; переводится через t при выводе). */
export const N_ = (key: string): string => key;

/** Языки документов: выбираются при создании карты и при экспорте (интерфейс от них не зависит). */
export const DOC_LANGUAGES: Array<[string, string]> = [["ru", N_("русский")], ["en", N_("английский")]];

/** Языки экспорта: русский, английский и язык карты (любой код ISO 639-1), если он другой. */
export function docLanguages(mapLang?: string | null): Array<[string, string]> {
  return mapLang && !DOC_LANGUAGES.some(([c]) => c === mapLang) ? [...DOC_LANGUAGES, [mapLang, mapLang]] : DOC_LANGUAGES;
}
