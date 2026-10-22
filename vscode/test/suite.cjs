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
  async "Restricted Mode takes the command and the export folder from the user's settings"() {
    const { untrustedWorkspaces } = vscode.extensions.getExtension("ordu1453.mapcan").packageJSON.capabilities;
    assert.equal(untrustedWorkspaces.supported, "limited");
    assert.deepEqual(untrustedWorkspaces.restrictedConfigurations,
      ["mapcan.server.path", "mapcan.server.args", "mapcan.export.outputDir"]);
  },

  async "activates and shows the map tree"(ctx) {
    const roots = await until("tree", () => {
      const r = ctx.api.tree.getChildren();
      return r.length ? r : undefined;
    });
    const bus = ctx.api.tree.getTreeItem(roots[0]);
    // Titles, as in the web editor; the identifier is in the tooltip; the estimated bus load (#131)
    assert.deepEqual([bus.label, bus.description], ["Demo bus", "0.3%"]);
    // and the tooltip says what the load is
    assert.match(bus.tooltip, /^Bus demo\nEstimated bus load: 0\.3%\n/);
    const device = ctx.api.tree.getChildren(roots[0])[0];
    // The node ID before the title: a long title does not hide it (#130)
    const dev = ctx.api.tree.getTreeItem(device);
    assert.deepEqual([dev.label, dev.description, dev.tooltip],
      ["0x21 · PMP · Pump", "", "Device pump\nPMP · Pump\nNode ID 0x21"]);
    const frame = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(device)[0]);
    assert.deepEqual([frame.label, frame.description, frame.tooltip], ["pump_state", "0x1A1", "Frame pump_state\nTX"]);
    assert.match(frame.iconPath.dark.path, /tree\/dark\/frame-tx\.svg$/);
    assert.ok(fs.existsSync(frame.iconPath.dark.fsPath));
    assert.equal(ctx.api.tree.mapUri.toString(), ctx.doc.uri.toString());
  },

  async "templates and examples to start from come from the server"() {
    const starters = await vscode.commands.executeCommand("mapcan.lsp.starters");
    assert.deepEqual(starters.templates.map((t) => t.id), ["canopen", "j1939", "can", "empty"]);
    assert.ok(starters.examples.some((e) => e.name === "vehicle-can"));
    // An example in several files comes with its included file, which names the copy of the map
    const tractor = await vscode.commands.executeCommand("mapcan.lsp.example", { name: "tractor", mapFile: "tractor.yaml" });
    assert.match(tractor.text, /^mapcan: 1/m);
    assert.match(tractor.includes["powertrain.yaml"], /^part_of: tractor\.yaml/m);
    const created = await vscode.commands.executeCommand("mapcan.lsp.newMap", { template: "j1939", title: "Truck", language: "en" });
    assert.match(created.text, /title: "Truck"/);
    const commands = await vscode.commands.getCommands(true);
    assert.ok(["mapcan.newMap", "mapcan.openExample"].every((c) => commands.includes(c)));
    const { walkthroughs } = vscode.extensions.getExtension("ordu1453.mapcan").packageJSON.contributes;
    assert.ok(walkthroughs[0].steps.length >= 4);
  },

  async "the repository and a new issue are a command away"() {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(["mapcan.openRepository", "mapcan.reportIssue", "mapcan.showServerVersion"].every((c) => commands.includes(c)));
  },

  async "the server reports a version the extension works with"(ctx) {
    const version = ctx.api.serverVersion();
    assert.match(version ?? "", /^\d+\.\d+\.\d+/);
    assert.equal(ctx.api.isOlder(version, "0.21.0"), false);
    assert.deepEqual(["0.20.3", "0.21.0.dev1", "0.21.1", "1.0"].map((v) => ctx.api.isOlder(v, "0.21.0")),
      [true, false, false, false]);
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
    const pos = positionOf(ctx.doc, "encoding: scaled", "encoding: ".length);
    const list = await vscode.commands.executeCommand("vscode.executeCompletionItemProvider", ctx.doc.uri, pos);
    const labels = list.items.map((i) => (typeof i.label === "string" ? i.label : i.label.label));
    assert.ok(labels.includes("bitfield"), labels.slice(0, 20).join(", "));
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
    assert.match(ctx.doc.getText(), /\n {14}- name: signal\n {16}encoding: raw\n {16}byte: 7\n {16}bit: 4\n {16}bit_length: 4\n/);
    assert.equal(vscode.window.activeTextEditor.document.getText(vscode.window.activeTextEditor.selection), "signal");
    await until("tree with the new signal", () => frame().children.some((s) => s.raw.label === "signal"));
    // The frame is full now: one more signal would lie over another one, so none is added
    const full = ctx.doc.getText();
    await vscode.commands.executeCommand("mapcan.addSignal", frame());
    assert.equal(ctx.doc.getText(), full);
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
    assert.match(ctx.doc.getText(), /\n {10}- name: pump_frame\n {12}canopen: pdo_tx2\n {12}length: 8\n {12}cycle_ms: 100\n {12}signals: \[\]\n/);
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
    // The webview ran its script and drew the signal's fields (it is served from dist/webview, see #75)
    const drawn = await until("the form drawn", () =>
      JSON.stringify(form.rendered?.path) === JSON.stringify(added.path) && form.rendered);
    assert.ok(drawn.fields.includes("name") && drawn.fields.includes("bit_length"), drawn.fields.join(", "));
    const set = (key, value) => vscode.commands.executeCommand("mapcan.lsp.set",
      { uri: ctx.doc.uri.toString(), path: [...added.path, key], value });
    const result = await set("title", "Battery voltage");
    const edit = new vscode.WorkspaceEdit();
    for (const e of result.edits) edit.replace(ctx.doc.uri, new vscode.Range(...e.range), e.text);
    await vscode.workspace.applyEdit(edit);
    // The title goes to its place in the canonical order (mapcan fmt): after the name
    assert.match(ctx.doc.getText(), /- name: signal\n {16}title: Battery voltage\n {16}encoding: raw\n {16}byte: 7\n {16}bit: 4\n {16}bit_length: 4\n/);
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
    // Not a preview tab: VS Code may replace that with the next editor opened
    await vscode.window.showTextDocument(doc, { preview: false });
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
    // The webview tab appears asynchronously
    const changesTabs = () => vscode.window.tabGroups.all.flatMap((g) => g.tabs)
      .filter((t) => t.input instanceof vscode.TabInputWebview && t.input.viewType.endsWith("mapcan.changes"));
    await until("the Changes tab", () => changesTabs().length > 0);
    assert.equal(changesTabs().length, 1);
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
    // Undo acts on the focused part of the window: the editor gets the focus first
    await vscode.window.showTextDocument(doc);
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

    // Revision history: the draft lists the changes, the entry goes first; the document's version and date
    // come from it, so the ones written in the document are removed
    const oldText = execFileSync("git", ["show", `${commits[1].hash}:pump.yaml`], { cwd: repo, encoding: "utf8" });
    const draft = await vscode.commands.executeCommand("mapcan.lsp.historyDraft", { uri: doc.uri.toString(), oldText });
    assert.ok(draft.changes.some((l) => /pressure/.test(l)), draft.changes.join("\n"));
    const added = await vscode.commands.executeCommand("mapcan.lsp.addHistory",
      { uri: doc.uri.toString(), ...draft, version: "0.2.0", author: "Test" });
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, new vscode.Range(...added.edit.range), added.edit.text);
    await vscode.workspace.applyEdit(edit);
    assert.doesNotMatch(doc.getText(), /\n  version: /);
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
    // The version of the tag is that of the new history entry (the document's version comes from it)
    assert.doesNotMatch(doc.getText(), /\n  version: /);
    assert.match(doc.getText(), new RegExp(`\\n  history:\\n    - version: ${tag.slice(1).replace(/\./g, "\\.")}\\n`
      + "      date: .*\\n      author: Test\\n      changes:\\n        - .*RUNNING"));
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

  async "the webviews draw the bit layout and the export formats"(ctx) {
    // Counted in the pages themselves: data that arrives but is not drawn fails here (#79)
    await vscode.window.showTextDocument(ctx.doc);
    const frame = ["buses", 0, "devices", 0, "frames", 0];
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    await ctx.api.form.open(frame);
    const drawn = await until("the frame's layout drawn", () => {
      const r = ctx.api.form.rendered;
      return r && same(r.path, frame) && r.layout ? r : undefined;
    });
    assert.equal(drawn.layout.rows, 8);
    assert.ok(drawn.layout.legend >= 1);
    // A device has no layout
    await ctx.api.form.open(frame.slice(0, 4));
    await until("a device without layout", () => same(ctx.api.form.rendered?.path, frame.slice(0, 4))
      && ctx.api.form.rendered.layout === null);
    await ctx.api.form.close();
    await vscode.commands.executeCommand("mapcan.export");
    await until("the export formats drawn", () => ctx.api.exportView.rendered?.formats > 0);
    await vscode.window.showTextDocument(ctx.doc);
  },

  async "nodes of included files are shown and edited in their file"(ctx) {
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
    // One tree: the file is named in the tooltip only
    assert.deepEqual([aux.label, aux.description, aux.contextValue], ["Aux bus", "", "bus.included"]);
    assert.match(aux.tooltip, /\nIn extra\.yaml$/);
    assert.match(aux.command.arguments[0].fsPath, /extra\.yaml$/);
    const valve = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(roots[1])[0]);
    assert.deepEqual([valve.description, valve.contextValue], ["", "device.included"]);
    // A field written by the form goes to the included file
    const result = await vscode.commands.executeCommand("mapcan.lsp.set",
      { uri: vscode.Uri.file(main).toString(), path: ["buses", 1, "devices", 0, "title"], value: "Valve" });
    assert.deepEqual(result.edits, []);
    assert.equal(result.others.length, 1);
    assert.match(result.others[0].uri, /extra\.yaml$/);
    assert.match(result.others[0].edit.text, /title: Valve/);
    // Written by the Node panel there with no tab open on it: saved when the map is saved
    const extraUri = vscode.Uri.parse(result.others[0].uri);
    await ctx.api.form.open(["buses", 1, "devices", 0]);
    await until("the form", () => ctx.api.form.rendered?.path);
    ctx.api.form.onMessage({ type: "set", key: "title", value: "Valve" });
    const extraDoc = await until("the change in extra.yaml",
      () => vscode.workspace.textDocuments.find((d) => d.uri.toString() === extraUri.toString() && d.isDirty));
    assert.match(extraDoc.getText(), /title: Valve/);
    assert.deepEqual(ctx.api.hiddenChanges([extraUri]).map((d) => path.basename(d.uri.fsPath)), ["extra.yaml"]);
    // The main file has no changes of its own: saving it still saves the other file
    assert.equal(vscode.window.activeTextEditor.document.uri.toString(), vscode.Uri.file(main).toString());
    await vscode.commands.executeCommand("workbench.action.files.save");
    await until("extra.yaml saved", () => !extraDoc.isDirty);
    assert.match(fs.readFileSync(extraUri.fsPath, "utf8"), /title: Valve/);
    await ctx.api.form.close();
    // The tree adds and deletes nodes of the included file in that file
    const added = await vscode.commands.executeCommand("mapcan.lsp.edit",
      { uri: vscode.Uri.file(main).toString(), action: "add", path: ["buses", 1, "devices", 0], kind: "frame" });
    assert.match(added.uri, /extra\.yaml$/);
    assert.match(added.edit.text, /- name: valve_frame/);
    // The only device of the bus: its list stays a list
    const deleted = await vscode.commands.executeCommand("mapcan.lsp.edit",
      { uri: vscode.Uri.file(main).toString(), action: "delete", path: ["buses", 1, "devices", 0] });
    assert.match(deleted.uri, /extra\.yaml$/);
    assert.match(deleted.edit.text, /devices: \[\]/);
    // A device added to a bus of the main file goes to the main file
    const device = await vscode.commands.executeCommand("mapcan.lsp.edit",
      { uri: vscode.Uri.file(main).toString(), action: "add", path: ["buses", 0], kind: "device" });
    assert.equal(device.uri, undefined);
    assert.match(device.edit.text, /- name: device/);
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
    await until("the first map in the tree", () => ctx.api.tree.mapUri?.toString() === ctx.doc.uri.toString()
      && ctx.api.tree.getChildren().length === 1);
  },

  async "a device added in a new file: the file is made and the map includes it (#136)"(ctx) {
    const dir = path.join(workspace, "own-files");
    fs.mkdirSync(dir, { recursive: true });
    const main = path.join(dir, "main.yaml");
    fs.writeFileSync(main, "mapcan: 1\n\ndocument: {title: T, language: en}\n\n"
      + "buses:\n  - name: can1\n    title: Main bus\n    protocol: canopen\n    devices:\n"
      + "      - {name: node_a, title: Device 1, node_id: 0x01}\n");
    const doc = await vscode.workspace.openTextDocument(main);
    await vscode.window.showTextDocument(doc);
    const bus = () => ctx.api.tree.getChildren()[0];
    await until("the map in the tree", () => ctx.api.tree.mapUri?.toString() === doc.uri.toString() && bus());
    const { showInputBox } = vscode.window;
    let offered;
    vscode.window.showInputBox = async (options) => {
      offered = options.value;
      return "devices/node_b.yaml";
    };
    try {
      await vscode.commands.executeCommand("mapcan.addDeviceFile", bus());
    } finally {
      Object.assign(vscode.window, { showInputBox });
    }
    assert.equal(offered, "devices/device.yaml");
    const file = path.join(dir, "devices", "node_b.yaml");
    assert.match(fs.readFileSync(file, "utf8"), /^part_of: \.\.\/main\.yaml\n\nbuses:\n {2}- name: can1\n {4}devices:\n {6}- name: node_b\n {8}title: Device 2\n {8}node_id: 0x02\n/m);
    assert.match(doc.getText(), /\n\ninclude: \[devices\/node_b\.yaml\]\n\nbuses:\n/);
    // The new file is open with the device's name selected, and the device is in the tree and the form
    // (visible, not active: the window may not have the focus while the tests run)
    const editor = vscode.window.visibleTextEditors.find((e) => e.document.uri.toString() === vscode.Uri.file(file).toString());
    assert.ok(editor);
    assert.equal(editor.document.getText(editor.selection), "node_b");
    const added = await until("the device in the tree", () => bus().children.find((d) => d.raw.ident === "node_b"));
    assert.deepEqual(ctx.api.form.openPath, added.path);
    await ctx.api.form.close();
    // Deleting the device deletes its file, left empty, and the line of include
    await vscode.window.showTextDocument(doc);
    await until("the device in the tree", () => bus().children.find((d) => d.raw.ident === "node_b"));
    await vscode.commands.executeCommand("mapcan.deleteNode", bus().children.find((d) => d.raw.ident === "node_b"));
    await until("the file deleted", () => !fs.existsSync(file));
    assert.doesNotMatch(doc.getText(), /include/);
    assert.doesNotMatch(doc.getText(), /\n\n\n/);
    await until("the tree without the device", () => !bus().children.some((d) => d.raw.ident === "node_b"));
    // Clean up
    await vscode.commands.executeCommand("workbench.action.revertAndCloseActiveEditor");
    // The folder may still be watched for a moment (Windows): it is in the test's temporary folder anyway
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
    await vscode.window.showTextDocument(ctx.doc);
    await until("the first map in the tree", () => ctx.api.tree.mapUri?.toString() === ctx.doc.uri.toString());
  },

  async "an included file open on its own: its device's address, its frame's functions, Export of its map"(ctx) {
    const dir = path.join(workspace, "split");
    fs.mkdirSync(path.join(dir, "devices"), { recursive: true });
    fs.writeFileSync(path.join(dir, "main.yaml"), "mapcan: 1\ndocument: {title: Example, language: en}\n"
      + "include: [devices/node.yaml]\nbuses:\n  - name: can1\n    title: CAN 1\n    protocol: canopen\n"
      + "    bitrate: 500000\n    devices: []\n");
    const node = path.join(dir, "devices", "node.yaml");
    fs.writeFileSync(node, "mapcan: 1\npart_of: ../main.yaml\nbuses:\n  - name: can1\n    devices:\n"
      + "      - name: node\n        title: A rather long device title that does not fit in the side bar\n"
      + "        node_id: 0x10\n        frames:\n          - name: state\n            canopen: pdo_tx1\n"
      + "            length: 8\n            signals: []\n");
    const doc = await vscode.workspace.openTextDocument(node);
    await vscode.window.showTextDocument(doc);
    const [bus] = await until("the map of the included file in the tree", () => {
      const r = ctx.api.tree.mapUri?.toString() === doc.uri.toString() && ctx.api.tree.getChildren();
      return r && r.length === 1 && ctx.api.tree.getChildren(r[0]).length ? r : undefined;
    });
    // The bus load by the bus (#131); the node ID before a long title, which cuts it no more (#130)
    // (none when no frame has a period, and the tooltip says why)
    const busItem = ctx.api.tree.getTreeItem(bus);
    assert.equal(busItem.description, "");
    assert.match(busItem.tooltip, /\nBus load unknown: no frame has a cycle or a minimum interval\.\n/);
    const device = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(bus)[0]);
    assert.equal(device.label, "0x10 · A rather long device title that does not fit in the side bar");
    assert.equal(device.description, "");
    assert.match(device.tooltip, /^Device node\nA rather long device title.*\nNode ID 0x10\n/);
    // The form offers every CANopen function to the frame of the included file (#133)
    const fields = await ctx.api.client().sendRequest("mapcan/node",
      { textDocument: { uri: doc.uri.toString() }, path: ["buses", 0, "devices", 0, "frames", 0] });
    assert.match(fields.file, /node\.yaml$/);
    const types = fields.frameTypes.map((t) => t.type);
    for (const t of ["", "nmt", "emcy", "pdo_tx1", "pdo_rx4", "sdo_tx", "heartbeat"]) assert.ok(types.includes(t), t);
    // Export in the included file exports its map, named after it, next to it (#135)
    await ctx.api.exportView.onMessage({ type: "export", formats: ["md"], outDir: "build" });
    const result = ctx.api.exportView.last.result;
    assert.equal(result.error, undefined);
    // Compared relative to the folder: the server and the extension may spell the drive letter differently
    assert.equal(path.relative(dir, result.map), "main.yaml");
    assert.deepEqual(result.files.map((f) => path.relative(dir, f)), [path.join("build", "main.md")]);
    assert.match(fs.readFileSync(path.join(dir, "build", "main.md"), "utf8"), /A rather long device title/);
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
    await until("the first map in the tree", () => ctx.api.tree.mapUri?.toString() === ctx.doc.uri.toString());
  },

  async "rename follows a device into the included file it is described in"(ctx) {
    const extra = path.join(workspace, "pumps.yaml");
    fs.writeFileSync(extra, "buses:\n  - name: can1\n    devices:\n      - name: pump\n");
    const main = path.join(workspace, "with-pump.yaml");
    fs.writeFileSync(main, "mapcan: 1\ninclude: [pumps.yaml]\ndocument: {title: T, language: en}\n"
      + "buses:\n  - name: can1\n    protocol: can\n    frames:\n"
      + "      - {name: cmd, id: 0x100, length: 1, receivers: [pump]}\n");
    const doc = await vscode.workspace.openTextDocument(main);
    await vscode.window.showTextDocument(doc);
    await until("the server", () => ctx.api.client()?.isRunning());
    const line = doc.lineAt(7).text;
    const pos = new vscode.Position(7, line.indexOf("[pump]") + 2);
    const edit = await until("the rename", async () => {
      const e = await vscode.commands.executeCommand("vscode.executeDocumentRenameProvider", doc.uri, pos, "motor");
      return e && e.entries().length === 2 ? e : undefined;
    });
    const byFile = Object.fromEntries(edit.entries().map(([uri, edits]) => [path.basename(uri.fsPath), edits]));
    assert.deepEqual(byFile["with-pump.yaml"].map((e) => [e.range.start.line, e.newText]), [[7, "motor"]]);
    assert.deepEqual(byFile["pumps.yaml"].map((e) => [e.range.start.line, e.newText]), [[3, "motor"]]);
    await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
    await until("the first map in the tree", () => ctx.api.tree.mapUri?.toString() === ctx.doc.uri.toString());
  },

  async "other YAML files do not reach the server"(ctx) {
    const other = await vscode.workspace.openTextDocument(path.join(workspace, "compose.yaml"));
    const hovers = await vscode.commands.executeCommand(
      "vscode.executeHoverProvider", other.uri, new vscode.Position(0, 2));
    assert.ok(!hovers.some((h) => h.contents.some((c) => /mapcan/.test(c.value ?? c))));
    assert.deepEqual(vscode.languages.getDiagnostics(other.uri), []);
  },

  async "a new file is validated once it becomes a map"(ctx) {
    const doc = await vscode.workspace.openTextDocument({ language: "yaml", content: "a: 1\n" });
    const editor = await vscode.window.showTextDocument(doc);
    const text = fs.readFileSync(example, "utf-8").replace("byte: 4", "byte: 4\n                bit_length: 99999");
    await editor.edit((e) => e.replace(new vscode.Range(0, 0, doc.lineCount, 0), text));
    const diags = await until("diagnostics", () => {
      const d = vscode.languages.getDiagnostics(doc.uri);
      return d.length ? d : undefined;
    });
    assert.equal(diags[0].code, "schema");
    await vscode.commands.executeCommand("workbench.action.revertAndCloseActiveEditor");
    await vscode.window.showTextDocument(ctx.doc);
  },

  async "edits are validated as you type"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    await editor.edit((e) => e.replace(
      new vscode.Range(positionOf(ctx.doc, "byte: 4", 0), positionOf(ctx.doc, "byte: 4", 7)),
      "byte: 4\n                bit_length: 99999"));
    // The server analyses once typing pauses: the messages of the text before the edit may still be shown
    const diag = await until("diagnostics", () =>
      vscode.languages.getDiagnostics(ctx.doc.uri).find((d) => d.code === "schema"));
    assert.equal(diag.source, "mapcan");
    assert.equal(ctx.doc.getText(diag.range), "99999");
    const result = await vscode.commands.executeCommand("mapcan.lsp.export",
      { uri: ctx.doc.uri.toString(), formats: ["md"], outDir: path.join(workspace, "build2") });
    assert.match(result.error, /errors/);
  },

  async "maps and the files they include get the format's schema for the YAML extension"(ctx) {
    assert.equal(ctx.api.schemaOf(ctx.doc.uri.toString()), "mapcan-schema://schema/v1.json");
    const part = await vscode.workspace.openTextDocument({ language: "yaml", content: "mapcan: 1\npart_of: m.yaml\n" });
    assert.equal(ctx.api.schemaOf(part.uri.toString()), "mapcan-schema://schema/part-v1.json");
    const other = await vscode.workspace.openTextDocument({ language: "yaml", content: "services: {}\n" });
    assert.equal(ctx.api.schemaOf(other.uri.toString()), undefined);
    // The schemas come with the extension
    const ext = vscode.extensions.getExtension("ordu1453.mapcan");
    for (const f of ["mapcan.schema.json", "mapcan-part.schema.json"]) {
      const schema = JSON.parse(fs.readFileSync(path.join(ext.extensionPath, "dist", "schema", f), "utf8"));
      assert.match(schema.$id, /^https:\/\/ordu1453\.github\.io\/mapcan\/schema\/(part-)?v1\.json$/);
    }
  },

  async "the walkthrough's buttons and pictures exist, and the tour shows a problem on its own map"() {
    const ext = vscode.extensions.getExtension("ordu1453.mapcan");
    const [walkthrough] = ext.packageJSON.contributes.walkthroughs;
    const commands = await vscode.commands.getCommands(true);
    for (const step of walkthrough.steps) {
      for (const [, command] of step.description.matchAll(/\(command:([\w.]+)\)/g)) {
        assert.ok(commands.includes(command), `${step.id}: no command ${command}`);
      }
      const media = step.media.markdown ? [step.media.markdown] : Object.values(step.media.image);
      for (const file of media) assert.ok(fs.existsSync(path.join(ext.extensionPath, file)), `${step.id}: no ${file}`);
    }

    await vscode.commands.executeCommand("mapcan.tour.showProblem");
    const editor = vscode.window.activeTextEditor;
    assert.match(editor.document.fileName, /tour[\\/]battery\.yaml$/);
    const problem = vscode.languages.getDiagnostics(editor.document.uri).find((d) => d.severity === 0);
    assert.equal(problem.code, "bit-overlap");
    assert.ok(editor.selection.active.isEqual(problem.range.start));
    // A second time, after an edit: the map is written again, mistake included
    await editor.edit((e) => e.insert(new vscode.Position(0, 0), "# edited\n"));
    await vscode.commands.executeCommand("mapcan.tour.showProblem");
    assert.doesNotMatch(vscode.window.activeTextEditor.document.getText(), /# edited/);
    assert.equal(vscode.window.activeTextEditor.document.isDirty, false);

    await vscode.commands.executeCommand("mapcan.tour.showHover");
    assert.match(vscode.window.activeTextEditor.document.lineAt(vscode.window.activeTextEditor.selection.active).text,
      /- name: battery_status/);
  },

  // Last: closes every editor.
  async "the server stops when no map is open and starts with the next one"(ctx) {
    ctx.api.setIdleStop(500);
    // Earlier tests leave unsaved documents (a new untitled map, edits): closing them with
    // closeAllEditors would ask to save them, and the dialog would hold the window open
    for (let i = 0; i < 50 && vscode.window.tabGroups.all.some((g) => g.tabs.length); i++) {
      await vscode.commands.executeCommand("workbench.action.revertAndCloseActiveEditor");
      if (!vscode.window.activeTextEditor) await vscode.commands.executeCommand("workbench.action.closeActiveEditor");
    }
    await until("the server to stop", () => ctx.api.client() === undefined, 300000);
    await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(ctx.doc.uri));
    await until("the server", () => ctx.api.client()?.isRunning());
    await until("the tree", () => ctx.api.tree.getChildren().length);
  },
};

