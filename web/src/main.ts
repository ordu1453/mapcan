import { createApp } from "vue";
import App from "./App.vue";
import { installDeleteShortcut } from "./edit";
import { installShortcuts, startEvents } from "./store";
import "./style.css";

createApp(App).mount("#app");
installShortcuts();
installDeleteShortcut();
startEvents();
