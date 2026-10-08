// The interface is in English only. Strings are written in English in the code; the English text is also
// the key of the Russian translation in locale/ru.json, which tests keep complete.

/** Interface string with {name} placeholders filled from params. */
export function t(key: string, params?: Record<string, unknown>): string {
  return params ? key.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : key;
}

/** Mark a string for translation without formatting it now (static tables; shown through t later). */
export const N_ = (key: string): string => key;

/** Document languages: chosen when creating a map and on export (the interface does not depend on them). */
export const DOC_LANGUAGES: Array<[string, string]> = [["ru", N_("Russian")], ["en", N_("English")]];

/** Export languages: Russian, English and the map's language (any ISO 639-1 code) if it is another one. */
export function docLanguages(mapLang?: string | null): Array<[string, string]> {
  return mapLang && !DOC_LANGUAGES.some(([c]) => c === mapLang) ? [...DOC_LANGUAGES, [mapLang, mapLang]] : DOC_LANGUAGES;
}
