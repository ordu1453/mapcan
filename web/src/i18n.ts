// The interface is in English only. Strings are written in English in the code; the English text is also
// the key of the Russian translation in locale/ru.json, which tests keep complete.

/** Interface string with {name} placeholders filled from params. */
export function t(key: string, params?: Record<string, unknown>): string {
  return params ? key.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : key;
}

/** Mark a string for translation without formatting it now (static tables; shown through t later). */
export const N_ = (key: string): string => key;

/** Языки документов: выбираются при создании карты и при экспорте (интерфейс от них не зависит). */
export const DOC_LANGUAGES: Array<[string, string]> = [["ru", N_("Russian")], ["en", N_("English")]];

/** Языки экспорта: русский, английский и язык карты (любой код ISO 639-1), если он другой. */
export function docLanguages(mapLang?: string | null): Array<[string, string]> {
  return mapLang && !DOC_LANGUAGES.some(([c]) => c === mapLang) ? [...DOC_LANGUAGES, [mapLang, mapLang]] : DOC_LANGUAGES;
}
