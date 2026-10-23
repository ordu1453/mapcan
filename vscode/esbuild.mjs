// Bundles the extension into dist/extension.js (the vscode module is provided by the editor) and the node
// form's webview script into dist/webview/form.js, together with the forms shared with the web editor
// (../web/src/form).
import * as esbuild from "esbuild";
import { cpSync, mkdirSync } from "node:fs";

const watch = process.argv.includes("--watch");

// The JSON Schemas of the format for the YAML extension (src/schema.ts)
mkdirSync(new URL("dist/schema/", import.meta.url), { recursive: true });
for (const file of ["mapcan.schema.json", "mapcan-part.schema.json", "mapcan-v1.schema.json", "mapcan-part-v1.schema.json"]) {
  cpSync(new URL(`../schema/${file}`, import.meta.url), new URL(`dist/schema/${file}`, import.meta.url));
}

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
