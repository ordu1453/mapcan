// Working with YAML text without a full parse: syntax highlighting and finding the lines of a node by path.
// Made for the block style in which maps are written by hand and saved by the editor.
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

// A value after "key:" or "- ": a scalar, a comment or a flow collection {…}/[…].
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

/** Highlighting HTML per line (without the trailing line breaks). */
export function highlight(text: string): string[] {
  const out: string[] = [];
  let blockIndent = -1;          // indent of the line with "|" / ">": deeper lines are text
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
    // Text of a block scalar: lines deeper than the key (or than the "-" of a scalar item).
    if (BLOCK_RE.test(rest.replace(/\s+#.*$/, "").trim())) blockIndent = k ? keyCol(line) : indentOf(line);
    out.push(html);
  }
  return out;
}

// ------------------------------------------------------------------ lines of a node by path

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

/** Column where the line's key starts (after the "- " markers). */
function keyCol(line: string): number {
  return /^\s*(?:-\s+)*/.exec(line)![0].length;
}

/** End of the value of a key/item started on line `from` at column `col`: the first line that left the block. */
function blockEnd(lines: string[], from: number, end: number, col: number, item: boolean): number {
  for (let i = from + 1; i < end; i++) {
    const l = lines[i];
    if (!isContent(l)) continue;
    const ind = indentOf(l);
    // A list item ends at the next "-" of the same level; the value of a key can be
    // a list without an indent ("key:\n- a"), so for a key a "-" line at the same level is still its value.
    if (ind < col || (ind === col && (item || !l.trimStart().startsWith("-")))) return i;
  }
  return end;
}

/** Trim trailing empty lines and comments. */
function trimEnd(lines: string[], start: number, end: number, text: Set<number>): number {
  while (end > start + 1 && !isContent(lines[end - 1]) && !text.has(end - 1)) end--;
  return end;
}

/** Lines of the text of block scalars ("|", ">"): a "#" there is text, not a comment. */
function scalarText(lines: string[]): Set<number> {
  const out = new Set<number>();
  let blockIndent = -1;
  lines.forEach((line, i) => {
    if (blockIndent >= 0) {
      if (!line.trim()) return;
      if (indentOf(line) > blockIndent) { out.add(i); return; }
      blockIndent = -1;
    }
    const k = KEY_RE.exec(line);
    const rest = k ? line.slice(k[0].length) : line.replace(/^\s*(?:-\s+)*/, "");
    if (BLOCK_RE.test(rest.replace(/\s+#.*$/, "").trim())) blockIndent = k ? keyCol(line) : indentOf(line);
  });
  return out;
}

/** Lines of the node [first, last] (from 1), or null if the path is not found in the text. */
export function nodeLines(text: string, path: Path): { first: number; last: number } | null {
  const lines = text.split("\n");
  const scalars = scalarText(lines);
  let s = 0;                     // search area: [s, e)
  let e = lines.length;
  let firstOnS = false;          // line s is "- key: …" of an item, its key is searched too
  let inline = false;            // the value of the found node is written on the same line
  let found: [number, number] | null = null;

  for (const el of path) {
    if (inline) break;           // flow collection {…}/[…]: deeper is the same line
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
      const end = trimEnd(lines, hit, blockEnd(lines, hit, e, ind, true), scalars);
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
      if (j !== i && indentOf(l) !== col) continue;          // "- key" of another item
      const m = KEY_RE.exec(l);
      if (m && keyMatches(m[2], el)) { hit = j; break; }
    }
    if (hit < 0) return null;
    const end = trimEnd(lines, hit, blockEnd(lines, hit, e, col, false), scalars);
    found = [hit, end];
    s = hit + 1; e = end; firstOnS = false;
    inline = /^\s*[{[]/.test(lines[hit].slice(KEY_RE.exec(lines[hit])![0].length));
  }
  return found && { first: found[0] + 1, last: found[1] };
}

// ------------------------------------------------------------------ editing with keys

const INDENT = 2;

/** Replacing text[from, to) with insert, and the new selection: the result of a key press. */
export interface TextEdit {
  from: number;
  to: number;
  insert: string;
  selStart: number;
  selEnd: number;
}

const lineStartAt = (text: string, pos: number) => text.lastIndexOf("\n", pos - 1) + 1;

/** Shift the selected lines right (Tab) or left (Shift+Tab); empty lines are left alone. */
function shiftLines(text: string, start: number, end: number, out: boolean): TextEdit | null {
  const from = lineStartAt(text, start);
  // A selection ending at the start of a line does not take that line.
  let to = text.indexOf("\n", end > start && end === lineStartAt(text, end) ? end - 1 : end);
  if (to < 0) to = text.length;
  const lines = text.slice(from, to).split("\n");
  const deltas = lines.map((l) => (out ? -Math.min(INDENT, indentOf(l)) : l.trim() ? INDENT : 0));
  if (deltas.every((d) => d === 0)) return null;
  const insert = lines.map((l, i) => (deltas[i] > 0 ? " ".repeat(INDENT) + l : l.slice(-deltas[i]))).join("\n");
  // Position in the source text → in the new one: the cursor stays on its character but not left of the line's start;
  // from the start of a line it does not move, so a selection of whole lines takes the new indent too.
  const map = (p: number) => {
    let ls = from;
    let shift = 0;
    for (let i = 0; i < lines.length; i++) {
      const le = ls + lines[i].length;
      if (p <= le) return ls + shift + (p === ls ? 0 : Math.max(0, p - ls + deltas[i]));
      shift += deltas[i];
      ls = le + 1;
    }
    return p + shift;
  };
  return { from, to, insert, selStart: map(start), selEnd: map(end) };
}

/**
 * Edit by a key in the YAML tab, or null to let the browser handle it.
 * Tab indents (with a selection, shifts the lines), Shift+Tab shifts left, Enter breaks the line
 * with the current line's indent (deeper after "key:"), Backspace in the indent deletes back to the previous level.
 */
export function keyEdit(text: string, start: number, end: number, key: string, shift: boolean): TextEdit | null {
  const ls = lineStartAt(text, start);
  const before = text.slice(ls, start);
  if (key === "Tab") {
    if (shift || start !== end) return shiftLines(text, start, end, shift);
    const pad = " ".repeat(INDENT - (before.length % INDENT));
    return { from: start, to: end, insert: pad, selStart: start + pad.length, selEnd: start + pad.length };
  }
  if (key === "Enter") {
    if (!before.trim()) return null;
    // Fields of a list item "- key: …" go on at the key's level; after "key:" and "|", ">" deeper.
    let ind = before.trimStart().startsWith("-") ? keyCol(before) : indentOf(before);
    const code = before.replace(/\s+#.*$/, "").trimEnd();
    if (code.endsWith(":") || /:\s+[|>][-+0-9]*$/.test(code)) ind += INDENT;
    let to = end;
    while (text[to] === " ") to++;           // spaces after the cursor are not carried over
    const insert = "\n" + " ".repeat(ind);
    return { from: start, to, insert, selStart: start + insert.length, selEnd: start + insert.length };
  }
  if (key === "Backspace" && start === end) {
    // Spaces before the cursor are deleted back to the previous tab stop, but not beyond the spaces themselves.
    const spaces = before.length - before.trimEnd().length;
    const n = Math.min(spaces, ((before.length - 1) % INDENT) + 1);
    if (n < 2) return null;
    return { from: start - n, to: start, insert: "", selStart: start - n, selEnd: start - n };
  }
  return null;
}

/** The most nested of the nodes `paths` whose lines contain line `line` (from 1). */
export function nodeAtLine(text: string, line: number, paths: Path[]): Path | null {
  let best: Path | null = null;
  let size = Infinity;
  for (const p of paths) {
    const r = nodeLines(text, p);
    if (!r || line < r.first || line > r.last) continue;
    const n = r.last - r.first;
    // With equal ranges (a flow collection on one line), the deeper path.
    if (n < size || (n === size && best && p.length > best.length)) {
      best = p;
      size = n;
    }
  }
  return best;
}
