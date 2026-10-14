// Screenshots of the extension for the READMEs (Windows only): starts VS Code with the extension as the
// tests do, lets scripts/screenshot-scenes.cjs set up each scene, and captures the window into docs/images/.
//   node scripts/screenshots.mjs              light and dark
//   node scripts/screenshots.mjs dark         one theme
// Build first (npm run build). The window may be covered by others while it runs: it is captured with
// PrintWindow, not from the screen.
import { downloadAndUnzipVSCode } from "@vscode/test-electron";
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { drive } from "./demo-drive.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const repo = resolve(root, "..");
// MAPCAN_SHOTS_OUT and MAPCAN_SCENES take other scenes elsewhere (to look at a view while working on it)
const out = process.env.MAPCAN_SHOTS_OUT ?? join(repo, "docs", "images");
const scenes = process.env.MAPCAN_SCENES ? resolve(process.env.MAPCAN_SCENES) : join(here, "screenshot-scenes.cjs");
const server = process.env.MAPCAN_SERVER ?? join(repo, ".venv", "Scripts", "mapcan.exe");
const python = process.env.PYTHON ?? join(repo, ".venv", "Scripts", "python.exe");
const capture = join(here, "capture-window.ps1");
/** The window size of the screenshots, in physical pixels. */
const SIZE = { width: 1560, height: 980 };
/** The scale of the window whatever the monitor's: the README shows the pictures about 900 pixels wide, and the text
 * stays readable there. */
const SCALE = 1.5;
/** The DevTools port of the window, for the demo. */
const PORT = 9341;
const THEMES = { light: "Default Light Modern", dark: "Default Dark Modern" };

if (process.platform !== "win32") {
  console.error("screenshots.mjs captures windows with the Windows API: run it on Windows");
  process.exit(1);
}
const themes = process.argv.slice(2).filter((t) => t in THEMES);
mkdirSync(out, { recursive: true });
const executable = process.env.VSCODE_PATH || (await downloadAndUnzipVSCode());

const powershell = (...args) =>
  execFileSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", capture, ...args], { stdio: "inherit" });
