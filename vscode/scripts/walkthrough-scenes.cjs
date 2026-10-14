// Scenes for the screenshots of "Get started with mapcan" that the README has no picture for: the Export panel
// and the History panel. Run with screenshots.mjs:
//   MAPCAN_SCENES=scripts/walkthrough-scenes.cjs MAPCAN_SHOTS_OUT=<folder> node scripts/screenshots.mjs
// then scale the captures to 60% as JPEG into media/walkthrough/ (export-dark.jpg and so on).
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const vscode = require("vscode");

const workspace = process.env.MAPCAN_TEST_WORKSPACE;
const shots = process.env.MAPCAN_SHOTS;

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

async function shot(name) {
  await vscode.commands.executeCommand("notifications.clearAll");
  await sleep(1500);
  fs.writeFileSync(path.join(shots, `${name}.ready`), "");
  await until(`the capture of ${name}`, () => fs.existsSync(path.join(shots, `${name}.done`)));
}

const git = (...args) => execFileSync("git", args, { cwd: workspace, encoding: "utf8" });

/** Replace the first `from` after `after` in the map on the disk, and commit it. */
function commit(after, from, to, message) {
  const file = path.join(workspace, "vehicle-can.yaml");
  const text = fs.readFileSync(file, "utf8");
  const at = text.indexOf(from, text.indexOf(after));
  fs.writeFileSync(file, text.slice(0, at) + to + text.slice(at + from.length));
  git("commit", "-q", "-am", message);
}

exports.run = async function run() {
  try {
    await shot("window");
    // A history of three commits: the map, then two changes to its frames
    git("init", "-q");
    git("config", "user.name", "Ali Ordu");
    git("config", "user.email", "ali@example.com");
    // The exported files are not changes to commit: no badge on Source Control
    fs.appendFileSync(path.join(workspace, ".git", "info", "exclude"), "build/\n");
    git("add", "vehicle-can.yaml");
    git("commit", "-q", "-m", "Vehicle CAN map");
    commit("- name: bms_cells", "cycle_ms: 500", "cycle_ms: 200", "Send the cell voltages every 200 ms");
    commit("- name: pack_voltage", "max: 1000", "max: 800", "Limit the pack voltage to 800 V");

    const doc = await vscode.workspace.openTextDocument(path.join(workspace, "vehicle-can.yaml"));
    await vscode.window.showTextDocument(doc);
    const ext = vscode.extensions.getExtension("ordu1453.mapcan");
    const api = ext.isActive ? ext.exports : await ext.activate();
    await until("the server", () => api.client()?.isRunning());
    await until("the tree", () => api.tree.getChildren().length);
    await vscode.commands.executeCommand("workbench.view.extension.mapcan");
    await vscode.commands.executeCommand("workbench.action.closePanel");
    await vscode.commands.executeCommand("workbench.action.closeAuxiliaryBar");

    // History: the commits, and what changed since the first one in the Changes tab
    await vscode.commands.executeCommand("mapcan.export.removeView").then(undefined, () => undefined);
    await vscode.commands.executeCommand("mapcan.history.focus");
    await vscode.commands.executeCommand("mapcan.history.refresh");
    const commits = await until("the commits", () => (api.history.commits.length === 3 ? api.history.commits : undefined));
    await vscode.commands.executeCommand("mapcan.history.showChangesSince", commits[2]);
    await until("the changes", () => api.changes.markdown);
    await shot("history");

    // Export: the formats chosen and the files written
    await vscode.commands.executeCommand("workbench.action.closeAllEditors");
    await vscode.window.showTextDocument(doc);
    await vscode.commands.executeCommand("mapcan.history.removeView").then(undefined, () => undefined);
    // Exported before the panel is drawn: it shows these formats chosen, as it does after an export of the user's
    await api.exportView.onMessage({ type: "export", formats: ["dbc", "c", "xlsx", "pdf"], outDir: "build" });
    await until("the files", () => api.exportView.last?.result);
    await vscode.commands.executeCommand("mapcan.export.focus");
    await until("the export formats", () => api.exportView.rendered?.formats);
    await shot("export");
  } catch (err) {
    console.error(err);
  } finally {
    fs.writeFileSync(path.join(shots, "finished"), "");
  }
};
