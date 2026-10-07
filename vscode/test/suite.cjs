// Runs inside the Extension Development Host (see runTest.mjs).
const assert = require("node:assert/strict");
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
    assert.deepEqual([bus.label, bus.description], ["Demo bus", "demo"]);
    const device = ctx.api.tree.getChildren(roots[0])[0];
    assert.equal(ctx.api.tree.getTreeItem(device).label, "PMP · pump");
    const frame = ctx.api.tree.getTreeItem(ctx.api.tree.getChildren(device)[0]);
    assert.deepEqual([frame.label, frame.description, frame.tooltip], ["pump_state", "0x1A1", "TX"]);
    assert.match(frame.iconPath.dark.path, /tree\/dark\/frame-tx\.svg$/);
    assert.ok(fs.existsSync(frame.iconPath.dark.fsPath));
    assert.equal(ctx.api.tree.mapUri.toString(), ctx.doc.uri.toString());
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

  async "edits are validated as you type"(ctx) {
    const editor = await vscode.window.showTextDocument(ctx.doc);
    await editor.edit((e) => e.replace(
      new vscode.Range(positionOf(ctx.doc, "byte: 4", 0), positionOf(ctx.doc, "byte: 4", 7)),
      "byte: 4\n                bit_length: 99"));
    const diags = await until("diagnostics", () => {
      const d = vscode.languages.getDiagnostics(ctx.doc.uri);
      return d.length ? d : undefined;
    });
    assert.equal(diags[0].source, "mapcan");
    assert.equal(diags[0].code, "schema");
    assert.equal(ctx.doc.getText(diags[0].range), "99");
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
