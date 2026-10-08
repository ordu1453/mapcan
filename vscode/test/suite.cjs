// Runs inside the Extension Development Host (see runTest.mjs).
const assert = require("node:assert/strict");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");

const workspace = process.env.MAPCAN_TEST_WORKSPACE;
const example = path.resolve(__dirname, "..", "..", "examples", "minimal.yaml");

async function until(what, fn, timeout = 30000) {
  const end = Date.now() + timeout;
  for (;;) {
    const value = await fn();
    if (value) return value;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 200));
  }
}

function positionOf(doc, text, offset = 1) {
  return doc.positionAt(doc.getText().indexOf(text) + offset);
}

const tests = {
  async "activates and shows the map tree"(ctx) {
    const roots = await until("tree", () => {
      const r = ctx.api.tree.getChildren();
      return r.length ? r : undefined;
    });
    const bus = ctx.api.tree.getTreeItem(roots[0]);
    // Titles, as in the web editor; the identifier is in the tooltip
    assert.deepEqual([bus.label, bus.description, bus.tooltip], ["Demo bus", "", "Bus demo"]);
    const device = ctx.api.tree.getChildren(roots[0])[0];
    assert.equal(ctx.api.tree.getTreeItem(device).label, "PMP · Pump");
    const frame = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(device)[0]);
    assert.deepEqual([frame.label, frame.description, frame.tooltip], ["pump_state", "0x1A1", "Frame pump_state\nTX"]);
    assert.match(frame.iconPath.dark.path, /tree\/dark\/frame-tx\.svg$/);
    assert.ok(fs.existsSync(frame.iconPath.dark.fsPath));
    assert.equal(ctx.api.tree.mapUri.toString(), ctx.doc.uri.toString());
  },

  async "clicking a node selects its whole lines"(ctx) {
    const device = ctx.api.tree.getChildren(ctx.api.tree.getChildren()[0])[0];
    const signal = ctx.api.tree.getChildren(ctx.api.tree.getChildren(device)[0])[0];
    const item = ctx.api.tree.getTreeItem(signal);
    await vscode.commands.executeCommand(item.command.command, ...item.command.arguments);
    const sel = vscode.window.activeTextEditor.selection;
    assert.equal(sel.active.character, 0);
    assert.equal(sel.end.character, 0);
    const text = ctx.doc.getText(sel);
    assert.match(text, /^ {14}- name: mode {12}# enum, byte 0\n/);
    assert.match(text, /2: \{name: FAULT, description: fault\}\n$/);
  },

  async "hover shows the frame layout"(ctx) {
    const hovers = await vscode.commands.executeCommand(
      "vscode.executeHoverProvider", ctx.doc.uri, positionOf(ctx.doc, "pump_state", 3));
    const text = hovers.flatMap((h) => h.contents.map((c) => c.value ?? c)).join("\n");
    assert.match(text, /\*\*pump_state\*\* · `0x1A1`/);
    assert.match(text, /\| Byte \| 7 \|/);
  },

  async "inlay hints show IDs and bits"(ctx) {
    const range = new vscode.Range(0, 0, ctx.doc.lineCount, 0);
    const hints = await vscode.commands.executeCommand("vscode.executeInlayHintProvider", ctx.doc.uri, range);
    const labels = hints.map((h) => (typeof h.label === "string" ? h.label : h.label.map((p) => p.value).join("")));
    assert.ok(labels.includes("→ 0x1A1"), labels.join(", "));
    assert.ok(labels.includes("bits 16–31"), labels.join(", "));
  },

  async "completion offers enum values"(ctx) {
    const pos = positionOf(ctx.doc, "byte_order: big_endian", "byte_order: ".length);
    const list = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", ctx.doc.uri, pos);
    const labels = list.items.map((i) => (typeof i.label === "string" ? i.label : i.label.label));
    assert.ok(labels.includes("little_endian"), labels.slice(0, 20).join(", "));
  },

  async "export writes files from the current text"(ctx) {
    const outDir = path.join(workspace, "build");
    const result = await vscode.commands.executeCommand("mapcan.lsp.export",
      { uri: ctx.doc.uri.toString(), formats: ["dbc", "md"], outDir });
    assert.equal(result.error, undefined);
    assert.ok(fs.existsSync(path.join(outDir, "dbc", "demo.dbc")));
    assert.ok(fs.existsSync(path.join(outDir, "minimal.md")));
  },

  async "tree commands add, duplicate and delete nodes"(ctx) {
    const tree = ctx.api.tree;
    const frame = () => tree.getChildren(tree.getChildren(tree.getChildren()[0])[0])[0];
    const before = ctx.doc.getText();
    await vscode.commands.executeCommand("mapcan.addSignal", frame());
    assert.match(ctx.doc.getText(), /\n {14}- name: signal\n {16}encoding: raw\n {16}start_bit: 60\n {16}bit_length: 1\n/);
    assert.equal(vscode.window.activeTextEditor.document.getText(vscode.window.activeTextEditor.selection), "signal");
    await until("tree with the new signal", () => frame().children.some((s) => s.raw.label === "signal"));
    const added = frame().children.find((s) => s.raw.label === "signal");
    await vscode.commands.executeCommand("mapcan.duplicateNode", added);
    assert.match(ctx.doc.getText(), /- name: signal_copy\n/);
    await until("tree with the copy", () => frame().children.some((s) => s.raw.label === "signal_copy"));
    for (const label of ["signal_copy", "signal"]) {
      await vscode.commands.executeCommand("mapcan.deleteNode", frame().children.find((s) => s.raw.label === label));
      await until(`tree without ${label}`, () => !frame().children.some((s) => s.raw.label === label));
    }
    assert.equal(ctx.doc.getText(), before);
  },

  async "a frame added to a CANopen device gets the first free PDO type"(ctx) {
    const tree = ctx.api.tree;
    const device = () => tree.getChildren(tree.getChildren()[0])[0];
    const before = ctx.doc.getText();
    await vscode.commands.executeCommand("mapcan.addFrame", device());
    assert.match(ctx.doc.getText(), /\n {10}- name: pump_frame\n {12}type: pdo_tx2\n {12}dlc: 8\n {12}cycle_ms: 100\n {12}signals: \[\]\n/);
    const added = await until("new frame", () => device().children.find((f) => f.raw.ident === "pump_frame"));
    await vscode.commands.executeCommand("mapcan.closeForm");
    await vscode.commands.executeCommand("mapcan.deleteNode", added);
    await until("tree without the frame", () => !device().children.some((f) => f.raw.ident === "pump_frame"));
    assert.equal(ctx.doc.getText(), before);
  },

  async "a node added with + opens in the form, which writes fields to the YAML"(ctx) {
    const tree = ctx.api.tree;
    const form = ctx.api.form;
    const frame = () => tree.getChildren(tree.getChildren(tree.getChildren()[0])[0])[0];
    const before = ctx.doc.getText();
    await vscode.commands.executeCommand("mapcan.addSignal", frame());
    const added = await until("new signal", () => frame().children.find((s) => s.raw.ident === "signal"));
    assert.deepEqual(form.openPath, added.path);
    const set = (key, value) => vscode.commands.executeCommand("mapcan.lsp.set",
      { uri: ctx.doc.uri.toString(), path: [...added.path, key], value });
    const result = await set("title", "Battery voltage");
    const edit = new vscode.WorkspaceEdit();
    for (const e of result.edits) edit.replace(ctx.doc.uri, new vscode.Range(...e.range), e.text);
    await vscode.workspace.applyEdit(edit);
    assert.match(ctx.doc.getText(), /- name: signal\n {16}encoding: raw\n {16}start_bit: 60\n {16}bit_length: 1\n {16}title: Battery voltage\n/);
    await until("tree with the title", () => frame().children.some((s) => s.raw.label === "Battery voltage"));
    await vscode.commands.executeCommand("mapcan.deleteNode", frame().children.find((s) => s.raw.ident === "signal"));
    assert.equal(form.openPath, undefined);
    await until("tree without the signal", () => !frame().children.some((s) => s.raw.ident === "signal"));
    assert.equal(ctx.doc.getText(), before);
    await vscode.commands.executeCommand("mapcan.export");
  },

  async "quick fix corrects a decimal comma"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    const at = positionOf(ctx.doc, "factor: 0.01", "factor: 0".length);
    await editor.edit((e) => e.replace(new vscode.Range(at, at.translate(0, 1)), ","));
    const diag = await until("number-comma", () =>
      vscode.languages.getDiagnostics(ctx.doc.uri).find((d) => d.code === "number-comma"));
    const actions = await vscode.commands.executeCommand(
      "vscode.executeCodeActionProvider", ctx.doc.uri, diag.range, vscode.CodeActionKind.QuickFix.value);
    const fix = actions.find((a) => a.title === "Change to 0.01");
    assert.ok(fix, actions.map((a) => a.title).join(", "));
    await vscode.workspace.applyEdit(fix.edit);
    assert.match(ctx.doc.getText(), /factor: 0\.01\n/);
    await until("no diagnostics", () => vscode.languages.getDiagnostics(ctx.doc.uri).every((d) => d.severity > 1));
  },

  async "problems color the tree"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    const at = positionOf(ctx.doc, "start_bit: 56", "start_bit: ".length);
    await editor.edit((e) => e.replace(new vscode.Range(at, at.translate(0, 2)), "0"));
    const tree = ctx.api.tree;
    const counter = () => tree.getChildren(tree.getChildren(tree.getChildren()[0])[0])[0].children
      .find((s) => s.raw.label === "counter");
    const item = await until("decorated counter", () => {
      const it = tree.getTreeItem(counter());
      return it.resourceUri ? it : undefined;
    });
    const deco = tree.provideFileDecoration(item.resourceUri);
    assert.equal(deco.badge, "1");
    assert.equal(deco.color.id, "list.errorForeground");
    const diag = vscode.languages.getDiagnostics(ctx.doc.uri).find((d) => d.code === "bit-overlap");
    const actions = await vscode.commands.executeCommand(
      "vscode.executeCodeActionProvider", ctx.doc.uri, diag.range, vscode.CodeActionKind.QuickFix.value);
    await vscode.workspace.applyEdit(actions.find((a) => a.title.startsWith("Move to free bits")).edit);
    assert.match(ctx.doc.getText(), /start_bit: 56\n/);
    await until("tree without problems", () => !tree.getTreeItem(counter()).resourceUri);
  },

  async "definition, references and rename follow devices"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    const at = positionOf(ctx.doc, "            cycle_ms: 100", 0);
    await editor.edit((e) => e.insert(at, "            receivers: [pump]\n"));
    const ref = positionOf(ctx.doc, "receivers: [pump]", "receivers: [".length + 1);
    const defs = await vscode.commands.executeCommand("vscode.executeDefinitionProvider", ctx.doc.uri, ref);
    const def = defs[0].targetRange ?? defs[0].range;
    assert.equal(ctx.doc.lineAt(def.start.line).text.trim(), "- name: pump");
    const refs = await vscode.commands.executeCommand("vscode.executeReferenceProvider", ctx.doc.uri, ref);
    assert.equal(refs.length, 2);
    const edit = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", ctx.doc.uri, ref, "motor");
    await vscode.workspace.applyEdit(edit);
    assert.match(ctx.doc.getText(), /- name: motor\n/);
    assert.match(ctx.doc.getText(), /receivers: \[motor\]/);
    await vscode.commands.executeCommand("undo");
    await vscode.commands.executeCommand("undo");
    assert.ok(!ctx.doc.getText().includes("receivers: [pump]"));
  },

  async "snippets are offered after a dash"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    const end = ctx.doc.lineAt(ctx.doc.lineCount - 1).range.end;
    await editor.edit((e) => e.insert(end, "\n              - "));
    const pos = ctx.doc.lineAt(ctx.doc.lineCount - 1).range.end;
    const list = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", ctx.doc.uri, pos);
    const signal = list.items.find((i) => (i.label.label ?? i.label) === "signal enum");
    assert.ok(signal, list.items.map((i) => i.label.label ?? i.label).join(", "));
    assert.match(signal.insertText.value ?? signal.textEdit?.newText, /^name: \$\{1:state\}\n {2}description/);
    await vscode.commands.executeCommand("undo");
  },

  async "preview and comparison render Markdown"(ctx) {
    // The previous test undoes an edit; the preview needs the server to have checked the map again
    await until("no errors", () => vscode.languages.getDiagnostics(ctx.doc.uri).every((d) => d.severity > 0));
    await vscode.commands.executeCommand("mapcan.openPreview");
    const uri = vscode.Uri.from({ scheme: "mapcan-preview", path: "/minimal.md", query: ctx.doc.uri.toString() });
    const preview = await vscode.workspace.openTextDocument(uri);
    assert.match(preview.getText(), /pump_state/);
    const old = fs.readFileSync(example, "utf8").replace("name: pressure", "name: pressure_old");
    const diff = await vscode.commands.executeCommand("mapcan.lsp.diff", { uri: ctx.doc.uri.toString(), oldText: old });
    assert.match(diff.text, /pressure/);
  },

  async "history lists commits and compares versions"(ctx) {
    // A map of its own in a repository of its own, so the edits of other tests do not matter
    const repo = path.join(workspace, "repo");
    fs.mkdirSync(repo);
    const file = path.join(repo, "pump.yaml");
    const original = fs.readFileSync(example, "utf8");
    const git = (...args) => execFileSync("git",
      ["-c", "user.name=Test", "-c", "user.email=test@example.com", ...args], { cwd: repo, encoding: "utf8" });
    git("init", "-q");
    fs.writeFileSync(file, original.replace("name: pressure", "name: pressure_old"));
    git("add", "pump.yaml");
    git("commit", "-q", "-m", "Add map");
    fs.writeFileSync(file, original);
    git("commit", "-q", "-am", "Rename pressure");
    const doc = await vscode.workspace.openTextDocument(file);
    await vscode.window.showTextDocument(doc);
    await until("map in the tree", () => ctx.api.tree.mapUri?.toString() === doc.uri.toString());

    const history = ctx.api.history;
    await vscode.commands.executeCommand("mapcan.history.focus");
    await vscode.commands.executeCommand("mapcan.history.refresh");
    const commits = await until("commits", () => (history.commits.length === 2 ? history.commits : undefined));
    assert.deepEqual(commits.map((c) => c.subject), ["Rename pressure", "Add map"]);
    assert.equal(commits[1].parentPath, undefined);
    assert.equal(history.getTreeItem(commits[1]).contextValue, "commit.added");

    // Every comparison goes to the same Changes tab, which does not take the focus
    const groups = vscode.window.tabGroups.all.length;
    await vscode.commands.executeCommand("mapcan.history.showCommitChanges", commits[0]);
    assert.match(ctx.api.changes.markdown, /pressure/);
    ctx.api.changes.markdown = undefined;
    await vscode.commands.executeCommand("mapcan.history.showChangesSince", commits[1]);
    assert.match(ctx.api.changes.markdown, /pressure/);
    await vscode.commands.executeCommand("mapcan.history.showChangesSince", commits[0]);
    const tabs = vscode.window.tabGroups.all.flatMap((g) => g.tabs)
      .filter((t) => t.input instanceof vscode.TabInputWebview && t.input.viewType.endsWith("mapcan.changes"));
    assert.equal(tabs.length, 1);
    assert.ok(vscode.window.tabGroups.all.length <= groups + 1);
    assert.equal(vscode.window.activeTextEditor.document.uri.toString(), doc.uri.toString());

    await vscode.commands.executeCommand("mapcan.history.openVersion", commits[1]);
    const version = vscode.window.activeTextEditor.document;
    assert.equal(version.uri.scheme, "mapcan-rev");
    assert.match(version.getText(), /name: pressure_old/);
    await new Promise((r) => setTimeout(r, 500));
    assert.equal(ctx.api.tree.mapUri.toString(), doc.uri.toString());

    const editor = await vscode.window.showTextDocument(doc);
    await editor.edit((e) => e.insert(new vscode.Position(0, 0), "# edited\n"));
    await until("uncommitted entry", () => history.getChildren().length === 3);
    assert.equal(history.getTreeItem(history.getChildren()[0]).contextValue, "uncommitted");
    await vscode.commands.executeCommand("undo");
    await until("no uncommitted entry", () => history.getChildren().length === 2);

    // Two versions: the older one is the old side, whichever was selected first
    await vscode.commands.executeCommand("mapcan.history.selectForCompare", commits[0]);
    assert.match(history.getTreeItem(commits[0]).description, /selected$/);
    ctx.api.changes.markdown = undefined;
    await vscode.commands.executeCommand("mapcan.history.compareWithSelected", commits[1]);
    assert.match(ctx.api.changes.markdown, /pressure/);

    // Restore is an edit of the document: Undo brings the current text back
    await vscode.commands.executeCommand("mapcan.history.restore", commits[1]);
    assert.match(doc.getText(), /name: pressure_old/);
    await vscode.window.showTextDocument(doc);
    await vscode.commands.executeCommand("undo");
    assert.equal(doc.getText(), original);

    // Revision history: the draft lists the changes, the entry goes first with the document version
    const oldText = execFileSync("git", ["show", `${commits[1].hash}:pump.yaml`], { cwd: repo, encoding: "utf8" });
    const draft = await vscode.commands.executeCommand("mapcan.lsp.historyDraft", { uri: doc.uri.toString(), oldText });
    assert.ok(draft.changes.some((l) => /pressure/.test(l)), draft.changes.join("\n"));
    const added = await vscode.commands.executeCommand("mapcan.lsp.addHistory",
      { uri: doc.uri.toString(), ...draft, version: "0.2.0", author: "Test" });
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(...added.edit.range), added.edit.text);
    await vscode.workspace.applyEdit(edit);
    assert.match(doc.getText(), /\n  version: 0\.2\.0\n/);
    assert.match(doc.getText(), /\n  history:\n    - version: 0\.2\.0\n      date: \d{4}-\d\d-\d\d\n      author: Test\n      changes:\n/);
    await vscode.commands.executeCommand("undo");
    assert.equal(doc.getText(), original);

    // The button asks for the author every time, prefilled with the name entered last time
    const { showQuickPick, showInputBox } = vscode.window;
    const boxes = [];
    const addWith = async (author) => {
      vscode.window.showQuickPick = async (items) => items;
      vscode.window.showInputBox = async (options) => {
        boxes.push(options);
        return options.title.endsWith("(3/3)") ? author ?? options.value : options.value;
      };
      try {
        await vscode.commands.executeCommand("mapcan.history.addToHistory", commits[1]);
      } finally {
        Object.assign(vscode.window, { showQuickPick, showInputBox });
      }
      await vscode.window.showTextDocument(doc);
      const text = doc.getText();
      await vscode.commands.executeCommand("undo");
      return text;
    };
    assert.match(await addWith("Jane Smith"), /\n      author: Jane Smith\n/);
    assert.match(await addWith(undefined), /\n      author: Jane Smith\n/);
    assert.equal(boxes.filter((b) => b.title.endsWith("(3/3)")).at(-1).value, "Jane Smith");
    assert.equal(doc.getText(), original);

    // The Map view marks nodes changed since the last commit, unsaved edits included
    const tree = ctx.api.tree;
    const node = (ident) => [...tree.nodes()].find((n) => n.raw.ident === ident);
    const change = (ident) => {
      const uri = tree.getTreeItem(node(ident)).resourceUri;
      return uri ? new URLSearchParams(uri.query).get("change") : null;
    };
    const editor2 = await vscode.window.showTextDocument(doc);
    await editor2.edit((e) => e.replace(
      new vscode.Range(positionOf(doc, "name: RUN", 6), positionOf(doc, "name: RUN", 9)), "RUNNING"));
    await until("modified signal", () => change("mode") === "modified");
    assert.equal(change("pump_state"), "inside");
    assert.equal(change("pressure"), null);
    const deco = tree.provideFileDecoration(tree.getTreeItem(node("mode")).resourceUri);
    assert.equal(deco.badge, "M");
    await vscode.commands.executeCommand("undo");
    await until("no marks", () => change("mode") === null);

    // Release Version: a revision, a commit of the map and the tag v<version>
    git("config", "user.name", "Test");
    git("config", "user.email", "test@example.com");
    await editor2.edit((e) => e.replace(
      new vscode.Range(positionOf(doc, "name: RUN", 6), positionOf(doc, "name: RUN", 9)), "RUNNING"));
    vscode.window.showQuickPick = async (items) => items;
    vscode.window.showInputBox = async (options) => (options.title.endsWith("(3/3)") ? "Test" : options.value);
    try {
      await vscode.commands.executeCommand("mapcan.history.release");
    } finally {
      Object.assign(vscode.window, { showQuickPick, showInputBox });
    }
    const tag = git("tag").trim();
    assert.match(tag, /^v\d+\.\d+\.\d+$/);
    assert.equal(doc.isDirty, false);
    assert.equal(git("status", "--porcelain", "--", "pump.yaml"), "");
    assert.match(git("log", "-1", "--format=%s"), /RUNNING/);
    assert.match(doc.getText(), new RegExp(`\\n  version: ${tag.slice(1).replace(/\./g, "\\.")}\\n`));
    assert.match(doc.getText(), /\n  history:\n    - version: .*\n      date: .*\n      author: Test\n      changes:\n        - .*RUNNING/);
    await until("tagged commit", () => history.commits[0]?.tags.includes(tag));
    assert.match(history.getTreeItem(history.commits[0]).description, new RegExp(`^${tag} · `));
    await until("no marks after the release", () => change("mode") === null);

    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
  },

  async "the form's layout and tables write the web editor's operations"(ctx) {
    await vscode.window.showTextDocument(ctx.doc);
    const before = ctx.doc.getText();
    const frame = ["buses", 0, "devices", 0, "frames", 0];
    const ops = async (list) => {
      const result = await vscode.commands.executeCommand("mapcan.lsp.ops", { uri: ctx.doc.uri.toString(), ops: list });
      const edit = new vscode.WorkspaceEdit();
      edit.replace(ctx.doc.uri, new vscode.Range(...result.edit.range), result.edit.text);
      await vscode.workspace.applyEdit(edit);
    };
    // A value of the table and a signal dragged over free bits, each one edit
    await ops([{ op: "set", path: [...frame, "signals", 0, "values", "3"], value: "SERVICE" }]);
    assert.match(ctx.doc.getText(), /2: \{name: FAULT, description: fault\}\n {18}3: SERVICE\n/);
    await vscode.commands.executeCommand("undo");
    assert.equal(ctx.doc.getText(), before);
    const n = (await ctx.api.tree.nodeByPath(frame)).children.length;
    await ops([
      { op: "insert", path: [...frame, "signals"], value: { name: "extra" } },
      { op: "set_layout", path: [...frame, "signals", n], start_bit: 60, bit_length: 4 },
    ]);
    // The position is written as the map writes positions (byte and bit here)
    assert.match(ctx.doc.getText(), /\n {14}- name: extra\n {16}byte: 7\n {16}bit: 4\n {16}bit_length: 4\n/);
    await vscode.commands.executeCommand("undo");
    assert.equal(ctx.doc.getText(), before);
    const error = await vscode.commands.executeCommand("mapcan.lsp.ops",
      { uri: ctx.doc.uri.toString(), ops: [{ op: "remove", path: ["nope"] }] });
    assert.ok(error.error);
  },

  async "nodes of included files are shown read-only"(ctx) {
    fs.writeFileSync(path.join(workspace, "extra.yaml"),
      "buses:\n  - name: aux\n    title: Aux bus\n    protocol: can\n    devices:\n      - name: valve\n");
    const main = path.join(workspace, "with-include.yaml");
    fs.writeFileSync(main, "mapcan: 1\ninclude: [extra.yaml]\ndocument: {title: T, language: en}\n"
      + "buses:\n  - name: can1\n    title: Main bus\n    protocol: can\n");
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(main));
    const roots = await until("tree with the included bus", () => {
      const r = ctx.api.tree.getChildren();
      return r.length === 2 ? r : undefined;
    });
    const own = ctx.api.tree.getTreeItem(roots[0]);
    const aux = ctx.api.tree.getTreeItem(roots[1]);
    assert.equal(own.contextValue, "bus");
    assert.deepEqual([aux.label, aux.description, aux.contextValue], ["Aux bus", "extra.yaml", "included"]);
    assert.match(aux.tooltip, /read-only here/);
    assert.match(aux.command.arguments[0].fsPath, /extra\.yaml$/);
    // The device under it comes from the same file: the file is named once, at the bus
    const valve = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(roots[1])[0]);
    assert.deepEqual([valve.description, valve.contextValue], ["", "included"]);
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
    await until("the first map in the tree", () => ctx.api.tree.mapUri?.toString() === ctx.doc.uri.toString()
      && ctx.api.tree.getChildren().length === 1);
  },

  async "edits are validated as you type"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    await editor.edit((e) => e.replace(
      new vscode.Range(positionOf(ctx.doc, "byte: 4", 0), positionOf(ctx.doc, "byte: 4", 7)),
      "byte: 4\n                bit_length: 99999"));
    const diags = await until("diagnostics", () => {
      const d = vscode.languages.getDiagnostics(ctx.doc.uri);
      return d.length ? d : undefined;
    });
    assert.equal(diags[0].source, "mapcan");
    assert.equal(diags[0].code, "schema");
    assert.equal(ctx.doc.getText(diags[0].range), "99999");
    const result = await vscode.commands.executeCommand("mapcan.lsp.export",
      { uri: ctx.doc.uri.toString(), formats: ["md"], outDir: path.join(workspace, "build2") });
    assert.match(result.error, /errors/);
  },
};

exports.run = async function run() {
  const file = path.join(workspace, "minimal.yaml");
  fs.copyFileSync(example, file);
  const doc = await vscode.workspace.openTextDocument(file);
  await vscode.window.showTextDocument(doc);
  const ext = vscode.extensions.getExtension("ordu1453.mapcan");
  const api = await until("activation", async () => (ext.isActive ? ext.exports : (await ext.activate(), undefined)));
  const ctx = { doc, api };
  const failures = [];
  for (const [name, test] of Object.entries(tests)) {
    try {
      await test(ctx);
      console.log(`  ✓ ${name}`);
    } catch (err) {
      console.log(`  ✗ ${name}\n    ${err.stack ?? err}`);
      failures.push(name);
    }
  }
  if (failures.length) throw new Error(`${failures.length} test(s) failed`);
};
