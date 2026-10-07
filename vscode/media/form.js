// Node form (see src/form.ts). Fields are written to the YAML as they are typed: after a short
// pause, on Enter and when a field loses focus. Values from the server never overwrite the field
// being typed in.
// @ts-check
(function () {
  // eslint-disable-next-line no-undef
  const vscode = acquireVsCodeApi();
  const app = /** @type {HTMLElement} */ (document.getElementById("app"));

  const FRAME_TYPES = [
    ["raw", "Raw (explicit ID)"], ["nmt", "NMT"], ["sync", "SYNC"], ["emcy", "EMCY"], ["time", "TIME"],
    ["pdo_tx1", "PDO TX 1"], ["pdo_rx1", "PDO RX 1"], ["pdo_tx2", "PDO TX 2"], ["pdo_rx2", "PDO RX 2"],
    ["pdo_tx3", "PDO TX 3"], ["pdo_rx3", "PDO RX 3"], ["pdo_tx4", "PDO TX 4"], ["pdo_rx4", "PDO RX 4"],
    ["sdo_tx", "SDO TX"], ["sdo_rx", "SDO RX"], ["heartbeat", "Heartbeat"],
  ];
  // Direction of CANopen frame types (as in canopen.py); SYNC and TIME have none
  const TYPE_DIRECTION = {
    nmt: "rx", emcy: "tx", sdo_tx: "tx", sdo_rx: "rx", heartbeat: "tx",
    pdo_tx1: "tx", pdo_tx2: "tx", pdo_tx3: "tx", pdo_tx4: "tx", pdo_rx1: "rx", pdo_rx2: "rx", pdo_rx3: "rx", pdo_rx4: "rx",
  };
  const KINDS = [
    ["enum", "Enum"], ["flag", "Flag"], ["bitfield", "Bit field"], ["metric", "Quantity"],
    ["raw", "Integer"], ["float", "Float (IEEE 754)"], ["bytes", "Bytes"],
  ];
  const KIND_LABEL = Object.fromEntries(KINDS);

  /**
   * @typedef {{protocol: string, owner: string|null, devices: {name: string, label: string}[],
   *   signalKind: string|null, values: Record<string, any>, units: string[][], lang: string}} Ctx
   * @typedef {{key: string, label: string, type: string, half?: boolean, mono?: boolean, required?: boolean,
   *   tip?: string, placeholder?: string | ((c: Ctx) => string), options?: (c: Ctx) => string[][],
   *   when?: (c: Ctx) => boolean}} Field
   * @typedef {{title?: string, fields: Field[]}} Section
   */

  const frameType = (/** @type {Ctx} */ c) => c.values.type ?? "raw";
  const direction = (/** @type {Ctx} */ c) =>
    c.values.direction ?? (c.protocol === "canopen" ? TYPE_DIRECTION[frameType(c)] : undefined) ?? null;
  // Sender and receivers are devices of the bus other than the frame's owner
  const others = (/** @type {Ctx} */ c) => c.devices.filter((d) => d.name !== c.owner).map((d) => [d.name, d.label]);
  const receivers = (/** @type {Ctx} */ c) => others(c).filter(([d]) => d !== c.values.sender);
  const signalKind = (/** @type {Ctx} */ c) => c.values.kind ?? c.signalKind ?? "raw";
  const numeric = (/** @type {Ctx} */ c) => ["metric", "raw", "float"].includes(signalKind(c));
  const byBytes = (/** @type {Ctx} */ c) => c.values.start_bit == null;

  /** @type {Field} */
  const NAME = { key: "name", label: "Identifier", type: "text", required: true, mono: true,
    tip: "Latin letters, digits and _. Used in code, DBC and references." };
  /** @type {Section} */
  const NOTES = { title: "Notes", fields: [
    { key: "description", label: "Description", type: "textarea" },
    { key: "comment", label: "Note", type: "textarea", when: () => false },
  ] };

  /** @type {Record<string, Section[]>} */
  const FORMS = {
    bus: [
      { fields: [
        { key: "title", label: "Name", type: "text", required: true, placeholder: "Body CAN" },
        NAME,
      ] },
      { title: "Bus", fields: [
        { key: "protocol", label: "Protocol", type: "select", half: true,
          options: () => [["canopen", "CANopen"], ["j1939", "SAE J1939"], ["can", "CAN"]] },
        { key: "bitrate", label: "Bitrate", type: "int", half: true, placeholder: "500000", tip: "bit/s" },
        { key: "fd", label: "CAN FD", type: "bool" },
      ] },
      NOTES,
    ],
    device: [
      { fields: [
        { key: "title", label: "Full name", type: "text", required: true, placeholder: "Battery management system" },
        { key: "short", label: "Abbreviation", type: "text", half: true, placeholder: "BMS" },
        { ...NAME, half: true },
      ] },
      { title: "Address", fields: [
        { key: "node_id", label: "Node ID", type: "hex", half: true, placeholder: "0x01", tip: "CANopen node ID, 1..127",
          when: (c) => c.protocol === "canopen" },
        { key: "address", label: "Source address", type: "hex", half: true, placeholder: "0x00", tip: "J1939 address, 0..253",
          when: (c) => c.protocol === "j1939" },
      ] },
      NOTES,
    ],
    frame: [
      { fields: [
        { key: "title", label: "Name", type: "text", placeholder: "Same as identifier" },
        NAME,
      ] },
      { title: "Identification", fields: [
        { key: "type", label: "Type", type: "select", options: () => FRAME_TYPES, when: (c) => c.protocol === "canopen" },
        { key: "id", label: "CAN ID", type: "hex", half: true,
          placeholder: (c) => (c.protocol === "can" ? "0x123" : "Auto"),
          tip: "Empty: computed from the type and node ID (CANopen) or from PGN and SA (J1939)",
          when: (c) => c.protocol !== "canopen" || frameType(c) === "raw" || c.values.id != null },
        { key: "pgn", label: "PGN", type: "hex", half: true, placeholder: "0xF004", when: (c) => c.protocol === "j1939" },
        { key: "priority", label: "Priority", type: "int", half: true, placeholder: "6", when: (c) => c.protocol === "j1939" },
        { key: "extended", label: "29-bit ID", type: "bool",
          when: (c) => c.protocol === "can" || (c.protocol === "canopen" && frameType(c) === "raw") },
      ] },
      { title: "Timing", fields: [
        { key: "dlc", label: "DLC", type: "int", half: true, placeholder: "8", tip: "Data length, bytes" },
        { key: "cycle_ms", label: "Cycle, ms", type: "int", half: true, placeholder: "Event" },
      ] },
      { title: "Routing", fields: [
        { key: "direction", label: "Direction", type: "select",
          options: (c) => [["", c.protocol === "canopen" ? "By type" : "Not set"], ["tx", "TX (sent by the device)"], ["rx", "RX (received by the device)"]],
          when: (c) => !!c.owner && !(c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)]) },
        { key: "sender", label: "Sender", type: "select", options: (c) => [["", "Outside the map"], ...others(c)],
          when: (c) => (!c.owner || direction(c) === "rx") && others(c).length > 0 },
        { key: "receivers", label: "Receivers", type: "devices", options: receivers,
          when: (c) => !(c.owner && direction(c) === "rx") && receivers(c).length > 0 },
      ] },
      NOTES,
    ],
    signal: [
      { fields: [
        { key: "title", label: "Name", type: "text", placeholder: "Same as identifier" },
        NAME,
        { key: "kind", label: "Kind", type: "select",
          options: (c) => [["", c.values.kind == null && c.signalKind ? `Auto (${KIND_LABEL[c.signalKind] ?? c.signalKind})` : "Auto"], ...KINDS] },
      ] },
      { title: "Position", fields: [
        { key: "byte", label: "Byte", type: "int", half: true, placeholder: "0", when: byBytes },
        { key: "bit", label: "Bit", type: "int", half: true, placeholder: "0", tip: "Bit in the byte, 0..7", when: byBytes },
        { key: "start_bit", label: "Start bit", type: "int", half: true, tip: "LSB, lsb0 numbering", when: (c) => !byBytes(c) },
        { key: "bit_length", label: "Length, bits", type: "int", half: true, placeholder: "8",
          when: (c) => c.values.byte_length == null },
        { key: "byte_length", label: "Length, bytes", type: "int", half: true, when: (c) => c.values.byte_length != null },
        { key: "byte_order", label: "Byte order", type: "select",
          options: () => [["", "Little-endian"], ["big_endian", "Big-endian"]], when: (c) => c.protocol === "can" },
      ] },
      { title: "Value", fields: [
        { key: "unit", label: "Unit", type: "unit", half: true, when: numeric },
        { key: "signed", label: "Signed", type: "bool", half: true, when: (c) => ["raw", "metric"].includes(signalKind(c)) },
        { key: "factor", label: "Factor", type: "float", half: true, placeholder: "1", tip: "phys = raw × factor + offset", when: numeric },
        { key: "offset", label: "Offset", type: "float", half: true, placeholder: "0", tip: "phys = raw × factor + offset", when: numeric },
        { key: "min", label: "Min", type: "float", half: true, when: numeric },
        { key: "max", label: "Max", type: "float", half: true, when: numeric },
        { key: "initial", label: "Default", type: "float", half: true, tip: "Physical value",
          when: (c) => !["bitfield", "bytes"].includes(signalKind(c)) },
      ] },
      NOTES,
    ],
    flag: [
      { fields: [
        NAME,
        { key: "bit", label: "Bit", type: "int", half: true, required: true, tip: "Offset from the field's LSB" },
        { key: "bit_length", label: "Length, bits", type: "int", half: true, placeholder: "1" },
      ] },
      NOTES,
    ],
    sdo: [
      { fields: [
        NAME,
        { key: "command", label: "Command", type: "hex", required: true, placeholder: "0x2B" },
        { key: "index", label: "Index", type: "hex", half: true, required: true, placeholder: "0x6040" },
        { key: "subindex", label: "Subindex", type: "hex", half: true, placeholder: "0x00" },
      ] },
      NOTES,
    ],
  };

  const INT_RE = /^[-+]?(0x[0-9a-f]+|[0-9]+)$/i;

  /** Text of a field → value for YAML; null removes the key. Throws on invalid input. */
  function parse(/** @type {Field} */ f, /** @type {string} */ raw) {
    const s = raw.trim();
    if (s === "") {
      if (f.required) throw new Error("Required");
      return null;
    }
    switch (f.type) {
      case "int":
      case "hex": {
        if (!INT_RE.test(s)) throw new Error(f.type === "hex" ? "Number expected: 0x1A or 26" : "Integer expected");
        const neg = s.startsWith("-");
        const body = s.replace(/^[-+]/, "");
        const v = /^0x/i.test(body) ? parseInt(body.slice(2), 16) : Number(body);
        if (!Number.isSafeInteger(v)) throw new Error("Number too large");
        return neg ? -v : v;
      }
      case "float": {
        const v = Number(s.replace(",", "."));
        if (!Number.isFinite(v)) throw new Error("Number expected");
        return v;
      }
      default:
        return s;
    }
  }

  function format(/** @type {Field} */ f, /** @type {any} */ v) {
    if (v === null || v === undefined) return "";
    if (f.type === "hex" && typeof v === "number") return "0x" + v.toString(16).toUpperCase().padStart(2, "0");
    return String(v);
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

  const ctx = () => /** @type {Ctx} */ ({
    protocol: node.protocol, owner: node.owner, devices: node.devices, signalKind: node.signalKind,
    values: node.values, units: node.units ?? [], lang: node.lang,
  });

  function el(/** @type {string} */ tag, /** @type {Record<string, any>} */ props = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") e.className = v;
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
    if (value !== current) send(r.def.key, value);
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
    const r = { def: f, row: null, input: null, error: el("div", { class: "error", hidden: true }), timer: undefined };
    let control;
    if (f.type === "bool") {
      r.input = el("input", { type: "checkbox", id, onchange: () => send(f.key, r.input.checked) });
      control = el("label", { class: "check", for: id, title: f.tip }, r.input, f.label);
    } else if (f.type === "select") {
      r.input = el("select", { id, onchange: () => send(f.key, r.input.value || null) });
      control = r.input;
    } else if (f.type === "devices") {
      r.input = el("div", { class: "checks", id });
      control = r.input;
    } else if (f.type === "unit") {
      control = unitCombo(r, id);
    } else {
      const textarea = f.type === "textarea";
      r.input = el(textarea ? "textarea" : "input", {
        id, type: textarea ? undefined : "text", rows: textarea ? "2" : undefined,
        class: f.mono || f.type === "hex" ? "mono" : undefined,
        spellcheck: textarea || (f.type === "text" && !f.mono) ? undefined : "false",
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
        for: f.type === "devices" ? undefined : id, title: f.tip }, f.label, f.required ? el("span", { class: "req" }, "*") : null);
    r.row = el("div", { class: "field" + (f.half ? " half" : "") }, f.type === "bool" && !f.half ? null : label, control, r.error);
    return r;
  }

  function render() {
    app.textContent = "";
    rows = new Map();
    sections = [];
    if (!node) {
      app.append(el("div", { class: "section" }, el("div", { class: "field label" }, "The node is no longer in the map.")));
      return;
    }
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
        const opts = f.options(c);
        const value = v == null ? "" : String(v);
        // A value from YAML that is not among the options stays visible, so it can be changed
        if (value && !opts.some(([o]) => o === value)) opts.push([value, value]);
        r.input.replaceChildren(...opts.map(([o, label]) => el("option", { value: o }, label)));
        r.input.value = value;
      } else if (f.type === "devices") {
        const picked = new Set(Array.isArray(v) ? v : v ? [v] : []);
        r.input.replaceChildren(...f.options(c).map(([name, label]) => {
          const box = el("input", { type: "checkbox", value: name });
          box.checked = picked.has(name);
          box.addEventListener("change", () => {
            send(f.key, [...r.input.querySelectorAll("input:checked")].map((b) => b.value));
          });
          return el("label", { class: "check", title: name }, box, el("span", { class: "sub" }, label));
        }));
      } else {
        if (!busy) r.input.value = format(f, v);
        const ph = typeof f.placeholder === "function" ? f.placeholder(c) : f.placeholder;
        if (ph) r.input.placeholder = ph;
      }
    }
    updateVisibility();
  }

  /** Fields that do not apply are hidden (a field with a value in YAML is always shown), and so are empty sections. */
  function updateVisibility() {
    const c = ctx();
    for (const s of sections) {
      let any = false;
      for (const r of s.fields) {
        r.row.hidden = !(!r.def.when || r.def.when(c) || node.values[r.def.key] != null);
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
  });

  vscode.postMessage({ type: "ready" });
})();
