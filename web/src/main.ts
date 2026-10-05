import { createApp } from "vue";
import App from "./App.vue";
import { installShortcuts, startEvents } from "./store";
import "./style.css";

createApp(App).mount("#app");
installShortcuts();
startEvents();
