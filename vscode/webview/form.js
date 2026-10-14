// Node form (see src/form.ts). Fields are written to the YAML as they are typed: after a short
// pause, on Enter and when a field loses focus. Values from the server never overwrite the field
// being typed in. Which fields a node has, when they apply and how their text is parsed is shared
// with the web editor (web/src/form); esbuild.mjs bundles it into dist/webview/form.js.
// @ts-check
import { fieldHelp } from "../../web/src/form/help";
import { formatValue, parseInput, parseInteger, selectValue } from "../../web/src/form/input";
import { applies, FORMS, isRequired, optionsOf, placeholderOf, signalEncoding } from "../../web/src/form/spec";

(function () {
  const vscode = acquireVsCodeApi();
  const app = /** @type {HTMLElement} */ (document.getElementById("app"));

  /**
   * @typedef {import("../../web/src/form/spec").FieldDef} Field
   * @typedef {import("../../web/src/form/spec").FormContext} Ctx
   */

  /** Text of a field → value for the YAML; null removes the key. Throws on invalid input. */
  function parse(/** @type {Field} */ f, /** @type {string} */ raw) {
    if (raw.trim() === "" && isRequired(f, ctx())) throw new Error("Required");
    return parseInput(f.type, raw);
  }

  // ---------------------------------------------------------------- state

  /** @type {any} */
  let node = null;
  let created = false;
  /** Fields of the shown node: key → {def, row, input, error, timer} */
  /** @type {Map<string, any>} */
  let rows = new Map();
  /** @type {{el: HTMLElement, fields: any[]}[]} */
  let sections = [];
  let shownKind = "";
  let shownPath = "";

  /** What the form's conditions know about the node (FormContext in web/src/form/spec.ts), from the server. */
  const ctx = () => /** @type {Ctx} */ ({
    values: node.values, protocol: node.protocol, fd: !!node.fd, busBrs: node.busBrs ?? null, owner: node.owner,
    devices: node.devices, frameDirection: node.frameDirection, signalEncoding: node.signalEncoding,
    bitLength: node.bitLength ?? null, hasSelector: !!node.hasSelector, frameTypes: node.frameTypes ?? [],
  });

  function el(/** @type {string} */ tag, /** @type {Record<string, any>} */ props = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") e.className = v;
      // The webview's CSP drops style attributes; properties set through CSSOM are allowed
      else if (k === "style") for (const decl of String(v).split(";")) {
        const i = decl.indexOf(":");
        if (i > 0) e.style.setProperty(decl.slice(0, i).trim(), decl.slice(i + 1).trim());
      }
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c != null) e.append(c);
    return e;
  }

  const CHEVRON = '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3.15 5.65a.5.5 0 0 1 .7 0L8 9.79l4.15-4.14a.5.5 0 1 1 .7.7l-4.5 4.5a.5.5 0 0 1-.7 0l-4.5-4.5a.5.5 0 0 1 0-.7z"/></svg>';

  function send(/** @type {string} */ key, /** @type {any} */ value) {
    node.values[key] = value;
    vscode.postMessage({ type: "set", key, value });
    updateVisibility();
  }

  /** Write the text field now (if it changed and is valid). */
  function commit(/** @type {any} */ r) {
    clearTimeout(r.timer);
    r.timer = undefined;
    let value;
    try {
      value = parse(r.def, r.input.value);
    } catch (err) {
      r.row.classList.add("invalid");
      r.error.textContent = /** @type {Error} */ (err).message;
      r.error.hidden = false;
      return;
    }
    r.row.classList.remove("invalid");
    r.error.hidden = true;
    const current = node.values[r.def.key] ?? null;
    if (JSON.stringify(value) !== JSON.stringify(current)) send(r.def.key, value);
  }

  // ---------------------------------------------------------------- unit combobox

  /**
   * Input with a list of standard units in the document's language. The list filters as you type;
   * any other text is accepted as it is.
   */
  function unitCombo(/** @type {any} */ r, /** @type {string} */ id) {
    const input = /** @type {HTMLInputElement} */ (el("input", { id, type: "text", autocomplete: "off", spellcheck: "false",
      role: "combobox", "aria-autocomplete": "list", "aria-expanded": "false" }));
    const menu = el("div", { class: "menu", role: "listbox", hidden: true });
    const toggle = el("button", { class: "toggle", type: "button", tabindex: "-1", title: "Standard units" });
    toggle.innerHTML = CHEVRON;
    let active = -1;
    /** @type {string[]} */
    let shown = [];

    const choices = () => [...new Set((node.units ?? []).map(([ru, en]) => (node.lang === "en" ? en : ru)))];
    const highlight = (/** @type {string} */ text, /** @type {string} */ q) => {
      const i = q ? text.toLowerCase().indexOf(q) : -1;
      return i < 0 ? [text] : [text.slice(0, i), el("mark", {}, text.slice(i, i + q.length)), text.slice(i + q.length)];
    };
    const open = (/** @type {boolean} */ all) => {
      const q = all ? "" : input.value.trim().toLowerCase();
      shown = choices().filter((u) => !q || u.toLowerCase().includes(q));
      if (!shown.length) return close();
      active = Math.max(0, shown.indexOf(input.value));
      menu.replaceChildren(...shown.map((u, i) => el("div", {
        class: "option" + (i === active ? " active" : ""), role: "option",
        onmousedown: (/** @type {MouseEvent} */ e) => {
          e.preventDefault();
          pick(i);
        },
      }, el("span", {}, highlight(u, q)))));
      menu.hidden = false;
      input.setAttribute("aria-expanded", "true");
      menu.children[active]?.scrollIntoView({ block: "nearest" });
    };
    const close = () => {
      menu.hidden = true;
      input.setAttribute("aria-expanded", "false");
      active = -1;
    };
    const move = (/** @type {number} */ d) => {
      if (menu.hidden) return open(true);
      menu.children[active]?.classList.remove("active");
      active = (active + d + shown.length) % shown.length;
      menu.children[active]?.classList.add("active");
      menu.children[active]?.scrollIntoView({ block: "nearest" });
    };
    const pick = (/** @type {number} */ i) => {
      input.value = shown[i];
      close();
      commit(r);
    };

    input.addEventListener("input", () => {
      open(false);
      clearTimeout(r.timer);
      r.timer = setTimeout(() => commit(r), 400);
    });
    input.addEventListener("focus", () => open(true));
    input.addEventListener("click", () => menu.hidden && open(true));
    input.addEventListener("blur", () => {
      close();
      commit(r);
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
      else if (e.key === "Enter") {
        if (!menu.hidden && active >= 0) { e.preventDefault(); pick(active); } else commit(r);
      } else if (e.key === "Escape" && !menu.hidden) { e.preventDefault(); close(); }
    });
    toggle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      if (menu.hidden) {
        input.focus();
        open(true);
      } else close();
    });
    r.input = input;
    return el("div", { class: "combo" }, input, toggle, menu);
  }

  // ---------------------------------------------------------------- fields

  function buildField(/** @type {Field} */ f) {
    const id = `f-${f.key}`;
    const tip = fieldHelp(node.kind, f);
    const r = { def: f, row: null, input: null, error: el("div", { class: "error", hidden: true }), timer: undefined };
    let control;
    if (f.type === "bool") {
      r.input = el("input", { type: "checkbox", id, onchange: () => send(f.key, r.input.checked) });
      control = el("label", { class: "check", for: id, title: tip }, r.input, f.label);
    } else if (f.type === "select") {
      r.input = el("select", { id, onchange: () => send(f.key, selectValue(r.input.value, f.numeric)) });
      control = r.input;
    } else if (f.type === "devices") {
      r.input = el("div", { class: "checks", id });
      control = r.input;
    } else if (f.type === "unit") {
      control = unitCombo(r, id);
    } else {
      // Text with translations is edited in the document language
      const textarea = !!f.multiline;
      r.input = el(textarea ? "textarea" : "input", {
        id, type: textarea ? undefined : "text", rows: textarea ? "2" : undefined,
        class: f.mono || f.type === "hex" ? "mono" : undefined,
        spellcheck: textarea || (["text", "loc"].includes(f.type) && !f.mono) ? undefined : "false",
        oninput: () => {
          clearTimeout(r.timer);
          r.timer = setTimeout(() => commit(r), 400);
        },
        onblur: () => commit(r),
        onkeydown: (/** @type {KeyboardEvent} */ e) => {
          if (e.key === "Enter" && !textarea) commit(r);
        },
      });
      control = r.input;
    }
    // A checkbox carries its own label; for the others the label is above the control
    const label = f.type === "bool" ? el("div", { class: "label" }, " ")
      : el(f.type === "devices" ? "div" : "label", { class: f.type === "devices" ? "label" : undefined,
        for: f.type === "devices" ? undefined : id, title: tip }, f.label,
        isRequired(f, ctx()) ? el("span", { class: "req" }, "*") : null);
    r.row = el("div", { class: "field" + (f.half ? " half" : "") }, f.type === "bool" && !f.half ? null : label, control, r.error);
    return r;
  }

  // ---------------------------------------------------------------- bit layout

  /** Bits a signal occupies (as bits.py: lsb0 numbering, start — the LSB). */
  function occupiedBits(/** @type {number} */ start, /** @type {number} */ length, /** @type {boolean} */ bigEndian) {
    const out = [];
    let pos = start;
    let left = length;
    while (left > 0) {
      const byte = Math.floor(pos / 8);
      const shift = ((pos % 8) + 8) % 8;
      const n = Math.min(8 - shift, left);
      for (let k = 0; k < n; k++) out.push(byte * 8 + shift + k);
      left -= n;
      pos = bigEndian ? (byte - 1) * 8 : (byte + 1) * 8;
    }
    return out;
  }

  /** Two signals are in the frame at the same time (multiplexing). */
  const coexist = (/** @type {number[]|null} */ a, /** @type {number[]|null} */ b) =>
    a === null || b === null || a.some((v) => b.includes(v));
  const samePath = (/** @type {any[]} */ a, /** @type {any[]} */ b) =>
    a.length === b.length && a.every((x, i) => String(x) === String(b[i]));
  const isPrefix = (/** @type {any[]} */ p, /** @type {any[]} */ of) =>
    p.length <= of.length && p.every((x, i) => String(x) === String(of[i]));
  const rangeLabel = (/** @type {number} */ a, /** @type {number} */ b) => (a === b ? String(a) : `${a}–${b}`);

  /** @type {{mode: "create", anchor: number, cur: number} | {mode: "move", sig: any, grab: number, cur: number}
   *   | {mode: "resize", sig: any, edge: "lo"|"hi", cur: number} | null} */
  let drag = null;
  /** @type {number|null} */
  let hoverBit = null;
  /** @type {HTMLElement|null} */
  let layoutEl = null;
  /** @type {HTMLElement|null} */
  let tablesEl = null;

  /** The signal the form shows (a flag's signal too); null for a frame or SDO exchange. */
  function selectedSignal() {
    const f = node.frame;
    if (!f || !["signal", "flag"].includes(node.kind)) return null;
    return f.signals.find((/** @type {any} */ s) => !s.synthetic && isPrefix(s.path, node.path)) ?? null;
  }

  function selectedFlagBits() {
    const s = selectedSignal();
    if (!s || node.kind !== "flag") return [];
    return s.flags[Number(node.path[node.path.length - 1])]?.occupied ?? [];
  }

  /** Bits the dragged signal would take. */
  function preview() {
    const d = drag;
    if (!d) return null;
    let start, length, be = false;
    if (d.mode === "create") {
      start = Math.min(d.anchor, d.cur);
      length = Math.abs(d.cur - d.anchor) + 1;
    } else if (d.mode === "move") {
      be = d.sig.byte_order === "big_endian";
      start = d.sig.start_bit + (d.cur - d.grab);
      length = d.sig.bit_length;
    } else {
      const lo = d.sig.start_bit;
      const hi = lo + d.sig.bit_length - 1;
      start = d.edge === "lo" ? Math.min(d.cur, hi) : lo;
      length = d.edge === "lo" ? hi - start + 1 : Math.max(d.cur, lo) - lo + 1;
    }
    if (start < 0) return null;
    return { start, length, bits: new Set(occupiedBits(start, length, be)) };
  }

  /** Owners of each bit; the dragged signal is shown only as the preview. */
  function cells() {
    const f = node.frame;
    const dragged = drag && drag.mode !== "create" ? drag.sig : null;
    const out = [];
    for (let bit = 0; bit < f.length * 8; bit++) {
      const owners = f.signals.filter((/** @type {any} */ s) => s.occupied.includes(bit) && !(dragged && samePath(s.path, dragged.path)));
      let conflict = false;
      for (let i = 0; i < owners.length && !conflict; i++)
        for (let j = 0; j < i; j++) if (coexist(owners[i].mux, owners[j].mux)) conflict = true;
      const flag = owners.length === 1 ? owners[0].flags.find((/** @type {any} */ x) => x.occupied.includes(bit)) : undefined;
      out.push({ bit, owners, conflict, flag: flag?.name ?? null });
    }
    return out;
  }

  const colorOf = (/** @type {any} */ s) =>
    node.palette[node.frame.signals.indexOf(s) % node.palette.length] ?? "#ccc";

  /** Length handles of the selected little-endian signal in a cell. */
  function handles(/** @type {number} */ bit) {
    const s = selectedSignal();
    if (!s || s.byte_order === "big_endian") return [];
    const out = [];
    if (bit === s.start_bit) out.push("lo");
    if (bit === s.start_bit + s.bit_length - 1) out.push("hi");
    return out;
  }

  /**
   * The grid has three layers in the same cells: signals as bars (one per run of bits of a row),
   * free bits as outlined slots, and over both transparent cells that take the mouse.
   * The names that do not fit in their bar are in the legend below the grid.
   */
  function renderLayout() {
    if (!layoutEl) return;
    const f = node.frame;
    if (!f || !(f.length > 0) || !["frame", "signal", "flag", "sdo"].includes(node.kind)) {
      layoutEl.hidden = true;
      return;
    }
    layoutEl.hidden = false;
    const sel = selectedSignal();
    const flagBits = selectedFlagBits();
    const p = preview();
    const cs = cells();
    const isSel = (/** @type {any} */ s) => !!sel && samePath(s.path, sel.path);
    const grid = el("div", { class: "bitgrid", style: `grid-template-rows: 16px repeat(${f.length}, 24px)` });
    for (let b = 7; b >= 0; b--) grid.append(el("div", { class: "bg-head", style: `grid-column: ${9 - b}` }, String(b)));
    for (let row = 0; row < f.length; row++) {
      grid.append(el("div", { class: "bg-byte", style: `grid-row: ${row + 2}`, title: `Byte ${row}` }, String(row)));
    }

    // Bars: runs of a row with the same owners; the flags of the shown bit field are bars of their own
    /** @param {any} c */
    const key = (c) => {
      const flags = c.owners.length === 1 && isSel(c.owners[0]) ? `#${c.flag ?? ""}` : "";
      return c.owners.map((/** @type {any} */ s) => s.name).join("|") + flags;
    };
    /** @type {HTMLElement[]} */
    const labels = [];
    for (let row = 0; row < f.length; row++) {
      let col = 0;
      while (col < 8) {
        const c = cs[row * 8 + (7 - col)];
        let span = 1;
        while (col + span < 8 && key(cs[row * 8 + (7 - col - span)]) === key(c)) span++;
        if (c.owners.length) {
          const owner = c.owners[0];
          const field = c.owners.length === 1 && isSel(owner) && owner.flags.length > 0;
          const cls = ["bg-bar"];
          if (isSel(owner)) cls.push("selected");
          if (c.conflict) cls.push("conflict");
          if (owner.synthetic) cls.push("synthetic");
          if (field) cls.push(c.flag ? "flag" : "field");
          if (field && c.flag && flagBits.includes(c.bit)) cls.push("flag-selected");
          const name = c.conflict || c.owners.length > 1 ? c.owners.map((/** @type {any} */ s) => s.name).join(" | ")
            : field ? c.flag ?? "" : owner.name;
          const label = el("span", {}, name);
          labels.push(label);
          grid.append(el("div", {
            class: cls.join(" "),
            style: `grid-row: ${row + 2}; grid-column: ${col + 2} / span ${span}; --sig: ${colorOf(owner)}`,
          }, label));
        }
        col += span;
      }
    }

    // Cells over the bars: the mouse, free bits, the dragged position and the length handles
    for (const c of cs) {
      const cls = ["bg-cell"];
      if (!c.owners.length) cls.push("free");
      else if (c.owners.every((s) => s.synthetic)) cls.push("synthetic");
      if (p && p.bits.has(c.bit)) cls.push(c.owners.length ? "preview-bad" : "preview");
      const who = c.owners.map((s) => s.name).join(", ");
      const cell = el("div", {
        class: cls.join(" "),
        style: `grid-row: ${Math.floor(c.bit / 8) + 2}; grid-column: ${9 - (c.bit % 8)}`,
        title: `Bit ${c.bit}` + (who ? ` · ${who}` : "") + (c.flag ? ` · ${c.flag}` : ""),
        onmousedown: (/** @type {MouseEvent} */ e) => onDown(c, e),
        onmouseenter: () => onEnter(c.bit),
      });
      for (const h of handles(c.bit)) cell.append(el("span", { class: `grip ${h}`, "data-edge": h }));
      grid.append(cell);
    }
    grid.addEventListener("mouseleave", () => {
      hoverBit = null;
      status.textContent = statusText();
    });

    const status = el("div", { class: "bitgrid-status" }, statusText());
    layoutEl.replaceChildren(
      el("div", { class: "section-title" }, "Layout",
        el("span", { class: "section-note" }, ` · ${f.name} · ${f.length} bytes`)),
      el("div", { class: "field" }, grid, status, legend(f)),
    );
    // A name that does not fit in its bar is left out: the legend has it
    requestAnimationFrame(() => {
      for (const l of labels) if (l.scrollWidth > l.clientWidth + 1) l.textContent = "";
    });
  }

  /**
   * Signals of the frame: color, name and bits, and the flags of the bit field shown in the form;
   * a click shows the signal or flag in the form.
   */
  function legend(/** @type {any} */ f) {
    const sel = selectedSignal();
    const shown = node.path;
    const bits = (/** @type {number[]} */ occ) => {
      const lo = Math.min(...occ);
      const hi = Math.max(...occ);
      return lo === hi ? `bit ${lo}` : `bits ${rangeLabel(lo, hi)}`;
    };
    const row = (/** @type {any} */ path, /** @type {string} */ cls, /** @type {string} */ color,
      /** @type {string} */ name, /** @type {string} */ where, /** @type {boolean} */ clickable) => el("li", {
      class: [cls, samePath(path, shown) ? "selected" : "", clickable ? "" : "synthetic"].join(" ").trim(),
      title: clickable ? `Show ${name}` : `${name} (SDO)`,
      onclick: () => clickable && vscode.postMessage({ type: "select", path }),
    },
    el("span", { class: "swatch", style: `--sig: ${color}` }),
    el("span", { class: "name" }, name),
    el("span", { class: "bits" }, where));
    const items = [];
    for (const s of f.signals) {
      items.push(row(s.path, "", colorOf(s), s.name, bits(s.occupied), !s.synthetic));
      if (sel && samePath(s.path, sel.path)) {
        s.flags.forEach((/** @type {any} */ x, /** @type {number} */ i) =>
          items.push(row([...s.path, "flags", i], "flag", colorOf(s), x.name, bits(x.occupied), true)));
      }
    }
    return el("ul", { class: "bg-legend" }, items);
  }

  function statusText() {
    const p = preview();
    if (p && drag) {
      const verb = drag.mode === "create" ? "New signal" : drag.mode === "move" ? "Move" : "Length";
      return `${verb}: bits ${rangeLabel(p.start, p.start + p.length - 1)} (${p.length} bit)`;
    }
    if (hoverBit !== null && node?.frame) {
      const b = hoverBit;
      const c = cells()[b];
      const who = c?.owners.map((/** @type {any} */ s) => s.name).join(", ");
      return `Bit ${b} (byte ${Math.floor(b / 8)}, bit ${b % 8})` + (who ? ` · ${who}` : " · free") + (c?.flag ? ` · ${c.flag}` : "");
    }
    return node.kind === "signal" ? "Drag the signal to move it, its edge to change the length."
      : "Drag over free bits to add a signal.";
  }

  function onDown(/** @type {any} */ c, /** @type {MouseEvent} */ e) {
    if (e.button !== 0) return;
    e.preventDefault();
    const sel = selectedSignal();
    const hs = handles(c.bit);
    // The end cell of a longer signal is a handle as a whole; of a one-bit signal only the handle itself
    const grip = /** @type {HTMLElement} */ (e.target).dataset?.edge;
    const h = hs.length === 1 ? hs[0] : grip && hs.includes(grip) ? grip : null;
    if (h && sel) {
      drag = { mode: "resize", sig: sel, edge: /** @type {"lo"|"hi"} */ (h), cur: c.bit };
    } else {
      const own = c.owners.find((/** @type {any} */ s) => sel && samePath(s.path, sel.path)) ?? c.owners[0];
      if (own) {
        if (own.synthetic) return;
        // A click shows the signal in the form; the signal shown is moved by dragging
        if (node.kind !== "signal" || !sel || !samePath(own.path, sel.path)) {
          vscode.postMessage({ type: "select", path: own.path });
          return;
        }
        drag = { mode: "move", sig: own, grab: c.bit, cur: c.bit };
      } else {
        drag = { mode: "create", anchor: c.bit, cur: c.bit };
      }
    }
    renderLayout();
  }

  function onEnter(/** @type {number} */ bit) {
    hoverBit = bit;
    if (drag) {
      if (drag.cur === bit) return;
      drag.cur = bit;
      renderLayout();
    } else {
      const s = layoutEl?.querySelector(".bitgrid-status");
      if (s) s.textContent = statusText();
    }
  }

  function onUp() {
    const d = drag;
    if (!d) return;
    const p = preview();
    drag = null;
    if (p && node?.frame) {
      if (d.mode === "create") {
        addSignal(p.start, p.length);
      } else if ((d.mode === "move" && d.cur !== d.grab) || (d.mode === "resize"
          && (p.start !== d.sig.start_bit || p.length !== d.sig.bit_length))) {
        vscode.postMessage({ type: "ops", ops: [{ op: "set_layout", path: d.sig.path, start_bit: p.start, bit_length: p.length }] });
      }
    }
    renderLayout();
  }

  /** A name not taken by the frame's signals and flags: base, base2, base3… */
  function uniqueName(/** @type {string} */ base) {
    const taken = new Set();
    for (const s of node.frame?.signals ?? []) {
      taken.add(s.name);
      for (const f of s.flags) taken.add(f.name);
    }
    if (!taken.has(base)) return base;
    let i = 2;
    while (taken.has(`${base}${i}`)) i++;
    return `${base}${i}`;
  }

  function addSignal(/** @type {number} */ start, /** @type {number} */ length) {
    const f = node.frame;
    const index = f.signals.filter((/** @type {any} */ s) => !s.synthetic).length;
    const path = [...f.path, "signals", index];
    vscode.postMessage({ type: "ops", select: path, ops: [
      { op: "insert", path: [...f.path, "signals"], value: { name: uniqueName("signal") } },
      { op: "set_layout", path, start_bit: start, bit_length: length },
    ] });
  }

  window.addEventListener("mouseup", onUp);
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drag) {
      drag = null;
      renderLayout();
    }
  });

  // ---------------------------------------------------------------- value table and flags

  /** Text in the document's language: a text written in several languages keeps the others. */
  function localized(/** @type {any} */ old, /** @type {string} */ text) {
    if (old && typeof old === "object") {
      const out = { ...old };
      if (text) out[node.lang] = text;
      else delete out[node.lang];
      return Object.keys(out).length ? out : undefined;
    }
    return text || undefined;
  }

  const ops = (/** @type {any[]} */ list) => vscode.postMessage({ type: "ops", ops: list });

  /** An input of a table: written when it is changed (Enter or leaving it). */
  function cell(/** @type {any} */ value, /** @type {string} */ cls, /** @type {(v: string, input: HTMLInputElement) => void} */ change) {
    const input = /** @type {HTMLInputElement} */ (el("input", { type: "text", class: cls, spellcheck: "false" }));
    input.value = value == null ? "" : String(value);
    input.addEventListener("change", () => change(input.value.trim(), input));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") input.blur();
    });
    return el("td", { class: cls.includes("num") ? "num" : undefined }, input);
  }

  const removeButton = (/** @type {string} */ title, /** @type {() => void} */ onclick) =>
    el("td", { class: "act" }, el("button", { class: "icon-button secondary", title, onclick }, "✕"));

  function valueTable() {
    // Values from a named table of value_tables: edited in the table itself, here only the reference
    if (node.valueTableRef && ["signal", "flag"].includes(node.kind)) {
      return el("div", { class: "section" }, el("div", { class: "section-title" }, "Values"),
        el("div", { class: "field" }, el("div", { class: "empty" },
          `Table "${node.valueTableRef}" from value_tables (edit it there).`)));
    }
    const rowsData = node.valueTable;
    const show = rowsData != null || node.kind === "flag" || ["enum", "flag"].includes(signalEncoding(ctx()));
    if (!show || !["signal", "flag"].includes(node.kind)) return null;
    const p = node.path;
    const hex = node.values.value_format === "hex";
    const fmt = (/** @type {number} */ n) => (hex && n >= 0 ? "0x" + n.toString(16).toUpperCase().padStart(2, "0") : String(n));
    const list = rowsData ?? [];
    const add = () => {
      const used = list.map((/** @type {any} */ r) => r.value).filter((/** @type {any} */ v) => typeof v === "number");
      const k = used.length ? Math.max(...used) + 1 : 0;
      ops(rowsData == null
        ? [{ op: "set", path: [...p, "values"], value: { [k]: `VALUE_${k}` } }]
        : [{ op: "set", path: [...p, "values", String(k)], value: `VALUE_${k}` }]);
    };
    const setEntry = (/** @type {any} */ r, /** @type {string} */ name, /** @type {string} */ description) => {
      const old = r.raw && typeof r.raw === "object" ? { ...r.raw } : {};
      const desc = localized(old.description, description);
      /** @type {any} */
      let value;
      if (desc !== undefined || Object.keys(old).some((k) => k !== "name" && k !== "description")) {
        value = { ...old, name };
        if (desc === undefined) delete value.description;
        else value.description = desc;
      } else {
        value = name;
      }
      ops([{ op: "set", path: [...p, "values", r.key], value }]);
    };
    const body = list.map((/** @type {any} */ r) => el("tr", {},
      cell(r.value != null ? fmt(r.value) : r.key, "mono num", (v, input) => {
        let n;
        try {
          n = parseInteger(v);
        } catch {
          input.value = r.value != null ? fmt(r.value) : r.key;
          return;
        }
        if (n === r.value) return;
        if (list.some((/** @type {any} */ x) => x.value === n)) {
          input.value = fmt(r.value);
          return;
        }
        ops([{ op: "rename_key", path: [...p, "values", r.key], new_key: String(n) }]);
      }),
      cell(r.name, "mono", (v) => v !== r.name && setEntry(r, v, r.description)),
      cell(r.description, "", (v) => v !== r.description && setEntry(r, r.name, v)),
      removeButton("Delete the value", () => ops([list.length === 1
        ? { op: "remove", path: [...p, "values"] }
        : { op: "remove", path: [...p, "values", r.key] }])),
    ));
    return el("div", { class: "section" },
      el("div", { class: "section-title with-action" }, "Values",
        el("button", { class: "link-button", title: "Add a value", onclick: add }, "+ Value")),
      el("div", { class: "field" }, list.length
        ? el("table", { class: "table" },
          el("thead", {}, el("tr", {}, el("th", { class: "num" }, "Value"), el("th", {}, "Name"), el("th", {}, "Description"), el("th", {}))),
          el("tbody", {}, body))
        : el("div", { class: "empty" }, "No values.")));
  }

  function flagsTable() {
    if (node.kind !== "signal" || (node.flags == null && signalEncoding(ctx()) !== "bitfield")) return null;
    const p = node.path;
    const list = node.flags ?? [];
    const add = () => {
      const used = new Set();
      for (const f of list) for (let b = f.bit ?? 0; b < (f.bit ?? 0) + (f.bit_length ?? 1); b++) used.add(b);
      let bit = 0;
      while (used.has(bit)) bit++;
      ops([{ op: "insert", path: [...p, "flags"], value: { bit, name: uniqueName("flag") } }]);
    };
    const setInt = (/** @type {number} */ i, /** @type {string} */ key, /** @type {string} */ v, /** @type {HTMLInputElement} */ input) => {
      let n = null;
      try {
        n = v === "" ? null : parseInteger(v);
        if (n !== null && (key === "bit_length" ? n < 1 || n > 64 : n < 0 || n > 63)) throw new Error();
      } catch {
        input.value = String(list[i]?.[key] ?? (key === "bit_length" ? 1 : ""));
        return;
      }
      if (key === "bit" && n === null) {
        input.value = String(list[i]?.bit ?? "");
        return;
      }
      ops([{ op: "set", path: [...p, "flags", i, key], value: key === "bit_length" && n === 1 ? null : n }]);
    };
    const body = list.map((/** @type {any} */ f, /** @type {number} */ i) => el("tr", {},
      cell(f.bit, "mono num", (v, input) => setInt(i, "bit", v, input)),
      cell(f.bit_length ?? 1, "mono num", (v, input) => setInt(i, "bit_length", v, input)),
      cell(f.name, "mono", (v, input) => {
        if (!v) input.value = f.name ?? "";
        else if (v !== f.name) ops([{ op: "set", path: [...p, "flags", i, "name"], value: v }]);
      }),
      cell(f.description, "", (v) => {
        if (v === f.description) return;
        ops([{ op: "set", path: [...p, "flags", i, "description"], value: localized(f.raw?.description, v) ?? null }]);
      }),
      removeButton("Delete the flag", () => ops([list.length === 1
        ? { op: "remove", path: [...p, "flags"] }
        : { op: "remove", path: [...p, "flags", i] }])),
    ));
    return el("div", { class: "section" },
      el("div", { class: "section-title with-action" }, "Flags",
        el("button", { class: "link-button", title: "Add a flag", onclick: add }, "+ Flag")),
      el("div", { class: "field" }, list.length
        ? el("table", { class: "table" },
          el("thead", {}, el("tr", {}, el("th", { class: "num" }, "Bit"), el("th", { class: "num" }, "Len"),
            el("th", {}, "Name"), el("th", {}, "Description"), el("th", {}))),
          el("tbody", {}, body))
        : el("div", { class: "empty" }, "No flags.")));
  }

  /** The tables are built anew from the node, unless a value is being typed in them. */
  function renderTables() {
    if (!tablesEl) return;
    if (document.hasFocus() && tablesEl.contains(document.activeElement) && document.activeElement?.tagName === "INPUT") return;
    tablesEl.replaceChildren(...[valueTable(), flagsTable()].filter((x) => x !== null));
  }

  function render() {
    app.textContent = "";
    rows = new Map();
    sections = [];
    layoutEl = null;
    tablesEl = null;
    drag = null;
    if (!node) {
      app.append(el("div", { class: "section" }, el("div", { class: "field label" }, "The node is no longer in the map.")));
      return;
    }
    // A node of another file of the map: edited here, the changes go to that file
    if (node.file) {
      app.append(el("div", { class: "section readonly-note" },
        el("div", { class: "field label" }, `From ${node.file.split(/[\\/]/).pop()}: changes go to that file.`),
        el("button", { class: "secondary", onclick: () => vscode.postMessage({ type: "reveal" }) }, "Open in File")));
    }
    layoutEl = el("div", { class: "section layout", hidden: true });
    app.append(layoutEl);
    for (const s of FORMS[node.kind] ?? []) {
      const sec = el("div", { class: "section" }, s.title ? el("div", { class: "section-title" }, s.title) : null);
      const fields = s.fields.map((f) => {
        const r = buildField(f);
        rows.set(f.key, r);
        sec.append(r.row);
        return r;
      });
      sections.push({ el: sec, fields });
      app.append(sec);
    }
    tablesEl = el("div", { class: "tables" });
    app.append(tablesEl);
    if (node.readonly) for (const part of [layoutEl, tablesEl, ...sections.map((s) => s.el)]) part.inert = true;
    if (created) {
      app.append(el("div", { class: "actions" },
        el("button", { onclick: done }, "Done"),
        el("button", { class: "secondary", onclick: () => vscode.postMessage({ type: "discard" }), title: "Delete the new node" }, "Discard")));
    }
  }

  function done() {
    for (const r of rows.values()) if (r.timer !== undefined) commit(r);
    vscode.postMessage({ type: "done" });
  }

  /** Show the node's values; the focused field and fields with unsent typing keep what is typed. */
  function fill() {
    const c = ctx();
    for (const r of rows.values()) {
      const f = r.def;
      const busy = (document.hasFocus() && document.activeElement === r.input) || r.timer !== undefined
        || r.row.classList.contains("invalid");
      const v = node.values[f.key];
      if (f.type === "bool") {
        r.input.checked = !!v;
      } else if (f.type === "select") {
        const opts = optionsOf(f, c);
        const value = v == null ? "" : String(v);
        // A value from YAML that is not among the options stays visible, so it can be changed
        if (value && !opts.some(([o]) => o === value)) opts.push([value, value]);
        // The third element disables an option; the current value stays selectable
        r.input.replaceChildren(...opts.map(([o, label, disabled]) =>
          el("option", { value: o, disabled: !!disabled && o !== value }, label)));
        r.input.value = value;
      } else if (f.type === "devices") {
        const picked = new Set(Array.isArray(v) ? v : v ? [v] : []);
        r.input.replaceChildren(...optionsOf(f, c).map(([name, label]) => {
          const box = /** @type {HTMLInputElement} */ (el("input", { type: "checkbox", value: name }));
          box.checked = picked.has(name);
          box.addEventListener("change", () => {
            send(f.key, [...r.input.querySelectorAll("input:checked")].map((b) => b.value));
          });
          return el("label", { class: "check", title: name }, box, el("span", { class: "sub" }, label));
        }));
      } else {
        if (!busy) r.input.value = formatValue(f.type, v);
        r.input.placeholder = placeholderOf(f, c);
      }
    }
    updateVisibility();
    if (!drag) renderLayout();
    renderTables();
  }

  /** Fields that do not apply are hidden (a field with a value in YAML is always shown), and so are empty sections. */
  function updateVisibility() {
    const c = ctx();
    for (const s of sections) {
      let any = false;
      for (const r of s.fields) {
        r.row.hidden = !(applies(r.def, c) || node.values[r.def.key] != null);
        any ||= !r.row.hidden;
      }
      s.el.hidden = !any;
    }
  }

  function focusFirst() {
    for (const r of rows.values()) {
      if (r.row.hidden || ["bool", "devices", "select"].includes(r.def.type)) continue;
      r.input.focus();
      if (r.input.select) r.input.select();
      return;
    }
  }

  window.addEventListener("message", (event) => {
    const m = event.data;
    if (m.type !== "node") return;
    const path = m.node ? JSON.stringify(m.node.path) : "";
    const rebuild = !m.node || !node || m.node.kind !== shownKind || path !== shownPath || m.created !== created;
    node = m.node;
    created = m.created;
    if (rebuild) {
      shownKind = node?.kind ?? "";
      shownPath = path;
      render();
    }
    if (node) {
      fill();
      if (m.focus) focusFirst();
    }
    // What was drawn, so the extension (and its tests) can tell that the script runs in the webview
    if (rebuild) vscode.postMessage({ type: "rendered", path: node?.path ?? null, fields: [...rows.keys()] });
  });

  vscode.postMessage({ type: "ready" });
})();
