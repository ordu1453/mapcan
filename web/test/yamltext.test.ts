// The YAML tab without a full parse: highlighting, the lines of a node, editing with keys.

import { describe, expect, it } from "vitest";
import { highlight, keyEdit, nodeAtLine, nodeLines } from "../src/yamltext";

const MAP = [
  "mapcan: 2",                              // 1
  "document:",                              // 2
  "  title: Example",                       // 3
  "  note: |",                              // 4
  "    # not a comment",                    // 5
  "    a: not a key",                       // 6
  "buses:",                                 // 7
  "  - name: demo",                         // 8
  "    devices:",                           // 9
  "      - name: pump",                     // 10
  "        frames:",                        // 11
  "          - name: state     # tx",       // 12
  "            signals:",                   // 13
  "              - {name: a, byte: 0}",     // 14
  "              - name: b",                // 15
  "                values:",                // 16
  "                  0: OFF",               // 17
  "                  1: 'ON'",              // 18
  "",                                       // 19
  "      - name: panel",                    // 20
  "        frames: []",                     // 21
].join("\n");

describe("highlight", () => {
  const html = highlight(MAP);

  it("gives one line of HTML per line of text", () => {
    expect(html).toHaveLength(MAP.split("\n").length);
  });

  it("marks keys, numbers, strings and comments", () => {
    expect(html[0]).toBe('<span class="y-key">mapcan</span><span class="y-punct">:</span> <span class="y-num">2</span>');
    expect(html[11]).toContain('<span class="y-comment">     # tx</span>');
    expect(html[17]).toContain(`<span class="y-str">'ON'</span>`);
    expect(html[7]).toMatch(/^ {2}<span class="y-punct">-<\/span> <span class="y-key">name<\/span>/);
  });

  it("marks flow collections piece by piece", () => {
    expect(html[13]).toContain('<span class="y-punct">{</span>');
    expect(html[13]).toContain('<span class="y-key">name</span>');
    expect(html[13]).toContain('<span class="y-num">0</span>');
    expect(html[20]).toContain('<span class="y-punct">[</span><span class="y-punct">]</span>');
  });

  it("treats the lines of a block scalar as text", () => {
    expect(html[3]).toContain('<span class="y-punct">|</span>');
    expect(html[4]).toBe('<span class="y-str">    # not a comment</span>');
    expect(html[5]).toBe('<span class="y-str">    a: not a key</span>');
    expect(html[6]).toContain('<span class="y-key">buses</span>');
  });

  it("classifies scalars", () => {
    const [b, n, a, t, d, s] = highlight("a: true\nb: ~\nc: *ref\nd: !tag\ne: ---\nf: <x>");
    expect(b).toContain('y-bool">true');
    expect(n).toContain('y-bool">~');
    expect(a).toContain('y-anchor">*ref');
    expect(t).toContain('y-tag">!tag');
    expect(d).toContain('y-plain">---');
    expect(s).toContain("&lt;x&gt;");
  });

  it("marks document markers and comment lines", () => {
    const [start, comment, empty] = highlight("--- # doc\n  # note\n");
    expect(start).toContain('<span class="y-punct">---</span>');
    expect(comment).toBe('  <span class="y-comment"># note</span>');
    expect(empty).toBe("");
  });
});

describe("nodeLines", () => {
  it("finds a mapping key and its value", () => {
    expect(nodeLines(MAP, ["document"])).toEqual({ first: 2, last: 6 });
    expect(nodeLines(MAP, ["document", "title"])).toEqual({ first: 3, last: 3 });
  });

  it("finds list items and the keys of an item", () => {
    expect(nodeLines(MAP, ["buses", 0, "devices", 0])).toEqual({ first: 10, last: 18 });
    expect(nodeLines(MAP, ["buses", 0, "devices", 1])).toEqual({ first: 20, last: 21 });
    expect(nodeLines(MAP, ["buses", 0, "devices", 0, "frames", 0, "name"])).toEqual({ first: 12, last: 12 });
  });

  it("stops at a flow collection: deeper is the same line", () => {
    const sig = ["buses", 0, "devices", 0, "frames", 0, "signals", 0];
    expect(nodeLines(MAP, sig)).toEqual({ first: 14, last: 14 });
    expect(nodeLines(MAP, [...sig, "byte"])).toEqual({ first: 14, last: 14 });
  });

  it("matches the keys of a value table as numbers", () => {
    const values = ["buses", 0, "devices", 0, "frames", 0, "signals", 1, "values"];
    expect(nodeLines(MAP, [...values, 1])).toEqual({ first: 18, last: 18 });
    expect(nodeLines('values:\n  "0x10": A\n  \'it\'\'s\': B', ["values", 16])).toEqual({ first: 2, last: 2 });
    expect(nodeLines('values:\n  "0x10": A\n  \'it\'\'s\': B', ["values", "it's"])).toEqual({ first: 3, last: 3 });
  });

  it("answers null for a path that is not there", () => {
    expect(nodeLines(MAP, ["nope"])).toBeNull();
    expect(nodeLines(MAP, ["buses", 3])).toBeNull();
    // A key without a value: the deepest node found
    expect(nodeLines("a:\nb: 1", ["a", "x"])).toEqual({ first: 1, last: 1 });
  });

  it("keeps a last line of a block scalar that starts with #", () => {
    const text = "a:\n  note: |\n    text\n    # also text\n  # a comment\nb: 1";
    expect(nodeLines(text, ["a", "note"])).toEqual({ first: 2, last: 4 });
    expect(nodeLines(text, ["a"])).toEqual({ first: 1, last: 4 });
  });

  it("reads a list written without an indent under its key", () => {
    expect(nodeLines("items:\n- a\n- b\nnext: 1", ["items", 1])).toEqual({ first: 3, last: 3 });
  });
});

