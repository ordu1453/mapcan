// System file dialogs. Only in the app window (pywebview, mapcan app), not in a browser.

interface PywebviewApi {
  pick_file(mode: "open" | "save", directory: string, filename: string): Promise<string | null>;
}

function nativeApi(): PywebviewApi | null {
  const api = (window as unknown as { pywebview?: { api?: Partial<PywebviewApi> } }).pywebview?.api;
  return api?.pick_file ? (api as PywebviewApi) : null;
}

export const hasNativeDialog = (): boolean => nativeApi() !== null;

export async function nativePick(mode: "open" | "save", directory: string, filename: string): Promise<string | null> {
  const api = nativeApi();
  return api ? api.pick_file(mode, directory, filename) : null;
}
