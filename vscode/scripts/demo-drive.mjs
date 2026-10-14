// The demo GIF of the extension (see screenshots.mjs): drives the Node panel with the mouse through the DevTools
// protocol of the VS Code window and takes a screenshot for each step. The Node panel is a webview in a process of
// its own: its elements are found by evaluating in its target, the mouse and the keyboard go through the window.
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { chromium } from "playwright-core";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Evaluates an expression in a DevTools target (a webview) and returns its value. */
function evaluate(target, expression) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    socket.onopen = () => socket.send(JSON.stringify({
      id: 1, method: "Runtime.evaluate", params: { expression, returnByValue: true },
    }));
    socket.onmessage = (m) => {
      const reply = JSON.parse(m.data);
      if (reply.id !== 1) return;
      socket.close();
      if (reply.result?.exceptionDetails) reject(new Error(reply.result.exceptionDetails.exception?.description));
      else resolve(reply.result?.result?.value);
    };
    socket.onerror = () => reject(new Error(`no connection to ${target.url}`));
  });
}

// In the webview: the document of the form is in an iframe of the webview's own page
const IN_FORM = (body) => `(() => {
  const frame = document.querySelector("iframe");
  const d = frame && frame.contentDocument;
  if (!d) return null;
  const at = frame.getBoundingClientRect();
  const center = (e) => { const r = e.getBoundingClientRect(); return [at.x + r.x + r.width / 2, at.y + r.y + r.height / 2]; };
  ${body}
})()`;

/** The page's points of the centers of the layout's cells, by bit. */
const CELLS = IN_FORM(`
  return d.querySelector(".bg-cell") && {
    width: innerWidth,
    cells: Object.fromEntries([...d.querySelectorAll(".bg-cell")].map((c) => [/\\d+/.exec(c.title)[0], center(c)])),
  };`);

/** The center of the control of a field, by the beginning of its label. */
const FIELD = (label) => IN_FORM(`
  const l = [...d.querySelectorAll("label")].find((l) => l.textContent.trim().startsWith(${JSON.stringify(label)}));
  const input = l && d.getElementById(l.htmlFor);
  if (!input) return null;
  input.scrollIntoView({ block: "nearest" });
  return { width: innerWidth, point: center(input) };`);

const SCROLL_TOP = IN_FORM(`d.scrollingElement.scrollTo(0, 0); return true;`);

/** Chooses an option of a select field by its text, as the user would in its drop-down. */
const CHOOSE = (label, option) => IN_FORM(`
  const l = [...d.querySelectorAll("label")].find((l) => l.textContent.trim().startsWith(${JSON.stringify(label)}));
  const select = d.getElementById(l.htmlFor);
  const o = [...select.options].find((o) => o.text.startsWith(${JSON.stringify(option)}));
  select.value = o.value;
  select.dispatchEvent(new Event("change", { bubbles: true }));
  return o.text;`);

/** A drawn mouse pointer over the workbench: screenshots leave the real one out. */
function addPointer() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", "20");
  svg.setAttribute("height", "26");
  svg.setAttribute("viewBox", "0 0 20 26");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", "M1 1 L1 20 L6 15 L9.5 23 L13 21.5 L9.5 14 L16 14 Z");
  path.setAttribute("fill", "#000");
  path.setAttribute("stroke", "#fff");
  path.setAttribute("stroke-width", "1.5");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  svg.id = "demo-pointer";
  Object.assign(svg.style, { position: "fixed", left: "-40px", top: "0", zIndex: "2147483647", pointerEvents: "none" });
  document.body.append(svg);
}

/**
 * Runs the demo in the VS Code window listening on `port`, with the screenshots in `dir`. Returns the frames as
 * [file, milliseconds shown].
 */
export async function drive(port, dir) {
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`);
  const frames = [];
  try {
    const page = browser.contexts()[0].pages()[0];
    await page.evaluate(addPointer);
    const targets = (await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json()))
      .filter((t) => t.type === "iframe");
    let form;
    for (const t of targets) if (await evaluate(t, CELLS).catch(() => null)) form = t;
    if (!form) throw new Error("the Node panel shows no bit layout");
    // The webview's page in the workbench: its points are scaled by the zoom of the window
    const pageWidth = await page.evaluate(() => innerWidth);
    const box = await (async () => {
      for (const f of page.frames().slice(1)) {
        const b = await (await f.frameElement()).boundingBox();
        if (b && b.width > 0 && b.x < pageWidth / 2) return b;
      }
      throw new Error("the Node panel is not in the side bar");
    })();
    const toPage = (width, [x, y]) => [box.x + (x * box.width) / width, box.y + (y * box.width) / width];
    const cell = async (bit) => {
      const r = await evaluate(form, CELLS);
      return toPage(r.width, r.cells[bit]);
    };
    const field = async (label) => {
      const r = await evaluate(form, FIELD(label));
      return toPage(r.width, r.point);
    };

    // Page.captureScreenshot as it is: Playwright's screenshot of a page it did not open sets a viewport of its own
    const session = await page.context().newCDPSession(page);
    const shot = async (ms) => {
      const file = join(dir, `drive-${String(frames.length).padStart(3, "0")}.png`);
      const { data } = await session.send("Page.captureScreenshot", { format: "png" });
      writeFileSync(file, Buffer.from(data, "base64"));
      frames.push([file, ms]);
    };
    let at = [box.x + box.width + 300, box.y + 200];
    const move = async (x, y) => {
      at = [x, y];
      await page.mouse.move(x, y, { steps: 2 });
      await page.evaluate(([px, py]) => {
        const p = document.getElementById("demo-pointer");
        Object.assign(p.style, { left: `${px - 1}px`, top: `${py - 1}px` });
      }, at);
    };
    const glide = async (x, y) => {
      const [x0, y0] = at;
      for (let i = 1; i <= 5; i++) {
        await move(x0 + ((x - x0) * i) / 5, y0 + ((y - y0) * i) / 5);
        await shot(40);
      }
    };
    const drag = async (from, to) => {
      await glide(...(await cell(from)));
      await shot(250);
      await page.mouse.down();
      for (let n = from; n !== to;) {
        n += to > from ? 1 : -1;
        await move(...(await cell(n)));
        await sleep(60);
        await shot(170);
      }
      await page.mouse.up();
      await sleep(1200);    // the edit goes through the language server and back
    };

    await move(...at);
    await shot(1600);
    // A new signal on the free bits of the last byte
    await drag(63, 60);
    await shot(1300);
    // Its name and encoding in the form
    await glide(...(await field("Identifier")));
    await page.mouse.click(...at, { clickCount: 3 });
    for (const part of ["fa", "ult", "_co", "de"]) {
      await page.keyboard.type(part);
      await shot(140);
    }
    await page.keyboard.press("Enter");
    await sleep(1000);
    await shot(900);
    await glide(...(await field("Encoding")));
    await evaluate(form, CHOOSE("Encoding", "raw"));
    await sleep(1200);
    await shot(1300);
    // Longer by its edge, then over the next signal: the overlap is marked at once, here and in the YAML
    await evaluate(form, SCROLL_TOP);
    await sleep(400);
    await drag(60, 58);
    await shot(1300);
    await drag(61, 53);
    await sleep(800);
    await shot(2600);
    // Back to the free bits
    await drag(53, 61);
    await sleep(800);
    await shot(2600);
  } finally {
    await browser.close().catch(() => undefined);
  }
  return frames;
}
