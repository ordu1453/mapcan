// A `mapcan serve` of its own for each test: a temporary folder (the working folder of the editor), settings of
// its own (a profile, no recent files) and a free port. MAPCAN names the mapcan executable; the repository's .venv
// by default.
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { test as base, expect, type Page } from "@playwright/test";

export const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
export const mapcan = process.env.MAPCAN
  ?? join(repo, ".venv", process.platform === "win32" ? "Scripts/mapcan.exe" : "bin/mapcan");

function freePort(): Promise<number> {
  return new Promise((ok, fail) => {
    const s = createServer();
    s.once("error", fail);
    s.listen(0, "127.0.0.1", () => {
      const { port } = s.address() as { port: number };
      s.close(() => ok(port));
    });
  });
}

export interface Editor {
  /** The working folder: what the editor opens and saves. */
  dir: string;
  url: string;
}

interface Fixtures {
  /** Files to put into the working folder before the server starts: name → a file of the repository. */
  files: Record<string, string>;
  /** The map `mapcan serve` opens (a name in `files`); the start screen without it. */
  open: string | null;
  editor: Editor;
}

export const test = base.extend<Fixtures>({
  files: [{}, { option: true }],
  open: [null, { option: true }],
  editor: async ({ files, open }, use) => {
    const dir = mkdtempSync(join(tmpdir(), "mapcan-e2e-"));
    for (const [name, source] of Object.entries(files)) copyFileSync(join(repo, source), join(dir, name));
    const config = join(dir, ".config");
    mkdirSync(config);
    writeFileSync(join(config, "config.json"), JSON.stringify({ user: { name: "Jane Smith", github: null }, recent: [] }));
    const port = await freePort();
    const server: ChildProcess = spawn(
      mapcan, ["serve", open ? join(dir, open) : dir, "--no-browser", "--no-auth", "--port", String(port)],
      { cwd: dir, env: { ...process.env, MAPCAN_CONFIG_DIR: config }, stdio: "ignore" });
    const url = `http://127.0.0.1:${port}/`;
    try {
      await expect.poll(async () => (await fetch(url).catch(() => null))?.ok, { timeout: 30_000 }).toBe(true);
      await use({ dir, url });
    } finally {
      const exited = new Promise((r) => server.once("exit", r).once("error", r));
      // On Windows mapcan.exe starts Python as a child process: the whole tree is stopped, or it keeps the folder
      if (process.platform === "win32") spawnSync("taskkill", ["/pid", String(server.pid), "/t", "/f"]);
      else server.kill();
      await exited;
      rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
    }
  },
});

export { expect };

/** The editor with its map loaded: the tree and the validation panel are there. */
export async function openEditor(page: Page, editor: Editor): Promise<void> {
  await page.goto(editor.url);
  await expect(page.getByText("Validation").first()).toBeVisible();
}
