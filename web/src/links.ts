// Links to the project on GitHub: the version in the top bar and a line on the start screen.
// They open in the system browser (in the app window too: pywebview opens target="_blank" links there).

export const REPO_URL = "https://github.com/ordu1453/mapcan";
export const DOCS_URL = `${REPO_URL}/blob/main/docs/web.md`;
export const ISSUES_URL = `${REPO_URL}/issues/new`;

/** A new issue on GitHub with the versions filled in (as the VS Code extension's Report an Issue does); the map
 * itself is not sent. */
export function issueUrl(meta: { version: string; mode?: string; system?: string } | null): string {
  if (!meta) return ISSUES_URL;
  const lines = [`mapcan ${meta.version}, web editor (${meta.mode === "app" ? "mapcan app" : "mapcan serve"})`];
  if (meta.system) lines.push(`Server: ${meta.system}`);
  lines.push(`Browser: ${navigator.userAgent}`);
  return `${ISSUES_URL}?body=${encodeURIComponent(`\n\n---\n${lines.join("\n")}`)}`;
}

/** Release notes of a version (as tagged: vX.Y.Z). */
export const releaseUrl = (version: string): string => `${REPO_URL}/releases/tag/v${version}`;
