// Работа с текстом YAML без полного разбора: подсветка синтаксиса и поиск строк узла по пути.
// Рассчитано на блочный стиль, в котором карту пишут руками и сохраняет редактор.
import type { Path } from "./types";

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const span = (cls: string, s: string) => (s ? `<span class="y-${cls}">${esc(s)}</span>` : "");

const KEY_RE = /^(\s*(?:-\s+)*)("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^\s#'"{[\-][^#]*?|-[^\s#][^#]*?)(\s*:)(?=\s|$)/;
const NUM_RE = /^[-+]?(?:0x[0-9a-f_]+|0o[0-7_]+|0b[01_]+|(?:\d[\d_]*)?\.?\d[\d_]*(?:e[-+]?\d+)?|\.inf|\.nan)$/i;
const BLOCK_RE = /^[|>][-+0-9]*$/;

function scalar(s: string): string {
  const t = s.trim();
  if (!t) return esc(s);
  const lead = s.slice(0, s.indexOf(t));
  const tail = s.slice(lead.length + t.length);
  let cls = "plain";
  if (/^["']/.test(t)) cls = "str";
  else if (/^(?:true|false|null|~)$/i.test(t)) cls = "bool";
  else if (NUM_RE.test(t)) cls = "num";
  else if (/^[&*]\S+$/.test(t)) cls = "anchor";
  else if (/^!\S*$/.test(t)) cls = "tag";
  else if (BLOCK_RE.test(t)) cls = "punct";
  return esc(lead) + span(cls, t) + esc(tail);
}

// Значение после «ключ:» или «- »: скаляр, комментарий или flow-коллекция {…}/[…].
function value(s: string): string {
  const t = s.trimStart();
  if (!/^[{[]/.test(t)) {
    const m = /^((?:"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^#]|#(?<!\s#))*?)(\s+#.*|^#.*)?$/.exec(s);
    const body = m ? m[1] : s;
    const comment = m?.[2] ?? "";
    return scalar(body) + span("comment", comment);
  }
  let out = "";
  const re = /("(?:[^"\\]|\\.)*"|'(?:[^']|'')*')|(\s+#.*$)|([{}[\],])|([^{}[\],"']+)/gy;
  let m: RegExpExecArray | null;
  let pos = 0;
  while ((m = re.exec(s))) {
    pos = re.lastIndex;
    if (m[1]) out += span("str", m[1]);
    else if (m[2]) out += span("comment", m[2]);
    else if (m[3]) out += span("punct", m[3]);
    else {
      const kv = /^(\s*)([^:]+?)(\s*:)(\s.*|)$/.exec(m[4]);
      out += kv ? esc(kv[1]) + span("key", kv[2]) + span("punct", kv[3]) + scalar(kv[4]) : scalar(m[4]);
    }
  }
  return out + esc(s.slice(pos));
}

const indentOf = (l: string) => l.length - l.trimStart().length;
const isContent = (l: string) => /^\s*[^\s#]/.test(l);

/** HTML подсветки по строкам (без завершающих переводов строк). */
export function highlight(text: string): string[] {
  const out: string[] = [];
  let blockIndent = -1;          // отступ строки с «|» / «>»: более глубокие строки — текст
  for (const line of text.split("\n")) {
    if (blockIndent >= 0) {
      if (!isContent(line) && !line.trim()) { out.push(esc(line)); continue; }
      if (indentOf(line) > blockIndent) { out.push(span("str", line)); continue; }
      blockIndent = -1;
    }
    const trimmed = line.trimStart();
    if (!trimmed) { out.push(esc(line)); continue; }
    if (trimmed.startsWith("#")) { out.push(esc(line.slice(0, line.length - trimmed.length)) + span("comment", trimmed)); continue; }
    if (/^(?:---|\.\.\.)(?:\s|$)/.test(line)) { out.push(span("punct", line.slice(0, 3)) + value(line.slice(3))); continue; }

    let html = "";
    let rest = line;
    const k = KEY_RE.exec(line);
    const lead = k ? k[1] : (/^\s*(?:-\s+|-$)*/.exec(line)?.[0] ?? "");
    html += lead.replace(/[^-]+|-/g, (p) => (p === "-" ? span("punct", "-") : esc(p)));
    rest = line.slice(lead.length);
    if (k) {
      html += span("key", k[2]) + span("punct", k[3]);
      rest = line.slice(k[0].length);
    }
    html += value(rest);
    // Текст блочного скаляра — строки глубже ключа (или «-» элемента-скаляра).
    if (BLOCK_RE.test(rest.replace(/\s+#.*$/, "").trim())) blockIndent = k ? keyCol(line) : indentOf(line);
    out.push(html);
  }
  return out;
}

// ------------------------------------------------------------------ строки узла по пути

function keyText(raw: string): string {
  if (raw.startsWith('"')) {
    try { return JSON.parse(raw) as string; } catch { return raw.slice(1, -1); }
  }
  if (raw.startsWith("'")) return raw.slice(1, -1).replace(/''/g, "'");
  return raw;
}

function keyMatches(raw: string, el: string | number): boolean {
  const t = keyText(raw);
  if (t === String(el)) return true;
  return typeof el === "number" && t.trim() !== "" && Number(t.replace(/_/g, "")) === el;
}

/** Столбец, с которого начинается ключ строки (после маркеров «- »). */
function keyCol(line: string): number {
  return /^\s*(?:-\s+)*/.exec(line)![0].length;
}

/** Конец значения ключа/элемента, начатого в строке `from` со столбцом `col`: первая строка, вышедшая из блока. */
function blockEnd(lines: string[], from: number, end: number, col: number, item: boolean): number {
  for (let i = from + 1; i < end; i++) {
    const l = lines[i];
    if (!isContent(l)) continue;
    const ind = indentOf(l);
    // Элемент списка заканчивается на следующем «-» того же уровня; значение ключа может быть
    // списком без отступа («key:\n- a»), поэтому для ключа строка «-» на том же уровне — ещё его значение.
    if (ind < col || (ind === col && (item || !l.trimStart().startsWith("-")))) return i;
  }
  return end;
}

/** Обрезать хвостовые пустые строки и комментарии. */
function trimEnd(lines: string[], start: number, end: number): number {
  while (end > start + 1 && !isContent(lines[end - 1])) end--;
  return end;
}

/** Строки узла [first, last] (с 1) или null, если путь не найден в тексте. */
export function nodeLines(text: string, path: Path): { first: number; last: number } | null {
  const lines = text.split("\n");
  let s = 0;                     // область поиска: [s, e)
  let e = lines.length;
  let firstOnS = false;          // строка s — «- key: …» элемента, её ключ тоже ищем
  let inline = false;            // значение найденного узла записано в той же строке
  let found: [number, number] | null = null;

  for (const el of path) {
    if (inline) break;           // flow-коллекция {…}/[…]: глубже — та же строка
    let i = s;
    while (i < e && !isContent(lines[i])) i++;
    if (i >= e) return found && { first: found[0] + 1, last: found[1] };
    const firstLine = lines[i];
    const isSeq = !firstOnS && firstLine.trimStart().startsWith("-");

    if (isSeq && typeof el === "number") {
      const ind = indentOf(firstLine);
      let n = -1;
      let hit = -1;
      for (let j = i; j < e; j++) {
        const l = lines[j];
        if (!isContent(l) || indentOf(l) !== ind || !l.trimStart().startsWith("-")) continue;
        if (++n === el) { hit = j; break; }
      }
      if (hit < 0) return null;
      const end = trimEnd(lines, hit, blockEnd(lines, hit, e, ind, true));
      found = [hit, end];
      s = hit; e = end; firstOnS = true;
      inline = /^\s*-\s+[{[]/.test(lines[hit]);
      continue;
    }

    const col = keyCol(firstLine);
    let hit = -1;
    for (let j = i; j < e; j++) {
      const l = lines[j];
      if (!isContent(l) || keyCol(l) !== col) continue;
      if (j !== i && indentOf(l) !== col) continue;          // «- key» другого элемента
      const m = KEY_RE.exec(l);
      if (m && keyMatches(m[2], el)) { hit = j; break; }
    }
    if (hit < 0) return null;
    const end = trimEnd(lines, hit, blockEnd(lines, hit, e, col, false));
    found = [hit, end];
    s = hit + 1; e = end; firstOnS = false;
    inline = /^\s*[{[]/.test(lines[hit].slice(KEY_RE.exec(lines[hit])![0].length));
  }
  return found && { first: found[0] + 1, last: found[1] };
}

/** Самый вложенный из узлов `paths`, строки которого содержат строку `line` (с 1). */
export function nodeAtLine(text: string, line: number, paths: Path[]): Path | null {
  let best: Path | null = null;
  let size = Infinity;
  for (const p of paths) {
    const r = nodeLines(text, p);
    if (!r || line < r.first || line > r.last) continue;
    const n = r.last - r.first;
    // При равных диапазонах (flow-коллекция в одной строке) — более глубокий путь.
    if (n < size || (n === size && best && p.length > best.length)) {
      best = p;
      size = n;
    }
  }
  return best;
}
