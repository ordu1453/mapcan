import { createApp } from "vue";
import App from "./App.vue";
import { installDeleteShortcut } from "./edit";
import { t } from "./i18n";
import { installShortcuts, startEvents } from "./store";
import "./style.css";

// Настройки, сохранённые до переименования canmap → mapcan: тема, шаблон PDF и т.п.
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
  /* хранилище недоступно */
}

document.title = t("mapcan — редактор карты");
createApp(App).mount("#app");
installShortcuts();
installDeleteShortcut();
startEvents();
