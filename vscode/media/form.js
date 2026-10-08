// Node form (see src/form.ts). Fields are written to the YAML as they are typed: after a short
// pause, on Enter and when a field loses focus. Values from the server never overwrite the field
// being typed in.
// @ts-check
(function () {
  // eslint-disable-next-line no-undef
  const vscode = acquireVsCodeApi();
  const app = /** @type {HTMLElement} */ (document.getElementById("app"));

  // Direction of CANopen frame types (as in canopen.py); SYNC and TIME have none
  // Service frames of CANopen whose length the type fixes (CiA 301, as in canopen.py)
  const FIXED_DLC = ["nmt", "time", "heartbeat", "sdo_tx", "sdo_rx"];
  const TYPE_DIRECTION = {
    nmt: "rx", emcy: "tx", sdo_tx: "tx", sdo_rx: "rx", heartbeat: "tx",
    pdo_tx1: "tx", pdo_tx2: "tx", pdo_tx3: "tx", pdo_tx4: "tx", pdo_rx1: "rx", pdo_rx2: "rx", pdo_rx3: "rx", pdo_rx4: "rx",
  };
  const ENCODINGS = [
    ["enum", "Enum"], ["flag", "Flag"], ["bitfield", "Bit field"], ["metric", "Quantity"],
    ["raw", "Integer"], ["float", "Float (IEEE 754)"], ["bytes", "Bytes"],
  ];

  /**
   * @typedef {{protocol: string, owner: string|null, devices: {name: string, label: string}[],
   *   signalEncoding: string|null, frameDirection: string|null, bitLength: number|null, hasSelector: boolean, values: Record<string, any>,
   *   units: string[][], lang: string, frameTypes: {type: string, label: string, taken: string|null}[]}} Ctx
   * @typedef {{key: string, label: string, type: string, half?: boolean, mono?: boolean, required?: boolean,
   *   numeric?: boolean,
   *   tip?: string, placeholder?: string | ((c: Ctx) => string), options?: (c: Ctx) => string[][],
   *   when?: (c: Ctx) => boolean}} Field
   * @typedef {{title?: string, fields: Field[]}} Section
   */

  const frameType = (/** @type {Ctx} */ c) => c.values.type ?? "raw";
  const direction = (/** @type {Ctx} */ c) =>
    c.values.direction ?? (c.protocol === "canopen" ? TYPE_DIRECTION[frameType(c)] : undefined) ?? null;
  // Empty direction: the one computed from the type (CANopen) or from sender, shown in brackets
  const defaultDirection = (/** @type {Ctx} */ c) => {
    const base = c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)] ? "By type" : "Default";
    return c.values.direction == null && c.frameDirection ? `${base} (${c.frameDirection.toUpperCase()})` : base;
  };
  // Sender and receivers are devices of the bus other than the frame's owner
  const others = (/** @type {Ctx} */ c) => c.devices.filter((d) => d.name !== c.owner).map((d) => [d.name, d.label]);
  const receivers = (/** @type {Ctx} */ c) => others(c).filter(([d]) => d !== c.values.sender);
  const signalEncoding = (/** @type {Ctx} */ c) => c.values.encoding ?? c.signalEncoding ?? "raw";
  const numeric = (/** @type {Ctx} */ c) => ["metric", "raw", "float"].includes(signalEncoding(c));
  const byBytes = (/** @type {Ctx} */ c) => c.values.start_bit == null;
  // Length as typed in the form, else as the server computed it from the map
  const bitLength = (/** @type {Ctx} */ c) =>
    c.values.bit_length ?? (c.values.byte_length != null ? c.values.byte_length * 8 : c.bitLength);
  // Byte order matters for a value longer than a byte (any protocol: the format allows big-endian everywhere)
  const multiByte = (/** @type {Ctx} */ c) => !["flag", "bytes"].includes(signalEncoding(c)) && (bitLength(c) ?? 0) > 8;
  // The bit in the byte matters only for a value shorter than a byte
  const subByte = (/** @type {Ctx} */ c) => signalEncoding(c) === "flag" || (bitLength(c) ?? 8) < 8;
  // The SDO exchange's value: its other fields appear once it has an identifier
  const hasValue = (/** @type {Ctx} */ c) => c.values["value.name"] != null;

  /** @type {Field} */
  const NAME = { key: "name", label: "Identifier", type: "text", required: true, mono: true,
    tip: "Latin letters, digits and _. Used in code, DBC and references." };
  /** @type {Field} */
  const DESCRIPTION = { key: "description", label: "Description", type: "textarea" };
  /** @type {Section} */
  const NOTES = { title: "Notes", fields: [DESCRIPTION] };
  /** Frames and signals also have a note (a remark under the description in documents). */
  /** @type {Section} */
  const NOTES_COMMENT = { title: "Notes", fields: [DESCRIPTION, { key: "comment", label: "Note", type: "textarea" }] };

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
        { key: "interface", label: "Interface", type: "text", half: true, placeholder: "can0" },
        { key: "fd", label: "CAN FD", type: "bool", half: true },
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
        // Types from the server: a frame of the bus has no node-specific types; a type whose CAN ID
        // another frame already has is disabled and names that frame
        { key: "type", label: "Type", type: "select", when: (c) => c.protocol === "canopen",
          options: (c) => c.frameTypes.map((t) => [t.type, t.taken ? `${t.label} — ${t.taken}` : t.label, !!t.taken]) },
        { key: "id", label: "CAN ID", type: "hex", half: true,
          placeholder: (c) => (c.protocol === "can" ? "0x123" : "Auto"),
          tip: "Empty: computed from the type and node ID (CANopen) or from PGN and SA (J1939)",
          when: (c) => c.protocol !== "canopen" || frameType(c) === "raw" || c.values.id != null },
        { key: "pgn", label: "PGN", type: "hex", half: true, placeholder: "0xF004", when: (c) => c.protocol === "j1939" },
        { key: "priority", label: "Priority", type: "int", half: true, placeholder: "6", tip: "0..7", when: (c) => c.protocol === "j1939" },
        { key: "destination", label: "Destination (DA)", type: "hex", half: true, placeholder: "0xFF",
          tip: "PDU1 PGN only; empty: 0xFF (global)",
          when: (c) => c.protocol === "j1939" && c.values.pgn != null && ((c.values.pgn >> 8) & 0xff) < 240 },
        { key: "extended", label: "29-bit ID", type: "bool",
          when: (c) => c.protocol === "can" || (c.protocol === "canopen" && frameType(c) === "raw") },
      ] },
      { title: "Timing", fields: [
        { key: "dlc", label: "DLC", type: "int", half: true, placeholder: "8", tip: "Data length, bytes",
          when: (c) => !(c.protocol === "canopen" && FIXED_DLC.includes(frameType(c))) },
        { key: "cycle_ms", label: "Cycle, ms", type: "int", half: true, placeholder: "Not cyclic",
          tip: "Cyclic transmission period", when: (c) => c.values.trigger == null },
        { key: "trigger", label: "Trigger", type: "select", half: true, when: (c) => c.values.cycle_ms == null,
          options: () => [["", "Not set"], ["event", "On event"], ["on_request", "On request"]] },
      ] },
      { title: "Routing", fields: [
        { key: "direction", label: "Direction", type: "select",
          options: (c) => [["", defaultDirection(c)], ["tx", "TX (sent by the device)"], ["rx", "RX (received by the device)"]],
          when: (c) => !!c.owner && !(c.protocol === "canopen" && TYPE_DIRECTION[frameType(c)]) },
        { key: "sender", label: "Sender", type: "select", options: (c) => [["", "Outside the map"], ...others(c)],
          when: (c) => (!c.owner || direction(c) === "rx") && others(c).length > 0 },
        { key: "receivers", label: "Receivers", type: "devices", options: receivers,
          when: (c) => !(c.owner && direction(c) === "rx") && receivers(c).length > 0 },
      ] },
      NOTES_COMMENT,
    ],
    signal: [
      { fields: [
        { key: "title", label: "Name", type: "text", placeholder: "Same as identifier" },
        NAME,
        { key: "encoding", label: "Encoding", type: "select",
          options: (c) => (c.values.encoding == null ? [["", "Not set"], ...ENCODINGS] : ENCODINGS) },
      ] },
      { title: "Position", fields: [
        { key: "byte", label: "Byte", type: "int", half: true, placeholder: "0", when: byBytes },
        { key: "bit", label: "Bit", type: "int", half: true, placeholder: "0", tip: "Bit in the byte, 0..7",
          when: (c) => byBytes(c) && subByte(c) },
        { key: "start_bit", label: "Start bit", type: "int", half: true, tip: "LSB, lsb0 numbering", when: (c) => !byBytes(c) },
        { key: "bit_length", label: "Length, bits", type: "int", half: true,
          when: (c) => c.values.byte_length == null && signalEncoding(c) !== "flag" },
        { key: "byte_length", label: "Length, bytes", type: "int", half: true, when: (c) => c.values.byte_length != null },
        { key: "byte_order", label: "Byte order", type: "select",
          options: () => [["", "Little-endian (Intel)"], ["big_endian", "Big-endian (Motorola)"]], when: multiByte },
      ] },
      { title: "Value", fields: [
        { key: "unit", label: "Unit", type: "unit", half: true, when: numeric },
        { key: "signed", label: "Signed", type: "bool", half: true, when: (c) => ["raw", "metric"].includes(signalEncoding(c)) },
        { key: "signed_code", label: "Signed code", type: "select", half: true,
          options: () => [["", "Two's complement"], ["ones_complement", "Ones' complement"], ["sign_magnitude", "Sign and magnitude"]],
          when: (c) => !!c.values.signed },
        { key: "factor", label: "Factor", type: "float", half: true, placeholder: "1", tip: "phys = raw × factor + offset", when: numeric },
        { key: "offset", label: "Offset", type: "float", half: true, placeholder: "0", tip: "phys = raw × factor + offset", when: numeric },
        { key: "min", label: "Min", type: "float", half: true, when: numeric },
        { key: "max", label: "Max", type: "float", half: true, when: numeric },
        { key: "initial", label: "Default", type: "float", half: true, tip: "Physical value",
          when: (c) => !["bitfield", "bytes"].includes(signalEncoding(c)) },
        { key: "invalid", label: "No data (raw)", type: "intlist", half: true, mono: true, placeholder: "0xFF",
          tip: "Raw value(s) meaning \"no data\": 0xFF or 0xFE, 0xFF", when: (c) => ["raw", "metric", "enum"].includes(signalEncoding(c)) },
        { key: "value_format", label: "Values in documents", type: "select", half: true,
          options: () => [["", "Decimal"], ["hex", "Hex"]], when: (c) => signalEncoding(c) === "enum" },
      ] },
      { title: "Multiplexing", fields: [
        { key: "multiplexer", label: "Multiplexer selector", type: "bool",
          tip: "The signal selects which multiplexed signals the frame carries",
          when: (c) => ["raw", "enum"].includes(signalEncoding(c)) && !c.hasSelector },
        { key: "mux", label: "Selector values", type: "intlist", mono: true, placeholder: "0 or 1, 2",
          tip: "Values of the frame's selector at which the signal is present", when: (c) => c.hasSelector },
      ] },
      NOTES_COMMENT,
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
      { title: "Value", fields: [
        { key: "value.name", label: "Identifier", type: "text", mono: true,
          tip: "Empty: the exchange carries no value" },
        { key: "value.encoding", label: "Encoding", type: "select", when: hasValue,
          options: (c) => [...(c.values["value.encoding"] == null ? [["", "Not set"]] : []),
            ["enum", "Enum"], ["metric", "Quantity"], ["raw", "Integer"]] },
        { key: "value.bit_length", label: "Length, bits", type: "select", half: true, numeric: true,
          options: (c) => [...(c.values["value.bit_length"] == null ? [["", "Not set"]] : []),
            ["8", "8"], ["16", "16"], ["24", "24"], ["32", "32"]], when: hasValue },
        { key: "value.unit", label: "Unit", type: "unit", half: true, when: hasValue },
        { key: "value.factor", label: "Factor", type: "float", half: true, placeholder: "1", when: hasValue },
        { key: "value.offset", label: "Offset", type: "float", half: true, placeholder: "0", when: hasValue },
      ] },
      NOTES,
    ],
  };

  const INT_RE = /^[-+]?(0x[0-9a-f]+|[0-9]+)$/i;

  /** Text of a field → value for YAML; null removes the key. Throws on invalid input. */
  function parseInt_(/** @type {string} */ s, /** @type {string} */ message) {
    if (!INT_RE.test(s)) throw new Error(message);
    const neg = s.startsWith("-");
    const body = s.replace(/^[-+]/, "");
    const v = /^0x/i.test(body) ? parseInt(body.slice(2), 16) : Number(body);
    if (!Number.isSafeInteger(v)) throw new Error("Number too large");
    return neg ? -v : v;
  }

  function parse(/** @type {Field} */ f, /** @type {string} */ raw) {
    const s = raw.trim();
    if (s === "") {
      if (f.required) throw new Error("Required");
      return null;
    }
    switch (f.type) {
      case "int":
      case "hex":
        return parseInt_(s, f.type === "hex" ? "Number expected: 0x1A or 26" : "Integer expected");
      case "intlist": {
        // One value is written as a number, several as a list
        const parts = s.split(/[\s,;]+/).filter(Boolean).map((x) => parseInt_(x, "Integers expected: 1 or 1, 2"));
        return parts.length === 1 ? parts[0] : parts;
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
    if (Array.isArray(v)) return v.join(", ");
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
    protocol: node.protocol, owner: node.owner, devices: node.devices, signalEncoding: node.signalEncoding, frameDirection: node.frameDirection,
    bitLength: node.bitLength ?? null, hasSelector: !!node.hasSelector,
    values: node.values, units: node.units ?? [], lang: node.lang, frameTypes: node.frameTypes ?? [],
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
    const r = { def: f, row: null, input: null, error: el("div", { class: "error", hidden: true }), timer: undefined };
    let control;
    if (f.type === "bool") {
      r.input = el("input", { type: "checkbox", id, onchange: () => send(f.key, r.input.checked) });
      control = el("label", { class: "check", for: id, title: f.tip }, r.input, f.label);
    } else if (f.type === "select") {
      r.input = el("select", { id, onchange: () => {
        const v = r.input.value;
        send(f.key, v === "" ? null : f.numeric ? Number(v) : v);
      } });
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
    for (let bit = 0; bit < f.dlc * 8; bit++) {
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
    if (!f || !(f.dlc > 0) || !["frame", "signal", "flag", "sdo"].includes(node.kind)) {
      layoutEl.hidden = true;
      return;
    }
    layoutEl.hidden = false;
    const sel = selectedSignal();
    const flagBits = selectedFlagBits();
    const p = preview();
    const cs = cells();
    const isSel = (/** @type {any} */ s) => !!sel && samePath(s.path, sel.path);
    const grid = el("div", { class: "bitgrid", style: `grid-template-rows: 16px repeat(${f.dlc}, 24px)` });
    for (let b = 7; b >= 0; b--) grid.append(el("div", { class: "bg-head", style: `grid-column: ${9 - b}` }, String(b)));
    for (let row = 0; row < f.dlc; row++) {
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
    for (let row = 0; row < f.dlc; row++) {
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
        el("span", { class: "section-note" }, ` · ${f.name} · DLC ${f.dlc}`)),
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
          n = parseInt_(v, "");
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
        n = v === "" ? null : parseInt_(v, "");
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
        // The third element disables an option; the current value stays selectable
        r.input.replaceChildren(...opts.map(([o, label, disabled]) =>
          el("option", { value: o, disabled: !!disabled && o !== value }, label)));
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
    if (!drag) renderLayout();
    renderTables();
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
