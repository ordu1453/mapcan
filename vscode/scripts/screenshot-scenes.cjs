// Scenes for the screenshots (see screenshots.mjs), run in the Extension Development Host like the tests.
// Each scene is set up, then "<name>.ready" asks for the capture and "<name>.done" lets it go on.
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");

const workspace = process.env.MAPCAN_TEST_WORKSPACE;
const shots = process.env.MAPCAN_SHOTS;
const BMS_STATUS = ["buses", 0, "devices", 0, "frames", 0];
const VCU_COMMAND = ["buses", 0, "devices", 1, "frames", 0];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function until(what, fn, timeout = 60000) {
  const end = Date.now() + timeout;
  for (;;) {
    const value = await fn();
    if (value) return value;
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`);
    await sleep(200);
  }
}

/** Ask screenshots.mjs to capture the window, and wait until it has. */
async function shot(name) {
  await vscode.commands.executeCommand("notifications.clearAll");
  await sleep(1500);   // the webviews and the decorations settle
  fs.writeFileSync(path.join(shots, `${name}.ready`), "");
  await until(`the capture of ${name}`, () => fs.existsSync(path.join(shots, `${name}.done`)));
}

let frames = 0;

/** A frame of the quick fix GIF, shown for `ms`: captured like a screenshot after a short settle. */
async function frame(ms, settle = 250) {
  await vscode.commands.executeCommand("notifications.clearAll");
  await sleep(settle);
  const name = `quickfix-${String(frames++).padStart(3, "0")}`;
  fs.writeFileSync(path.join(shots, `${name}.ready`), String(ms));
  await until(`the capture of ${name}`, () => fs.existsSync(path.join(shots, `${name}.done`)));
}

/**
 * The quick fix GIF: a signal moved in the YAML onto another one, the mistake marked on the bit layout and in the
 * editor at once, and the quick fix that moves it to free bits. Leaves the map as it was.
 */
async function quickFix(api, doc, editor) {
  await api.form.open(BMS_STATUS);
  await sleep(1500);    // the form takes the focus when it has rendered: the editor takes it back
  await vscode.window.showTextDocument(doc);
  const top = positionOf(doc, "- name: bms_status", 2);
  editor.revealRange(new vscode.Range(top, top), vscode.TextEditorRevealType.AtTop);
  const digit = positionOf(doc, "byte: 4\n                unit: A", 6);
  editor.selection = new vscode.Selection(digit, digit);
  await frame(1600, 1500);
  editor.selection = new vscode.Selection(digit, digit.translate(0, 1));
  await frame(500);
  await editor.edit((e) => e.replace(new vscode.Range(digit, digit.translate(0, 1)), "2"));
  await frame(200, 100);
  await until("the problem", () => vscode.languages.getDiagnostics(doc.uri).some((d) => d.severity === 0));
  await frame(2400, 1200);
  const at = vscode.languages.getDiagnostics(doc.uri).find((d) => d.severity === 0).range.start;
  editor.selection = new vscode.Selection(at, at);
  await frame(500, 600);
  await vscode.commands.executeCommand("editor.action.quickFix");
  await frame(1600, 800);
  await vscode.commands.executeCommand("acceptSelectedCodeAction");
  await until("no problem", () => !vscode.languages.getDiagnostics(doc.uri).some((d) => d.severity === 0));
  await frame(2600, 1200);
  await vscode.commands.executeCommand("workbench.action.files.revert");
}

/**
 * The demo GIF: screenshots.mjs drives the Node panel with the mouse through the DevTools protocol. The scene opens
 * a frame with free bits in the panel and its YAML next to it, then "drive.ready" hands over until "drive.done".
 */
async function demo(api, doc, editor) {
  await api.form.open(VCU_COMMAND);
  await sleep(1500);    // the form takes the focus when it has rendered: the editor takes it back
  await vscode.window.showTextDocument(doc);
  const top = positionOf(doc, "- name: torque_request", 2);
  editor.selection = new vscode.Selection(top, top);
  editor.revealRange(new vscode.Range(top, top), vscode.TextEditorRevealType.AtTop);
  await vscode.commands.executeCommand("notifications.clearAll");
  await sleep(1500);
  fs.writeFileSync(path.join(shots, "drive.ready"), "");
  await until("the demo", () => fs.existsSync(path.join(shots, "drive.done")), 300000);
}

function positionOf(doc, text, offset = 0) {
  return doc.positionAt(doc.getText().indexOf(text) + offset);
}

exports.run = async function run() {
  try {
    await shot("window");
    const doc = await vscode.workspace.openTextDocument(path.join(workspace, "vehicle-can.yaml"));
    const editor = await vscode.window.showTextDocument(doc);
    const ext = vscode.extensions.getExtension("ordu1453.mapcan");
    const api = ext.isActive ? ext.exports : await ext.activate();
    await until("the server", () => api.client()?.isRunning());
    await until("the tree", () => api.tree.getChildren().length);
    await vscode.commands.executeCommand("workbench.view.extension.mapcan");
    await vscode.commands.executeCommand("workbench.action.closePanel");
    await vscode.commands.executeCommand("workbench.action.closeAuxiliaryBar");
    // The Map view and the Node form only: the form gets the height for the bit layout
    for (const view of ["mapcan.export", "mapcan.history"]) {
      await vscode.commands.executeCommand(`${view}.removeView`).then(undefined, () => undefined);
    }

    // A mistake: two signals in the same bytes, marked in the tree and the editor, with a quick fix
    const overlap = positionOf(doc, "byte: 4\n                unit: A", 6);
    await editor.edit((e) => e.replace(new vscode.Range(overlap, overlap.translate(0, 1)), "2"));
    await until("the problem", () => vscode.languages.getDiagnostics(doc.uri).some((d) => d.severity === 0));
    const at = vscode.languages.getDiagnostics(doc.uri).find((d) => d.severity === 0).range.start;
    editor.selection = new vscode.Selection(at, at);
    editor.revealRange(new vscode.Range(at, at), vscode.TextEditorRevealType.InCenter);
    await vscode.commands.executeCommand("editor.action.quickFix");
    await shot("problems");
    await vscode.commands.executeCommand("hideCodeActionWidget").then(undefined, () => undefined);
    await vscode.commands.executeCommand("undo");
    await until("no problem", () => !vscode.languages.getDiagnostics(doc.uri).some((d) => d.severity === 0));

    // The hover of a frame: its ID, cycle, receivers and bit layout
    const nameAt = positionOf(doc, "bms_status", 3);
    editor.selection = new vscode.Selection(nameAt, nameAt);
    editor.revealRange(new vscode.Range(nameAt, nameAt), vscode.TextEditorRevealType.AtTop);
    await vscode.commands.executeCommand("editor.action.showHover");
    await shot("hover");

    // The Node form of a frame with its bit layout, the whole height of the side bar (the Map view hidden)
    await vscode.commands.executeCommand("editor.action.hideHover").then(undefined, () => undefined);
    await vscode.commands.executeCommand("mapcan.map.removeView").then(undefined, () => undefined);
    await api.form.open(BMS_STATUS);
    await sleep(1500);    // the form takes the focus when it has rendered: the editor takes it back
    await vscode.window.showTextDocument(doc);
    const frameAt = positionOf(doc, "- name: bms_status", 2);
    editor.selection = new vscode.Selection(frameAt, frameAt);
    editor.revealRange(new vscode.Range(frameAt, frameAt), vscode.TextEditorRevealType.AtTop);
    await shot("map");
    await quickFix(api, doc, editor);
    await demo(api, doc, editor);
  } catch (err) {
    console.error(err);
  } finally {
    fs.writeFileSync(path.join(shots, "finished"), "");
  }
};
