// The interface is in English only. Strings are written in English in the code; the English text is also
// the key of the Russian translation in locale/ru.json (strings of the forms: in packages/forms), which tests
// keep complete. t and N_ are those of the shared forms.

import { N_ } from "@mapcan/forms";

export { N_, t } from "@mapcan/forms";

/** Document languages: chosen when creating a map and on export (the interface does not depend on them). */
export const DOC_LANGUAGES: Array<[string, string]> = [["ru", N_("Russian")], ["en", N_("English")]];

/** Export languages: Russian, English and the map's language (any ISO 639-1 code) if it is another one. */
export function docLanguages(mapLang?: string | null): Array<[string, string]> {
  return mapLang && !DOC_LANGUAGES.some(([c]) => c === mapLang) ? [...DOC_LANGUAGES, [mapLang, mapLang]] : DOC_LANGUAGES;
}
