// Screenshots for the main README, in the light and the dark theme, into docs/images/:
//   npm run screenshots              both themes
//   npm run screenshots -- dark      one theme
// The editor scenes run `mapcan serve` on a copy of an example with settings of their own (an author profile, no
// recent files); the document scene renders pages of the PDF to PNG. They use the repository's .venv (or MAPCAN
// and PYTHON set to a mapcan executable and its Python) and drive Microsoft Edge, or Google Chrome with
// BROWSER=chrome, through playwright-core.
import { execFileSync, spawn } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const out = process.env.MAPCAN_SHOTS_OUT ?? join(repo, "docs", "images");
const venv = (name) => join(repo, ".venv", process.platform === "win32" ? `Scripts/${name}.exe` : `bin/${name}`);
const mapcan = process.env.MAPCAN ?? venv("mapcan");
const python = process.env.PYTHON ?? venv("python");
const PORT = 8798;
const SIZE = { width: 1600, height: 1000 };
const themes = process.argv.slice(2).filter((t) => t === "light" || t === "dark");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** The mouse out of the way: a hovered bit is highlighted. */
const park = (page) => page.mouse.move(SIZE.width - 5, SIZE.height / 2);

async function openFrame(page) {
  await page.getByText("PMP · Pump").click();
  await page.getByText("pump_state").first().click();
  await sleep(800);
  await park(page);
}

// Editor scenes: the example they open, a change to its text before it opens, and what they do in the editor
const EDITOR = {
  // A frame: the tree, the bit layout of its signals and its form
  frame: { map: "minimal.yaml", run: openFrame },
  // A mistake: two signals in the same byte, marked in the tree, the layout and the validation panel
  problems: {
    map: "minimal.yaml",
    edit: (text) => text.replace("byte: 4\n                byte_length: 1\n                representation",
      "byte: 3\n                byte_length: 1\n                representation"),
    run: openFrame,
  },
};

async function serve(dir, example, edit) {
  const map = join(dir, example);
  copyFileSync(join(repo, "examples", example), map);
  if (edit) {
    const text = readFileSync(map, "utf8");
    const changed = edit(text);
    if (changed === text) throw new Error(`the change to ${example} found nothing to change`);
    writeFileSync(map, changed);
  }
  const config = join(dir, "config");
  mkdirSync(config);
  writeFileSync(join(config, "config.json"), JSON.stringify({ user: { name: "Jane Smith", github: null }, recent: [] }));
  const server = spawn(mapcan, ["serve", map, "--no-browser", "--no-auth", "--port", String(PORT)], {
    env: { ...process.env, MAPCAN_CONFIG_DIR: config },
    stdio: "ignore",
  });
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${PORT}/`)).ok) return server;
    } catch {
      // not listening yet
    }
    await sleep(200);
  }
  server.kill();
  throw new Error("mapcan serve did not start");
}

async function editorShot(browser, theme, name, scene) {
  const server = await serve(mkdtempSync(join(tmpdir(), "mapcan-web-shots-")), scene.map, scene.edit);
  try {
    const page = await browser.newPage({ viewport: SIZE, colorScheme: theme, locale: "en-US" });
    await page.goto(`http://127.0.0.1:${PORT}/`);
    await page.getByText("Validation").first().waitFor();
    await scene.run(page);
    await save(page, `web-${name}-${theme}.png`);
    await page.close();
  } finally {
    server.kill();
    await sleep(300);
  }
}

/** Pages of the PDF of examples/vehicle-can.yaml: the title page, a bus and a frame. */
function renderPages() {
  const dir = mkdtempSync(join(tmpdir(), "mapcan-pdf-shots-"));
  execFileSync(python, ["-c", `
import sys
from mapcan.loader import load
from mapcan.export.pdf import export_pdf
export_pdf(load(sys.argv[1]).map, sys.argv[2], fmt="png")
`, join(repo, "examples", "vehicle-can.yaml"), join(dir, "page.png")]);
  // As data URLs: a page set from a string cannot load files
  return [1, 3, 5].map((n) => `data:image/png;base64,${readFileSync(join(dir, `page-${n}.png`)).toString("base64")}`);
}

/** The pages side by side. */
async function documentShot(browser, theme, pages) {
  const dark = theme === "dark";
  const page = await browser.newPage({ viewport: { width: SIZE.width, height: 760 }, colorScheme: theme });
  await page.setContent(`<!doctype html><style>
    body { margin: 0; height: 100vh; display: flex; gap: 36px; align-items: center; justify-content: center;
      background: ${dark ? "#0d1117" : "#f6f8fa"}; }
    img { height: 680px; border-radius: 4px;
      box-shadow: 0 2px 6px rgba(0,0,0,${dark ? 0.6 : 0.12}), 0 12px 32px rgba(0,0,0,${dark ? 0.5 : 0.12}); }
  </style>${pages.map((src) => `<img src="${src}">`).join("")}`);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
  await save(page, `document-pages-${theme}.png`);
  await page.close();
}

async function save(page, name) {
  const file = join(out, name);
  await page.screenshot({ path: file });
  console.log(`  ${file}`);
}

mkdirSync(out, { recursive: true });
// --lang: date fields in English whatever the system's language
const browser = await chromium.launch({
  channel: process.env.BROWSER === "chrome" ? "chrome" : "msedge", args: ["--lang=en-US"],
});
try {
  const pages = renderPages();
  for (const theme of themes.length ? themes : ["light", "dark"]) {
    for (const [name, scene] of Object.entries(EDITOR)) await editorShot(browser, theme, name, scene);
    await documentShot(browser, theme, pages);
  }
} finally {
  await browser.close();
}
