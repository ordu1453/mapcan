// mapcan installed by the extension itself: a Python environment of its own in the extension's global storage,
// one per user (every folder uses it), so a computer needs nothing installed first. uv
// (https://docs.astral.sh/uv/) sets it up: the extension downloads uv from its GitHub releases unless it is on
// PATH, uv downloads Python and installs mapcan from PyPI.

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as fsp from "node:fs/promises";
import type { IncomingMessage } from "node:http";
import * as https from "node:https";
import * as path from "node:path";
import * as vscode from "vscode";

/** What the extension's environment gets: the language server, and PDF and Excel for the Export panel. */
const PACKAGE = "mapcan[lsp,pdf,xlsx]";
/** What an environment of the user's gets: the language server only. */
const PACKAGE_LSP = "mapcan[lsp]";
/** The Python the environment is made with: the one mapcan is tested with. */
const PYTHON = "3.12";

const exe = (name: string) => (process.platform === "win32" ? `${name}.exe` : name);

/** The folders of the extension's mapcan in the global storage. */
function dirs(storage: vscode.Uri) {
  const root = storage.fsPath;
  const env = path.join(root, "env");
  return {
    root,
    env,
    mapcan: path.join(env, process.platform === "win32" ? "Scripts" : "bin", exe("mapcan")),
    uv: path.join(root, "uv", exe("uv")),
    python: path.join(root, "python"),
  };
}

/** The mapcan the extension installed, if it did. */
export function managedMapcan(storage: vscode.Uri): string | undefined {
  const { mapcan } = dirs(storage);
  return fs.existsSync(mapcan) ? mapcan : undefined;
}

/** The name of the uv release archive for this computer. */
export function uvArchive(platform = process.platform, arch = process.arch): string | undefined {
  const cpu = ({ x64: "x86_64", arm64: "aarch64" } as Record<string, string>)[arch];
  if (!cpu) return undefined;
  if (platform === "win32") return `uv-${cpu}-pc-windows-msvc.zip`;
  if (platform === "darwin") return `uv-${cpu}-apple-darwin.tar.gz`;
  if (platform === "linux") return `uv-${cpu}-unknown-linux-gnu.tar.gz`;
  return undefined;
}

let installing: Promise<void> | undefined;

/**
 * Installs mapcan into the extension's environment, or updates it there; with `python`, updates it in the
 * environment of that Python instead. Throws with the reason if it fails; the details are in `log`.
 */
export function installMapcan(storage: vscode.Uri, log: vscode.LogOutputChannel, python?: string): Promise<void> {
  installing ??= Promise.resolve(vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "mapcan", cancellable: false },
    async (progress) => {
      const report = (message: string) => progress.report({ message });
      const d = dirs(storage);
      await fsp.mkdir(d.root, { recursive: true });
      const uv = await findUv(d, log, report);
      if (python) {
        report("Updating mapcan…");
        await runLogged(uv, ["pip", "install", "--python", python, "--upgrade", PACKAGE_LSP], d.root, process.env, log);
      } else {
        await install(d, uv, log, report);
      }
    },
  )).finally(() => (installing = undefined));
  return installing;
}

async function install(d: ReturnType<typeof dirs>, uv: string, log: vscode.LogOutputChannel,
  report: (m: string) => void): Promise<void> {
  // uv's own Python next to the environment, never one installed on the computer: removing that would break it
  const env = { ...process.env, UV_PYTHON_INSTALL_DIR: d.python, UV_PYTHON_PREFERENCE: "only-managed" };
  const run = (args: string[]) => runLogged(uv, args, d.root, env, log);
  const update = fs.existsSync(d.mapcan);
  if (!update) {
    report("Setting up Python…");
    await fsp.rm(d.env, { recursive: true, force: true });
    await run(["venv", "--python", PYTHON, d.env]);
  }
  report(update ? "Updating mapcan…" : "Installing mapcan…");
  await run(["pip", "install", "--python", d.env, ...(update ? ["--upgrade"] : []), PACKAGE]);
  if (!fs.existsSync(d.mapcan)) throw new Error(`mapcan is not in ${d.env} after the installation`);
  log.info(`mapcan installed: ${d.mapcan}`);
}

