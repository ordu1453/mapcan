// Links to the project on GitHub: the version in the top bar and a line on the start screen.
// They open in the system browser (in the app window too: pywebview opens target="_blank" links there).

export const REPO_URL = "https://github.com/ordu1453/mapcan";
export const DOCS_URL = `${REPO_URL}/blob/main/docs/web.md`;
export const ISSUES_URL = `${REPO_URL}/issues/new`;

/** Release notes of a version (as tagged: vX.Y.Z). */
export const releaseUrl = (version: string): string => `${REPO_URL}/releases/tag/v${version}`;
