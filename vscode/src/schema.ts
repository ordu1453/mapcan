// The JSON Schema of the format for the YAML extension (redhat.vscode-yaml): completion and hovers of keys in every
// map and every file a map includes, told apart by their text (the YAML extension itself only knows file names),
// with no "# yaml-language-server: $schema=" line needed. The schemas come with the extension (esbuild.mjs copies
// them from ../schema), so they work offline. A $schema line in a map still takes precedence.

import * as fs from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import { isMap, isPart } from "./tree";

const SCHEME = "mapcan-schema";
const FILES: Record<string, string> = { "v1.json": "mapcan.schema.json", "part-v1.json": "mapcan-part.schema.json" };

/** The part of the YAML extension's API used here. */
interface YamlApi {
  registerContributor(
    schema: string,
    requestSchema: (resource: string) => string | undefined,
    requestSchemaContent: (uri: string) => string | undefined,
  ): boolean;
}

/** The schema of an open document, if it is a map or a file a map includes. */
export function schemaOf(resource: string): string | undefined {
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === resource);
  if (!isMap(doc)) return undefined;
  return `${SCHEME}://schema/${isPart(doc) ? "part-v1.json" : "v1.json"}`;
}

export function registerSchemas(context: vscode.ExtensionContext): void {
  let done = false;
  const register = async (): Promise<void> => {
    const ext = vscode.extensions.getExtension<YamlApi>("redhat.vscode-yaml");
    if (done || !ext) return;
    done = true;
    try {
      const api = ext.isActive ? ext.exports : await ext.activate();
      api.registerContributor(SCHEME, schemaOf, (uri) => {
        const file = FILES[vscode.Uri.parse(uri).path.slice(1)];
        return file ? fs.readFileSync(path.join(context.extensionPath, "dist", "schema", file), "utf8") : undefined;
      });
    } catch (err) {
      console.error(err);
    }
  };
  void register();
  // The YAML extension installed later
  context.subscriptions.push(vscode.extensions.onDidChange(() => void register()));
}
