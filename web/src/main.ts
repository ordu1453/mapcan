import { createApp } from "vue";
import App from "./App.vue";
import { installDeleteShortcut } from "./edit";
import { t } from "./i18n";
import { installShortcuts, startEvents } from "./store";
import "./style.css";

// Settings saved before canmap was renamed to mapcan: theme, PDF template etc.
try {
  for (const key of Object.keys(localStorage)) {
    if (!key.startsWith("canmap-")) continue;
    const next = "mapcan-" + key.slice("canmap-".length);
    const value = localStorage.getItem(key);
    if (localStorage.getItem(next) === null && value !== null)
      localStorage.setItem(next, key === "canmap-pdf-template" && value === "canmap" ? "mapcan" : value);
    localStorage.removeItem(key);
  }
} catch {
  /* storage is not available */
}

document.title = t("mapcan — map editor");
createApp(App).mount("#app");
installShortcuts();
installDeleteShortcut();
startEvents();
