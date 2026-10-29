// The interface is in English only. Strings are written in English in the code; the English text is also
// the key of the Russian translation in locale/ru.json (of this package for its strings, of each editor for
// the rest), which tests keep complete.

/** Interface string with {name} placeholders filled from params. */
export function t(key: string, params?: Record<string, unknown>): string {
  return params ? key.replace(/\{(\w+)\}/g, (m, k: string) => (k in params ? String(params[k]) : m)) : key;
}

/** Mark a string for translation without formatting it now (static tables; shown through t later). */
export const N_ = (key: string): string => key;
