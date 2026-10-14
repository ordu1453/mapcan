// Integration test: starts a separate VS Code with the extension and runs test/suite.cjs.
//   npm test                     downloads VS Code stable into .vscode-test/
//   VSCODE_PATH=…/Code.exe npm test   uses an installed VS Code instead
//
// VS Code is started here rather than with runTests of @vscode/test-electron: its window does not always close
// when the tests end (it waits for the user to close it), so the suite writes its result to a file and VS Code
// is closed from here once it is there.
import { downloadAndUnzipVSCode } from "@vscode/test-electron";
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const venv = resolve(root, "..", ".venv");
const server =
  process.env.MAPCAN_SERVER ??
  (process.platform === "win32" ? join(venv, "Scripts", "mapcan.exe") : join(venv, "bin", "mapcan"));
const workspace = mkdtempSync(join(tmpdir(), "mapcan-ext-"));
const resultFile = join(workspace, ".result.json");

const executable = process.env.VSCODE_PATH || (await downloadAndUnzipVSCode());
const args = [
  workspace,
  "--disable-extensions",
  // --disable-gpu: under xvfb (CI) the window may hang on start with software GL
  "--disable-gpu",
  "--user-data-dir", join(workspace, ".user-data"),
  "--extensions-dir", join(workspace, ".extensions"),
  // The arguments runTests of @vscode/test-electron starts VS Code with
  "--no-sandbox",
  "--disable-gpu-sandbox",
  "--disable-updates",
  "--skip-welcome",
  "--skip-release-notes",
  "--no-cached-data",
  "--disable-workspace-trust",
  `--extensionTestsPath=${join(here, "suite.cjs")}`,
  `--extensionDevelopmentPath=${root}`,
];
const code = spawn(executable, args, {
  env: { ...process.env, MAPCAN_SERVER: server, MAPCAN_TEST_WORKSPACE: workspace },
});
code.stdout.on("data", (d) => process.stdout.write(d));
code.stderr.on("data", (d) => process.stderr.write(d));

/** Close VS Code with all its processes (the language server too). */
function killTree(pid) {
  return new Promise((done) => {
    const killer = process.platform === "win32"
      ? spawn(join(process.env.WINDIR || "C:\\Windows", "System32", "taskkill.exe"), ["/F", "/T", "/PID", String(pid)])
      : spawn("sh", [join(root, "node_modules", "@vscode", "test-electron", "killTree.sh"), String(pid), "9"]);
    killer.on("exit", done);
    killer.on("error", done);
  });
}

const exited = new Promise((done) => code.on("exit", (c, signal) => done(c ?? signal)));
const result = await new Promise((done) => {
  const timer = setInterval(() => {
    if (existsSync(resultFile)) {
      clearInterval(timer);
      try {
        done(JSON.parse(readFileSync(resultFile, "utf-8")));
      } catch {
        done({ failures: -1 });
      }
    }
  }, 500);
  // VS Code closed before the suite finished: a crash, or its window was closed
  void exited.then(() => {
    clearInterval(timer);
    done(existsSync(resultFile) ? JSON.parse(readFileSync(resultFile, "utf-8")) : undefined);
  });
});

// A moment for VS Code to close on its own, then it is closed from here
const closed = await Promise.race([exited.then(() => true), new Promise((r) => setTimeout(() => r(false), 5000))]);
if (!closed) await killTree(code.pid);
code.stdout.destroy();
code.stderr.destroy();

if (result === undefined) {
  console.error("VS Code closed before the tests finished");
  process.exit(1);
}
console.log(result.failures ? `${result.failures} test(s) failed` : "All tests passed");
process.exit(result.failures ? 1 : 0);
