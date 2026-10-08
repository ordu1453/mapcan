// Подсказки во вкладке YAML: ключи и значения по JSON Schema формата (GET /api/schema).
// Место курсора определяется по отступам текста, без полного разбора: подсказки работают
// и в черновике с синтаксической ошибкой.
import type { TextEdit } from "./yamltext";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Schema = Record<string, any>;

export interface Completion {
  label: string;
  detail: string;          // тип значения, «required»
  doc: string;             // описание поля из схемы
  edit: TextEdit;
  /** После вставки сразу показать подсказки следующего уровня (поля объекта, значения перечисления). */
  chain: boolean;
}

export interface CompletionList {
  items: Completion[];
  line: number;            // строка (с 0) и столбец начала заменяемого слова — для позиции списка
  col: number;
}

const ITEM = "[]";         // элемент списка в пути

interface LineInfo {
  indent: number;
  dashes: number[];        // столбцы маркеров «- » в начале строки
  keyCol: number;          // столбец после маркеров
  key: string | null;
  rest: string;            // текст после «ключ:» (или после маркеров, если ключа нет)
}

const KEY_RE = /^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s#'"{[\]-][^#:]*?|-[^\s#][^#:]*?)\s*:(?=\s|$)/;

function unquote(raw: string): string {
  if (raw.startsWith('"')) {
    try { return JSON.parse(raw) as string; } catch { return raw.slice(1, -1); }
  }
  return raw.startsWith("'") ? raw.slice(1, -1).replace(/''/g, "'") : raw;
}

function info(l: string): LineInfo {
  let i = 0;
  while (l[i] === " ") i++;
  const indent = i;
  const dashes: number[] = [];
  while (l[i] === "-" && (l[i + 1] === " " || i + 1 === l.length)) {
    dashes.push(i++);
    while (l[i] === " ") i++;
  }
  const m = KEY_RE.exec(l.slice(i));
  return { indent, dashes, keyCol: i, key: m ? unquote(m[1]) : null, rest: m ? l.slice(i + m[0].length) : l.slice(i) };
}

