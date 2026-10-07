// Generates media/tree/{light,dark}/*.svg — the Map view icons. The shapes are the ones of the web
// editor's tree (web/src/components/TreeIcon.vue); the colors are VS Code's icon foregrounds.
//   node scripts/make-icons.mjs
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const COLORS = { light: "#424242", dark: "#C5C5C5" };

const frame = '<rect x="1.5" y="4.5" width="9" height="7" rx="1"/><path d="M3.5 7h2M3.5 9h4"/>';
const ICONS = {
  bus:
    '<path d="M1.5 6.5h13M1.5 9.5h13"/><path d="M4.5 9.5v3M8 9.5v3M11.5 9.5v3"/>' +
    '<circle cx="4.5" cy="13" r=".6"/><circle cx="8" cy="13" r=".6"/><circle cx="11.5" cy="13" r=".6"/>',
  device:
    '<rect x="4" y="4" width="8" height="8" rx="1"/><rect x="6.3" y="6.3" width="3.4" height="3.4" rx=".4"/>' +
    '<path d="M6 1.8V4M10 1.8V4M6 12v2.2M10 12v2.2M1.8 6H4M1.8 10H4M12 6h2.2M12 10h2.2"/>',
  "frame-tx": frame + '<path d="M11 8h3.5M12.8 6.2 14.5 8l-1.7 1.8"/>',
  "frame-rx": frame + '<path d="M15 8h-3.5M13.2 6.2 11.5 8l1.7 1.8"/>',
  "frame-broadcast": frame + '<path d="M12.3 5.8a3 3 0 0 1 0 4.4"/><path d="M13.8 4.3a5.2 5.2 0 0 1 0 7.4"/>',
  signal: '<path d="M1.5 10.5h2.5v-5h3v5h3v-5h2.5v5h2"/>',
  flag: '<path d="M4 14.5V2"/><path d="M4 2.5h8l-1.8 2.8L12 8H4"/>',
  sdo: '<path d="M2 5.5h10.5M10.5 3.5l2 2-2 2"/><path d="M14 10.5H3.5M5.5 8.5l-2 2 2 2"/>',
};

for (const [theme, color] of Object.entries(COLORS)) {
  const dir = join(root, "media", "tree", theme);
  mkdirSync(dir, { recursive: true });
  for (const [name, body] of Object.entries(ICONS)) {
    writeFileSync(
      join(dir, `${name}.svg`),
      `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" fill="none" ` +
        `stroke="${color}" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">${body}</svg>\n`,
    );
  }
}
