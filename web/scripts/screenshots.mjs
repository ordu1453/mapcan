// Screenshots and the demo GIF for the main README, in the light and the dark theme, into docs/images/:
//   npm run screenshots              both themes
//   npm run screenshots -- dark      one theme
// The editor scenes run `mapcan serve` on a copy of an example with settings of their own (an author profile, no
// recent files); the document scene renders pages of the PDF to PNG; the demo is a series of screenshots that
// Pillow joins into a GIF. They use the repository's .venv (or MAPCAN
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
// A small window at twice the pixel density: the README shows the pictures about 900 pixels wide, and the text
// of the editor stays readable there
const SIZE = { width: 1100, height: 720 };
const SCALE = 2;
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
    const page = await browser.newPage({ viewport: SIZE, deviceScaleFactor: SCALE, colorScheme: theme, locale: "en-US" });
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

/** Pages of the PDF of examples/vehicle-can.yaml: a bus with its addressing and frames with their bit layouts. */
function renderPages() {
  const dir = mkdtempSync(join(tmpdir(), "mapcan-pdf-shots-"));
  execFileSync(python, ["-c", `
import sys
from mapcan.loader import load
from mapcan.export.pdf import export_pdf
export_pdf(load(sys.argv[1]).map, sys.argv[2], fmt="png")
`, join(repo, "examples", "vehicle-can.yaml"), join(dir, "page.png")]);
  // As data URLs: a page set from a string cannot load files
  return [3, 5].map((n) => `data:image/png;base64,${readFileSync(join(dir, `page-${n}.png`)).toString("base64")}`);
}

/** The pages side by side. */
async function documentShot(browser, theme, pages) {
  const dark = theme === "dark";
  const page = await browser.newPage({ viewport: { width: SIZE.width, height: 780 }, deviceScaleFactor: SCALE, colorScheme: theme });
  await page.setContent(`<!doctype html><style>
    body { margin: 0; height: 100vh; display: flex; gap: 28px; align-items: center; justify-content: center;
      background: ${dark ? "#0d1117" : "#f6f8fa"}; }
    img { height: 720px; border-radius: 4px;
      box-shadow: 0 2px 6px rgba(0,0,0,${dark ? 0.6 : 0.12}), 0 12px 32px rgba(0,0,0,${dark ? 0.5 : 0.12}); }
  </style>${pages.map((src) => `<img src="${src}">`).join("")}`);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
  await save(page, `document-pages-${theme}.png`);
  await page.close();
}

/** A drawn mouse pointer: screenshots leave the real one out. */
function pointer() {
  addEventListener("DOMContentLoaded", () => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "20");
    svg.setAttribute("height", "26");
    svg.setAttribute("viewBox", "0 0 20 26");
    svg.innerHTML = '<path d="M1 1 L1 20 L6 15 L9.5 23 L13 21.5 L9.5 14 L16 14 Z" fill="#000" stroke="#fff" ' +
      'stroke-width="1.5" stroke-linejoin="round"/>';
    // CSSOM, not a style attribute: the editor's CSP drops inline styles
    Object.assign(svg.style, { position: "fixed", left: "-40px", top: "0", zIndex: "2147483647", pointerEvents: "none" });
    document.body.append(svg);
    addEventListener("mousemove", (e) => Object.assign(svg.style, { left: `${e.clientX - 1}px`, top: `${e.clientY - 1}px` }), true);
  });
}

/**
 * The demo: a signal drawn on free bits and named, moved over another one (the mistake is marked at once), the
 * move undone, and the map exported. Each step is a screenshot shown for its own time.
 */
async function demoShot(browser, theme) {
  const dir = mkdtempSync(join(tmpdir(), "mapcan-web-demo-"));
  const server = await serve(dir, "minimal.yaml");
  const frames = [];
  try {
    const page = await browser.newPage({ viewport: SIZE, colorScheme: theme, locale: "en-US", bypassCSP: true });
    await page.addInitScript(pointer);
    await page.goto(`http://127.0.0.1:${PORT}/`);
    await page.getByText("Validation").first().waitFor();
    await openFrame(page);
    const shot = async (ms) => {
      const file = join(dir, `frame-${String(frames.length).padStart(3, "0")}.png`);
      await page.screenshot({ path: file });
      frames.push([file, ms]);
    };
    // The pointer on its way somewhere, in a few frames
    let at = [SIZE.width - 300, SIZE.height - 120];
    const glide = async (x, y) => {
      for (let i = 1; i <= 5; i++) {
        await page.mouse.move(at[0] + ((x - at[0]) * i) / 5, at[1] + ((y - at[1]) * i) / 5);
        await shot(40);
      }
      at = [x, y];
    };
    const bit = async (n) => {
      const b = await page.locator(`.bg-cell[title="bit ${n}"]`).boundingBox();
      return [b.x + b.width / 2, b.y + b.height / 2];
    };
    const drag = async (from, to) => {
      await glide(...(await bit(from)));
      await shot(250);
      await page.mouse.down();
      for (let n = from; n !== to;) {
        n += to > from ? 1 : -1;
        at = await bit(n);
        await page.mouse.move(...at, { steps: 3 });
        await shot(180);
      }
      await page.mouse.up();
      await sleep(700);
    };

    await page.mouse.move(...at);
    await shot(1400);
    // A new signal on the free bits of the last byte, then its name
    await drag(63, 60);
    await shot(1200);
    const id = page.getByRole("textbox", { name: "Identifier" }).or(page.locator("input[value='signal']")).first();
    const box = await id.boundingBox();
    await glide(box.x + 60, box.y + box.height / 2);
    await id.click({ clickCount: 3 });
    for (const part of ["fa", "ult", "_co", "de"]) {
      await page.keyboard.type(part);
      await shot(140);
    }
    await page.keyboard.press("Tab");
    await sleep(700);
    await shot(1200);
    // Over the counter: the overlap is marked on the layout, in the tree and in the validation panel
    await drag(62, 58);
    await shot(2600);
    const undo = page.getByTitle("Undo (Ctrl+Z)");
    const ub = await undo.boundingBox();
    await glide(ub.x + ub.width / 2, ub.y + ub.height / 2);
    await shot(400);
    await undo.click();
    await sleep(700);
    await shot(1200);
    // The documents and the code from the same file
    const exp = page.getByRole("button", { name: "Export ▾" });
    const eb = await exp.boundingBox();
    await glide(eb.x + eb.width / 2, eb.y + eb.height / 2);
    await exp.click();
    await sleep(300);
    await shot(2800);
    await page.close();
  } finally {
    server.kill();
    await sleep(300);
  }
  const file = join(out, `demo-${theme}.gif`);
  execFileSync(python, ["-c", `
import json, sys
from PIL import Image
frames = json.loads(sys.argv[2])
images = [Image.open(f).convert("RGB") for f, _ in frames]
# One palette for all the frames, from all of them: the colors of the editor do not flicker from frame to frame
sheet = Image.new("RGB", (images[0].width, images[0].height * len(images)))
for i, im in enumerate(images):
    sheet.paste(im, (0, im.height * i))
palette = sheet.quantize(colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
gif = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
gif[0].save(sys.argv[1], save_all=True, append_images=gif[1:], duration=[ms for _, ms in frames], loop=0, optimize=True)
`, file, JSON.stringify(frames)]);
  console.log(`  ${file}`);
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
    await demoShot(browser, theme);
  }
} finally {
  await browser.close();
}
