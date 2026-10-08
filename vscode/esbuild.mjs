// Bundles the extension into dist/extension.js (the vscode module is provided by the editor) and the node
// form's webview script into dist/webview/form.js, together with the forms shared with the web editor
// (../web/src/form).
import * as esbuild from "esbuild";

const watch = process.argv.includes("--watch");

const common = { bundle: true, sourcemap: true, minify: !watch, logLevel: "info" };
const contexts = await Promise.all([
  esbuild.context({
    ...common,
    entryPoints: ["src/extension.ts"],
    outfile: "dist/extension.js",
    external: ["vscode"],
    format: "cjs",
    platform: "node",
    target: "node20",
  }),
  esbuild.context({
    ...common,
    entryPoints: ["webview/form.js"],
    outfile: "dist/webview/form.js",
    format: "iife",
    platform: "browser",
    target: "es2022",
  }),
]);

if (watch) {
  await Promise.all(contexts.map((c) => c.watch()));
} else {
  await Promise.all(contexts.map((c) => c.rebuild()));
  await Promise.all(contexts.map((c) => c.dispose()));
}