const powershellOutput = (...args) =>
  execFileSync("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", capture, ...args], { encoding: "utf8" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

for (const theme of themes.length ? themes : Object.keys(THEMES)) {
  // A project folder with a short name: the window title shows it
  const workspace = join(mkdtempSync(join(tmpdir(), "mapcan-shots-")), "ev-project");
  const shots = join(workspace, "..", "shots");
  mkdirSync(workspace, { recursive: true });
  mkdirSync(shots);
  copyFileSync(join(repo, "examples", "vehicle-can.yaml"), join(workspace, "vehicle-can.yaml"));
  const userData = join(workspace, "..", "user-data");
  mkdirSync(join(userData, "User"), { recursive: true });
  // A plain window: the theme, no welcome page, chat, minimap, tips or command center
  const settings = {
    "workbench.colorTheme": THEMES[theme],
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": false,
    "workbench.layoutControl.enabled": false,
    "workbench.secondarySideBar.defaultVisibility": "hidden",
    "window.commandCenter": false,
    "window.restoreWindows": "none",
    "chat.disableAIFeatures": true,
    "chat.commandCenter.enabled": false,
    "editor.minimap.enabled": false,
    "editor.stickyScroll.enabled": false,
    "editor.overviewRulerBorder": false,
    "editor.scrollbar.horizontal": "hidden",
    "breadcrumbs.enabled": false,
    // The system frame and no menu: only the inside of the window is captured
    "window.titleBarStyle": "native",
    "window.customTitleBarVisibility": "never",
    "window.menuBarVisibility": "toggle",
    "editor.occurrencesHighlight": "off",
    "editor.selectionHighlight": false,
    "editor.fontSize": 14,
    "telemetry.telemetryLevel": "off",
    "update.mode": "none",
    "extensions.ignoreRecommendations": true,
    "security.workspace.trust.enabled": false,
    "git.openRepositoryInParentFolders": "never",
  };
  const writeSettings = () => writeFileSync(join(userData, "User", "settings.json"), JSON.stringify(settings, null, 2));
  writeSettings();

  const code = spawn(executable, [
    workspace,
    "--disable-extensions",
    "--user-data-dir", userData,
    "--extensions-dir", join(workspace, "..", "extensions"),
    "--no-sandbox", "--disable-gpu-sandbox", "--disable-updates", "--skip-welcome", "--skip-release-notes",
    "--disable-workspace-trust",
    `--remote-debugging-port=${PORT}`,
    `--extensionTestsPath=${scenes}`,
    `--extensionDevelopmentPath=${root}`,
  ], { env: { ...process.env, MAPCAN_SERVER: server, MAPCAN_TEST_WORKSPACE: workspace, MAPCAN_SHOTS: shots } });
  code.stdout.on("data", (d) => process.stdout.write(d));
  code.stderr.on("data", () => {});
  let exited = false;
  code.on("exit", () => (exited = true));

  // The scenes say "<name>.ready"; the window is captured and "<name>.done" lets them go on.
  // "window" asks for the size first, "quickfix-NNN" are the frames of the quick fix GIF (the file holds how long
  // each is shown), "drive" runs the demo, "finished" ends.
  const taken = new Set();
  const quickfix = [];
  for (;;) {
    if (exited) break;
    if (existsSync(join(shots, "finished"))) break;
    for (const name of readdirSync(shots).filter((f) => f.endsWith(".ready")).map((f) => f.slice(0, -6))) {
      if (taken.has(name)) continue;
      taken.add(name);
      if (name === "window") {
        powershell("-ProcessId", String(code.pid), "-Width", String(SIZE.width), "-Height", String(SIZE.height));
        // VS Code zooms by 1.2 a level, on top of the monitor's scale; it applies the setting at once
        const dpi = Number(powershellOutput("-ProcessId", String(code.pid), "-Dpi").trim()) || 96;
        settings["window.zoomLevel"] = Math.log(SCALE / (dpi / 96)) / Math.log(1.2);
        writeSettings();
        await sleep(2000);
      } else if (name.startsWith("quickfix-")) {
        const file = join(shots, `${name}.png`);
        powershell("-ProcessId", String(code.pid), "-Out", file);
        quickfix.push([file, Number(readFileSync(join(shots, `${name}.ready`), "utf8"))]);
      } else if (name === "drive") {
        if (quickfix.length) gif(quickfix, join(out, `vscode-quickfix-${theme}.gif`));
        try {
          gif(await drive(PORT, shots), join(out, `vscode-demo-${theme}.gif`));
        } catch (err) {
          console.error(`the demo failed: ${err.stack}`);
        }
      } else {
        const file = join(out, `vscode-${name}-${theme}.png`);
        powershell("-ProcessId", String(code.pid), "-Out", file);
        console.log(`  ${file}`);
      }
      writeFileSync(join(shots, `${name}.done`), "");
    }
    await sleep(300);
  }
  if (!exited) {
    try {
      execFileSync(join(process.env.WINDIR || "C:\\Windows", "System32", "taskkill.exe"),
        ["/F", "/T", "/PID", String(code.pid)], { stdio: "ignore" });
    } catch {
      // VS Code closed meanwhile
    }
  }
}

/** Joins the frames ([file, milliseconds shown]) into a GIF 1000 pixels wide, with one palette for all of them. */
function gif(frames, file) {
  execFileSync(python, ["-c", `
import json, sys
from PIL import Image
frames = json.loads(sys.argv[2])
images = []
for f, _ in frames:
    im = Image.open(f).convert("RGB")
    images.append(im.resize((1000, round(im.height * 1000 / im.width)), Image.Resampling.LANCZOS))
sheet = Image.new("RGB", (images[0].width, images[0].height * len(images)))
for i, im in enumerate(images):
    sheet.paste(im, (0, im.height * i))
palette = sheet.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
gif = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
gif[0].save(sys.argv[1], save_all=True, append_images=gif[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)
`, file, JSON.stringify(frames)]);
  console.log(`  ${file}`);
}