const isContent = (l: string) => /^\s*[^\s#]/.test(l);
const hasValue = (rest: string) => /^\s*[^\s#]/.test(rest);

/**
 * Путь к отображению, в котором ключ строки `line` начинается со столбца `col`: ключи и ITEM для элементов
 * списков; null — место не внутри отображения (текст многострочного значения и т. п.).
 */
export function contextPath(lines: string[], line: number, col: number): string[] | null {
  const path: string[] = [];
  let c = col;
  let afterItem = false;   // только что вышли из элемента: «key:» на том же столбце — список без отступа
  const dashes = (inf: LineInfo) => {
    for (let k = inf.dashes.length - 1; k >= 0; k--) {
      if (inf.dashes[k] < c) {
        path.push(ITEM);
        c = inf.dashes[k];
        afterItem = true;
      }
    }
  };
  dashes(info(lines[line].slice(0, col)));
  for (let j = line - 1; j >= 0 && (c > 0 || afterItem); j--) {
    if (!isContent(lines[j])) continue;
    const inf = info(lines[j]);
    if (inf.key !== null && (inf.keyCol < c || (afterItem && inf.keyCol === c && !inf.dashes.length))) {
      if (hasValue(inf.rest)) return null;
      path.push(inf.key);
      c = inf.keyCol;
      afterItem = false;
    } else if (inf.indent < c && inf.key === null && !inf.dashes.length) {
      return null;
    }
    dashes(inf);
  }
  return path.reverse();
}

// ------------------------------------------------------------------ схема

function deref(s: Schema | undefined, root: Schema): Schema | undefined {
  while (s?.$ref) s = root.$defs?.[String(s.$ref).split("/").pop()!];
  return s;
}

function variants(s: Schema | undefined, root: Schema): Schema[] {
  const d = deref(s, root);
  if (!d) return [];
  return d.anyOf ? d.anyOf.flatMap((v: Schema) => variants(v, root)) : [d];
}

const objectOf = (s: Schema | undefined, root: Schema) =>
  variants(s, root).find((v) => v.properties || typeof v.additionalProperties === "object");

/** Схема значения по пути (ключи и ITEM) или undefined, если путь не из формата. */
export function schemaAt(root: Schema, path: string[]): Schema | undefined {
  let s: Schema | undefined = root;
  for (const seg of path) {
    if (seg === ITEM) {
      s = variants(s, root).find((v) => v.items)?.items;
    } else {
      const o = objectOf(s, root);
      s = o?.properties?.[seg] ?? (typeof o?.additionalProperties === "object" ? o.additionalProperties : undefined);
    }
    if (!s) return undefined;
  }
  return s;
}

type Shape = "scalar" | "object" | "objects" | "list";

function shape(s: Schema, root: Schema): Shape {
  const vs = variants(s, root).filter((v) => v.type !== "null");
  if (vs.some((v) => !v.properties && !v.items && v.type !== "object")) return "scalar";
  const arr = vs.find((v) => v.items);
  if (arr) return objectOf(arr.items, root) ? "objects" : "list";
  return "object";
}

function typeName(s: Schema, root: Schema): string {
  const vs = variants(s, root).filter((v) => v.type !== "null");
  if (vs.some((v) => v.enum)) return "enum";
  const names = new Set(vs.map((v) => (v.items ? "list" : v.properties || v.type === "object" ? "object" : v.type ?? "")));
  // Текст с переводами: строка или {ru, en}
  if (names.has("string") && names.has("object")) names.delete("object");
  return [...names].filter(Boolean).join(" | ");
}

function valuesOf(s: Schema, root: Schema): string[] {
  const out: string[] = [];
  for (const v of variants(s, root)) {
    if (v.enum) out.push(...v.enum.map(String));
    else if (v.const !== undefined) out.push(String(v.const));
    else if (v.type === "boolean") out.push("true", "false");
  }
  return [...new Set(out)];
}

// ------------------------------------------------------------------ подсказки

const WORD_AFTER = /^[\w.-]*/;

/** Ключи, уже заданные в отображении, к которому относится строка `line` со столбцом ключа `col`. */
function presentKeys(lines: string[], line: number, col: number): Set<string> {
  const out = new Set<string>();
  const own = info(lines[line]);
  if (!own.dashes.length) {
    for (let j = line - 1; j >= 0; j--) {
      if (!isContent(lines[j])) continue;
      const inf = info(lines[j]);
      if (inf.indent < col) {
        if (inf.keyCol === col && inf.key !== null) out.add(inf.key);
        break;
      }
      if (inf.indent === col && inf.key !== null) out.add(inf.key);
    }
  }
  for (let j = line + 1; j < lines.length; j++) {
    if (!isContent(lines[j])) continue;
    const inf = info(lines[j]);
    if (inf.indent < col || (inf.indent === col && inf.dashes.length)) break;
    if (inf.indent === col && inf.key !== null) out.add(inf.key);
  }
  return out;
}

const lineStart = (text: string, pos: number) => text.lastIndexOf("\n", pos - 1) + 1;

// ------------------------------------------------------------------ flow-запись {…} / […]

interface Opener {
  ch: "{" | "[";
  pos: number;             // позиция скобки в строке
  key: string | null;      // ключ перед скобкой внутри родительской «{…}»
  seg: number;             // начало текущего элемента (после скобки или последней запятой)
}

const FLOW_KEY = /^\s*([^\s:,{}[\]]+)\s*$/;

/** Незакрытые скобки строки до позиции `end`; пусто — курсор не внутри «{…}»/«[…]» (или в строке, комментарии). */
function openers(line: string, end: number): Opener[] {
  const stack: Opener[] = [];
  for (let i = 0; i < end; i++) {
    const c = line[i];
    if (c === '"' || c === "'") {
      const close = line.indexOf(c, i + 1);
      if (close < 0 || close >= end) return [];
      i = close;
    } else if (c === "#" && (i === 0 || /\s/.test(line[i - 1]))) {
      return [];
    } else if (c === "{" || c === "[") {
      const top = stack[stack.length - 1];
      const km = top?.ch === "{" ? FLOW_KEY.exec(line.slice(top.seg, i).replace(/:\s*$/, "")) : null;
      stack.push({ ch: c, pos: i, key: km ? unquote(km[1]) : null, seg: i + 1 });
    } else if (c === "}" || c === "]") {
      stack.pop();
    } else if (c === "," && stack.length) {
      stack[stack.length - 1].seg = i + 1;
    }
  }
  return stack;
}

/** Ключи верхнего уровня внутри «{…}», начатой в позиции `start` (до закрывающей скобки или конца строки). */
function flowKeys(line: string, start: number): Set<string> {
  const out = new Set<string>();
  let depth = 0;
  let seg = start + 1;
  for (let i = start; i < line.length; i++) {
    const c = line[i];
    if (c === '"' || c === "'") {
      const close = line.indexOf(c, i + 1);
      if (close < 0) break;
      i = close;
    } else if (c === "{" || c === "[") {
      depth++;
    } else if (c === "}" || c === "]") {
      if (--depth === 0) break;
    } else if (depth === 1 && c === ":") {
      const km = FLOW_KEY.exec(line.slice(seg, i));
      if (km) out.add(unquote(km[1]));
    } else if (depth === 1 && c === ",") {
      seg = i + 1;
    }
  }
  return out;
}

// ------------------------------------------------------------------ подсказки

type Style = "block" | "flow";

/** Подсказки ключей объекта `obj`: вставка «ключ: » и заготовка значения по его типу. */
function keyItems(obj: Schema, root: Schema, present: Set<string>, prefix: string, from: number, to: number,
                  style: Style, col: number, hasColon: boolean): Completion[] {
  const required = new Set<string>(obj.required ?? []);
  const items: Completion[] = [];
  for (const [key, prop] of Object.entries(obj.properties as Record<string, Schema>)) {
    if (present.has(key) || !key.toLowerCase().startsWith(prefix.toLowerCase())) continue;
    const sh = shape(prop, root);
    let insert = key;
    let caret = 0;             // сдвиг курсора от конца вставки
    if (!hasColon) {
      if (style === "flow") {
        insert += sh === "scalar" ? ": " : sh === "object" ? ": {}" : ": []";
        if (sh !== "scalar") caret = 1;
      } else {
        const pad = "\n" + " ".repeat(col + 2);
        insert += sh === "scalar" ? ": " : sh === "list" ? ": []" : sh === "objects" ? ":" + pad + "- " : ":" + pad;
        if (sh === "list") caret = 1;
      }
    }
    const end = from + insert.length - caret;
    items.push({
      label: key,
      detail: [typeName(prop, root), required.has(key) ? "required" : ""].filter(Boolean).join(" · "),
      doc: deref(prop, root)?.description ?? "",
      edit: { from, to, insert, selStart: end, selEnd: end },
      chain: !hasColon && (sh === "object" || (style === "block" && sh === "objects")
        || (sh === "scalar" && valuesOf(prop, root).length > 0)),
    });
  }
  // Обязательные — первыми, остальные в порядке схемы
  items.sort((a, b) => Number(b.detail.endsWith("required")) - Number(a.detail.endsWith("required")));
  return items;
}

/** Подсказки значений перечисления свойства `prop`; `space` — пробел перед значением, если курсор сразу после «:». */
function valueItems(prop: Schema, root: Schema, prefix: string, tail: string, from: number, to: number,
                    space: string): Completion[] | null {
  const values = valuesOf(prop, root).filter((v) => v.startsWith(prefix));
  if (!values.length || (values.length === 1 && values[0] === prefix + tail)) return null;
  const doc = deref(prop, root)?.description ?? "";
  return values.map((v) => {
    const end = from + space.length + v.length;
    return { label: v, detail: "", doc, chain: false, edit: { from, to, insert: space + v, selStart: end, selEnd: end } };
  });
}

/**
 * Подсказки для курсора `pos`: ключи отображения (ещё не заданные) или значения перечисления после «ключ: » —
 * в блочной записи и внутри «{…}». `force` — показать и без набранного префикса (Ctrl+Space, после вставки).
 */
export function complete(text: string, pos: number, root: Schema, force = false): CompletionList | null {
  const ls = lineStart(text, pos);
  const lines = text.split("\n");
  const line = text.slice(0, ls).split("\n").length - 1;
  const before = text.slice(ls, pos);
  const after = text.slice(pos, text.indexOf("\n", pos) < 0 ? text.length : text.indexOf("\n", pos));
  const tail = WORD_AFTER.exec(after)![0];
  const hasColon = /^\s*:/.test(after.slice(tail.length));
  const result = (items: Completion[] | null, from: number): CompletionList | null =>
    (items?.length ? { items, line, col: from - ls } : null);

  // Внутри «{…}»: «- {bit: 1, na|}»
  const stack = openers(lines[line], before.length);
  if (stack.length) {
    const top = stack[stack.length - 1];
    if (top.ch !== "{") return null;
    // Путь к скобкам: блочная часть строки («- » или «ключ: »), затем ключи вложенных скобок
    const head = info(before.slice(0, stack[0].pos));
    const col = head.key !== null ? head.keyCol : stack[0].pos;
    const base = contextPath(lines, line, col);
    if (!base) return null;
    const path = head.key !== null ? [...base, head.key] : base;
    for (let k = 1; k < stack.length; k++) {
      if (stack[k - 1].ch === "[") path.push(ITEM);
      else if (stack[k].key !== null) path.push(stack[k].key!);
      else return null;
    }
    const seg = before.slice(top.seg);
    const km = /^\s*([\w-]*)$/.exec(seg);
    if (km) {
      const obj = objectOf(schemaAt(root, path), root);
      if (!obj?.properties || (!km[1] && !force)) return null;
      const from = pos - km[1].length;
      const items = keyItems(obj, root, flowKeys(lines[line], top.pos), km[1], from, pos + tail.length, "flow", 0, hasColon);
      return items.length === 1 && items[0].label === km[1] + tail && hasColon ? null : result(items, from);
    }
    const vm = /^\s*([^\s:,{}[\]]+)\s*:(\s*)([\w.-]*)$/.exec(seg);
    if (!vm) return null;
    const prop = schemaAt(root, [...path, unquote(vm[1])]);
    const from = pos - vm[3].length;
    return prop ? result(valueItems(prop, root, vm[3], tail, from, pos + tail.length, vm[2] ? "" : " "), from) : null;
  }

  // Ключ: «  - na|»
  const km = /^(\s*(?:-\s+)*)([\w-]*)$/.exec(before);
  if (km) {
    const prefix = km[2];
    if (!prefix && !force) return null;
    const col = km[1].length;
    const path = contextPath(lines, line, col);
    const obj = path && objectOf(schemaAt(root, path), root);
    if (!obj?.properties) return null;
    const from = pos - prefix.length;
    const items = keyItems(obj, root, presentKeys(lines, line, col), prefix, from, pos + tail.length, "block", col, hasColon);
    if (items.length === 1 && items[0].label === prefix + tail && hasColon) return null;
    // Новый элемент списка можно записать в одну строку: «- {bit: 0, name: …}»
    if (!prefix && !tail && km[1].trimEnd().endsWith("-") && !after.trim()) {
      items.push({ label: "{ }", detail: "flow", doc: "", chain: true,
        edit: { from, to: pos, insert: "{}", selStart: from + 1, selEnd: from + 1 } });
    }
    return result(items, from);
  }

  // Значение: «  encoding: me|»
  const inf = info(before);
  const vm = inf.key !== null ? /^(\s*)([\w.-]*)$/.exec(inf.rest) : null;
  if (vm) {
    const path = contextPath(lines, line, inf.keyCol);
    const prop = path && schemaAt(root, [...path, inf.key!]);
    const from = pos - vm[2].length;
    return prop ? result(valueItems(prop, root, vm[2], tail, from, pos + tail.length, inf.rest ? "" : " "), from) : null;
  }
  return null;
}