describe("nodeAtLine", () => {
  const paths = [["buses", 0], ["buses", 0, "devices", 0], ["buses", 0, "devices", 0, "frames", 0],
    ["buses", 0, "devices", 0, "frames", 0, "signals", 0],
    ["buses", 0, "devices", 0, "frames", 0, "signals", 0, "byte"], ["nope"]];

  it("takes the most nested node of the line", () => {
    expect(nodeAtLine(MAP, 12, paths)).toEqual(["buses", 0, "devices", 0, "frames", 0]);
    // A flow item and its field are on the same line: the deeper path
    expect(nodeAtLine(MAP, 14, paths)).toEqual(["buses", 0, "devices", 0, "frames", 0, "signals", 0, "byte"]);
    expect(nodeAtLine(MAP, 1, paths)).toBeNull();
  });
});

describe("keyEdit", () => {
  // "^" marks the cursor
  const at = (text: string) => text.indexOf("^");
  const press = (marked: string, key: string, shift = false, selLength = 0) => {
    const pos = at(marked);
    const text = marked.replace("^", "");
    const e = keyEdit(text, pos, pos + selLength, key, shift);
    if (!e) return null;
    const out = text.slice(0, e.from) + e.insert + text.slice(e.to);
    return out.slice(0, e.selStart) + "^" + out.slice(e.selStart);
  };

  it("indents to the next tab stop with Tab", () => {
    expect(press("a:\n^b", "Tab")).toBe("a:\n  ^b");
    expect(press("a:\n ^b", "Tab")).toBe("a:\n  ^b");
  });

  it("shifts the selected lines with Tab and Shift+Tab", () => {
    const text = "a:\nb: 1\n\nc: 2\n";
    const e = keyEdit(text, 3, 12, "Tab", false)!;
    expect(text.slice(0, e.from) + e.insert + text.slice(e.to)).toBe("a:\n  b: 1\n\n  c: 2\n");
    expect([e.selStart, e.selEnd]).toEqual([3, 16]);
    const back = keyEdit("  b: 1\n c: 2", 4, 4, "Tab", true)!;
    expect(back.insert).toBe("b: 1");
    expect(back.selStart).toBe(2);
    expect(keyEdit("b: 1", 0, 0, "Tab", true)).toBeNull();
    // A selection that ends at the start of a line does not take that line
    const two = keyEdit("a: 1\nb: 2\n", 0, 5, "Tab", false)!;
    expect(two.insert).toBe("  a: 1");
  });

  it("breaks the line with the right indent on Enter", () => {
    expect(press("  key: 1^", "Enter")).toBe("  key: 1\n  ^");
    expect(press("  key:^", "Enter")).toBe("  key:\n    ^");
    expect(press("  note: | # text^", "Enter")).toBe("  note: | # text\n    ^");
    expect(press("  - name: a^", "Enter")).toBe("  - name: a\n    ^");
    expect(press("  key: 1^   rest", "Enter")).toBe("  key: 1\n  ^rest");
    expect(press("   ^", "Enter")).toBeNull();
  });

  it("deletes the indent back to the previous level on Backspace", () => {
    expect(press("a:\n    ^b", "Backspace")).toBe("a:\n  ^b");
    expect(press("a:\n   ^b", "Backspace")).toBeNull();
    expect(press("a: x  ^", "Backspace")).toBe("a: x^");
    expect(press("a^", "Backspace")).toBeNull();
  });

  it("leaves other keys and Backspace over a selection to the browser", () => {
    expect(keyEdit("a", 0, 0, "x", false)).toBeNull();
    expect(keyEdit("    a", 2, 4, "Backspace", false)).toBeNull();
  });
});