exports.run = async function run() {
  // Another YAML file activates the extension but does not start the server.
  const other = path.join(workspace, "compose.yaml");
  fs.writeFileSync(other, "services:\n  web:\n    image: nginx\n");
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(other));
  const ext = vscode.extensions.getExtension("ordu1453.mapcan");
  const api = await until("activation", async () => (ext.isActive ? ext.exports : (await ext.activate(), undefined)));
  assert.equal(api.client(), undefined, "the server started for a YAML file that is not a map");

  const file = path.join(workspace, "minimal.yaml");
  fs.copyFileSync(example, file);
  const doc = await vscode.workspace.openTextDocument(file);
  await vscode.window.showTextDocument(doc);
  await until("the server", () => api.client()?.isRunning());
  const ctx = { doc, api };
  const failures = [];
  try {
    for (const [name, test] of Object.entries(tests)) {
      try {
        await test(ctx);
        console.log(`  ✓ ${name}`);
      } catch (err) {
        console.log(`  ✗ ${name}\n    ${err.stack ?? err}`);
        failures.push(name);
      }
    }
  } finally {
    // test/runTest.mjs closes VS Code once the result is here
    const result = path.join(workspace, ".result.json");
    fs.writeFileSync(result, JSON.stringify({ failures: failures.length }));
    console.log(`  result: ${result}`);
  }
  if (failures.length) throw new Error(`${failures.length} test(s) failed`);
};