/** uv: the one the extension downloaded, else one on PATH, else downloaded now. */
async function findUv(d: ReturnType<typeof dirs>, log: vscode.LogOutputChannel, report: (m: string) => void): Promise<string> {
  if (fs.existsSync(d.uv)) return d.uv;
  if (await runs("uv", ["--version"])) return "uv";
  const archive = uvArchive();
  if (!archive) throw new Error(`there is no uv for ${process.platform} ${process.arch}: install mapcan yourself`);
  report("Downloading uv…");
  const url = `https://github.com/astral-sh/uv/releases/latest/download/${archive}`;
  const tmp = await fsp.mkdtemp(path.join(d.root, "uv-download-"));
  try {
    const file = path.join(tmp, archive);
    log.info(`Downloading ${url}`);
    await download(url, file);
    // tar unpacks the .zip on Windows too (bsdtar, in Windows since 10 1803); the one of Git for Windows cannot
    const tar = process.platform === "win32"
      ? path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "tar.exe")
      : "tar";
    await runLogged(tar, ["-xf", file, "-C", tmp], tmp, process.env, log);
    const found = await findFile(tmp, exe("uv"));
    if (!found) throw new Error(`no ${exe("uv")} in ${archive}`);
    // Asynchronous: an antivirus may take a while over a new executable, and the extension host must not wait
    await fsp.mkdir(path.dirname(d.uv), { recursive: true });
    await fsp.copyFile(found, d.uv);
    if (process.platform !== "win32") await fsp.chmod(d.uv, 0o755);
    return d.uv;
  } finally {
    await fsp.rm(tmp, { recursive: true, force: true });
  }
}

async function findFile(dir: string, name: string): Promise<string | undefined> {
  for (const entry of await fsp.readdir(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isFile() && entry.name === name) return p;
    if (entry.isDirectory()) {
      const found = await findFile(p, name);
      if (found) return found;
    }
  }
  return undefined;
}

/** The response to a GET of `url`, after redirects (GitHub sends releases from another host). The https module of
 * the extension host goes through VS Code's proxy settings. */
function get(url: string, timeout: number, redirects = 5): Promise<IncomingMessage> {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: { "User-Agent": "mapcan-vscode" }, timeout }, (res) => {
      const status = res.statusCode ?? 0;
      if (status >= 300 && status < 400 && res.headers.location && redirects > 0) {
        res.resume();
        get(new URL(res.headers.location, url).toString(), timeout, redirects - 1).then(resolve, reject);
      } else if (status !== 200) {
        res.resume();
        reject(new Error(`${url}: HTTP ${status}`));
      } else {
        resolve(res);
      }
    });
    req.on("timeout", () => req.destroy(new Error("no answer")));
    req.on("error", (e) => reject(new Error(`${url}: ${e.message}`)));
  });
}

async function download(url: string, file: string): Promise<void> {
  const res = await get(url, 30_000);
  await new Promise<void>((resolve, reject) => {
    const out = fs.createWriteStream(file);
    res.pipe(out);
    out.on("finish", () => out.close(() => resolve()));
    out.on("error", reject);
    res.on("error", reject);
  });
}

/** The latest version of mapcan on PyPI; undefined when PyPI cannot be reached (no network, say). */
export async function latestMapcan(): Promise<string | undefined> {
  try {
    const res = await get("https://pypi.org/pypi/mapcan/json", 10_000);
    let text = "";
    for await (const chunk of res) text += chunk;
    const version = (JSON.parse(text) as { info?: { version?: unknown } }).info?.version;
    return typeof version === "string" ? version : undefined;
  } catch {
    return undefined;
  }
}

function runs(command: string, args: string[]): Promise<boolean> {
  return new Promise((resolve) => {
    const p = spawn(command, args, { stdio: "ignore", windowsHide: true });
    p.on("error", () => resolve(false));
    p.on("exit", (code) => resolve(code === 0));
  });
}

/** Runs a command with its output in the log; rejects with the last line of its errors if it fails. */
function runLogged(command: string, args: string[], cwd: string, env: NodeJS.ProcessEnv,
  log: vscode.LogOutputChannel): Promise<void> {
  log.info(`> ${command} ${args.join(" ")}`);
  return new Promise((resolve, reject) => {
    const p = spawn(command, args, { cwd, env, windowsHide: true });
    let last = "";
    // The output comes in chunks that may end inside a line: a line is logged when it is complete
    const lines = () => {
      let rest = "";
      return (data?: Buffer) => {
        const parts = (rest + (data ? data.toString() : "\n")).split(/\r?\n/);
        rest = parts.pop() ?? "";
        for (const line of parts.map((l) => l.trim()).filter(Boolean)) {
          log.info(line);
          last = line;
        }
      };
    };
    const out = lines();
    const err = lines();
    p.stdout.on("data", out);
    p.stderr.on("data", err);
    p.stdout.on("end", () => out());
    p.stderr.on("end", () => err());
    p.on("error", (e) => reject(new Error(`${path.basename(command)}: ${e.message}`)));
    // close, not exit: the output has all been read then
    p.on("close", (code) =>
      code === 0 ? resolve() : reject(new Error(`${path.basename(command)} ${args[0]} failed${last ? `: ${last}` : ""}`)));
  });
}
