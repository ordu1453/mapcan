// Integration test: starts a separate VS Code with the extension and runs test/suite.cjs.
//   npm test                     downloads VS Code stable into .vscode-test/
//   VSCODE_PATH=…/Code.exe npm test   uses an installed VS Code instead
import { runTests } from "@vscode/test-electron";
import { mkdtempSync } from "node:fs";
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

await runTests({
  vscodeExecutablePath: process.env.VSCODE_PATH || undefined,
  extensionDevelopmentPath: root,
  extensionTestsPath: join(here, "suite.cjs"),
  // --disable-gpu: under xvfb (CI) the window may hang on start with software GL
  launchArgs: [workspace, "--disable-extensions", "--disable-gpu", "--user-data-dir", join(workspace, ".user-data")],
  extensionTestsEnv: { MAPCAN_SERVER: server, MAPCAN_TEST_WORKSPACE: workspace },
});
