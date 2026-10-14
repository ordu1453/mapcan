// Export panel (see src/export.ts): formats, output folder, the Export button and the last result.
// @ts-check
(function () {
  // eslint-disable-next-line no-undef
  const vscode = acquireVsCodeApi();
  const app = /** @type {HTMLElement} */ (document.getElementById("app"));

  const ICON = {
    folder: '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M14.5 4H8.2l-1.4-1.4A.5.5 0 0 0 6.5 2.5h-5a.5.5 0 0 0-.5.5v10a.5.5 0 0 0 .5.5h13a.5.5 0 0 0 .5-.5v-8.5a.5.5 0 0 0-.5-.5zM14 13H2V6h12v7zm0-8H2V3.5h4.3l1.4 1.4c.1.1.2.1.3.1h6V5z"/></svg>',
    file: '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.85 4.44l-3.28-3.3A.5.5 0 0 0 10.21 1H3.5a.5.5 0 0 0-.5.5v13a.5.5 0 0 0 .5.5h10a.5.5 0 0 0 .5-.5V4.8a.5.5 0 0 0-.15-.36zM13 14H4V2h5.5v3a.5.5 0 0 0 .5.5h3V14zm0-9.5h-2.5V2.06L13 4.5z"/></svg>',
    error: '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 13A6 6 0 1 1 8 2a6 6 0 0 1 0 12zm-.5-9h1v4.5h-1V5zm0 5.5h1v1h-1v-1z"/></svg>',
    warning: '<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M8.57 1.86a.65.65 0 0 0-1.14 0L1.08 13.03A.65.65 0 0 0 1.65 14h12.7a.65.65 0 0 0 .57-.97L8.57 1.86zM2.2 13L8 2.8 13.8 13H2.2zM7.5 6h1v4h-1V6zm0 5h1v1h-1v-1z"/></svg>',
  };

  /** @type {any} */
  let state = null;
  /** Formats ticked in the panel (kept while the panel updates). */
  /** @type {Set<string> | null} */
  let picked = null;
  /** @type {HTMLInputElement | null} */
  let folder = null;
  /** @type {HTMLButtonElement | null} */
  let button = null;

  function el(/** @type {string} */ tag, /** @type {Record<string, any>} */ props = {}, ...children) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") e.className = v;
      else if (k === "html") e.innerHTML = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== false) e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c != null) e.append(c);
    return e;
  }

  const icon = (/** @type {keyof typeof ICON} */ name, cls = "") => el("span", { class: `status ${cls}`, html: ICON[name] });

  /** File name and its folder relative to the output folder. */
  function split(/** @type {string} */ f, /** @type {string} */ base) {
    const norm = f.replace(/\\/g, "/");
    const name = norm.split("/").pop() ?? norm;
    const b = base.replace(/\\/g, "/").replace(/\/$/, "");
    const rel = norm.toLowerCase().startsWith(b.toLowerCase() + "/") ? norm.slice(b.length + 1) : norm;
    const dir = rel.includes("/") ? rel.slice(0, rel.lastIndexOf("/")) : "";
    return { name, dir };
  }

  function exportNow() {
    if (!picked || picked.size === 0 || state.busy) return;
    vscode.postMessage({ type: "export", formats: state.formats.map((f) => f.id).filter((id) => picked.has(id)),
      outDir: folder?.value ?? "" });
  }

  function updateButton() {
    if (!button) return;
    const n = picked?.size ?? 0;
    button.disabled = state.busy || n === 0;
    button.textContent = state.busy ? "Exporting…" : "Export";
  }

  function result() {
    const last = state.last;
    if (!last) return null;
    const sec = el("div", { class: "section" });
    if (last.error) {
      sec.append(el("div", { class: "field message error" }, el("span", { html: ICON.error }), el("span", {}, last.error)));
      return sec;
    }
    const files = last.files ?? [];
    sec.append(el("div", { class: "section-title" }, `Exported · ${files.length} file${files.length === 1 ? "" : "s"}`));
    for (const w of last.warnings ?? []) {
      sec.append(el("div", { class: "field message warning" }, el("span", { html: ICON.warning }), el("span", {}, w)));
    }
    sec.append(el("ul", { class: "files field" }, files.map((f) => {
      const { name, dir } = split(f, last.outDir ?? "");
      return el("li", { title: f, onclick: () => vscode.postMessage({ type: "open", file: f }) },
        el("span", { html: ICON.file }), el("span", { class: "name" }, name), dir ? el("span", { class: "dir" }, dir) : null);
    })));
    return sec;
  }

  function render() {
    const typing = document.hasFocus() && document.activeElement === folder ? folder?.value : undefined;
    app.textContent = "";
    folder = null;
    button = null;
    if (!state.map || !state.saved) {
      app.append(el("div", { class: "empty" }, state.map ? "Save the map to export it." : "No map open."));
      return;
    }
    picked ??= new Set(state.picked);

    const formats = el("div", { class: "checks field" });
    for (const f of state.formats) {
      const box = /** @type {HTMLInputElement} */ (el("input", { type: "checkbox", onchange: () => {
        if (box.checked) picked?.add(f.id); else picked?.delete(f.id);
        updateButton();
      } }));
      box.checked = picked.has(f.id);
      formats.append(el("label", { class: "check", title: f.detail }, box, el("span", { class: "sub" }, f.label)));
    }
    app.append(el("div", { class: "section" }, el("div", { class: "section-title" }, "Formats"), formats));

    folder = /** @type {HTMLInputElement} */ (el("input", { type: "text", id: "out", spellcheck: "false",
      title: "Relative to the map's folder", onkeydown: (/** @type {KeyboardEvent} */ e) => e.key === "Enter" && exportNow() }));
    folder.value = typing ?? state.outDir;
    const browse = el("button", { class: "secondary icon-button", title: "Choose folder…", html: ICON.folder,
      onclick: () => vscode.postMessage({ type: "browse" }) });
    button = /** @type {HTMLButtonElement} */ (el("button", { onclick: exportNow, title: `From the current text of ${state.map}` }));
    app.append(el("div", { class: "section" },
      el("div", { class: "field" }, el("label", { for: "out" }, "Output folder"), el("div", { class: "row" }, folder, browse)),
      el("div", { class: "field actions" }, button)));
    updateButton();

    const r = result();
    if (r) app.append(r);
    if (typing !== undefined) folder.focus();
    // What was drawn, counted in the page, for the extension's tests
    vscode.postMessage({ type: "rendered", formats: app.querySelectorAll('input[type="checkbox"]').length });
  }

  window.addEventListener("message", (event) => {
    // The panel is told about every change of the map; it is redrawn only when its own state changes
    if (event.data.type !== "state" || JSON.stringify(event.data) === JSON.stringify(state)) return;
    state = event.data;
    render();
  });

  vscode.postMessage({ type: "ready" });
})();
