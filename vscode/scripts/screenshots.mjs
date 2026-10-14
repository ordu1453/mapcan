// Screenshots of the extension for the READMEs (Windows only): starts VS Code with the extension as the
// tests do, lets scripts/screenshot-scenes.cjs set up each scene, and captures the window into docs/images/.
//   node scripts/screenshots.mjs              light and dark
//   node scripts/screenshots.mjs dark         one theme
// Build first (npm run build). The window may be covered by others while it runs: it is captured with
// PrintWindow, not from the screen.
import { downloadAndUnzipVSCode } from "@vscode/test-electron";
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const repo = resolve(root, "..");
// MAPCAN_SHOTS_OUT and MAPCAN_SCENES take other scenes elsewhere (to look at a view while working on it)
const out = process.env.MAPCAN_SHOTS_OUT ?? join(repo, "docs", "images");
const scenes = process.env.MAPCAN_SCENES ? resolve(process.env.MAPCAN_SCENES) : join(here, "screenshot-scenes.cjs");
const server = process.env.MAPCAN_SERVER ?? join(repo, ".venv", "Scripts", "mapcan.exe");
const capture = join(here, "capture-window.ps1");
/** The window size of the screenshots, in physical pixels. */
const SIZE = { width: 1920, height: 1200 };
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
  writeFileSync(join(userData, "User", "settings.json"), JSON.stringify({
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
  }, null, 2));

  const code = spawn(executable, [
    workspace,
    "--disable-extensions",
    "--user-data-dir", userData,
    "--extensions-dir", join(workspace, "..", "extensions"),
    "--no-sandbox", "--disable-gpu-sandbox", "--disable-updates", "--skip-welcome", "--skip-release-notes",
    "--disable-workspace-trust",
    `--extensionTestsPath=${scenes}`,
    `--extensionDevelopmentPath=${root}`,
  ], { env: { ...process.env, MAPCAN_SERVER: server, MAPCAN_TEST_WORKSPACE: workspace, MAPCAN_SHOTS: shots } });
  code.stdout.on("data", (d) => process.stdout.write(d));
  code.stderr.on("data", () => {});
  let exited = false;
  code.on("exit", () => (exited = true));

  // The scenes say "<name>.ready"; the window is captured and "<name>.done" lets them go on.
  // "window" asks for the size first, "finished" ends.
  const taken = new Set();
  for (;;) {
    if (exited) break;
    if (existsSync(join(shots, "finished"))) break;
    for (const name of readdirSync(shots).filter((f) => f.endsWith(".ready")).map((f) => f.slice(0, -6))) {
      if (taken.has(name)) continue;
      taken.add(name);
      if (name === "window") {
        powershell("-ProcessId", String(code.pid), "-Width", String(SIZE.width), "-Height", String(SIZE.height));
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
