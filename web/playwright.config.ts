// Browser smoke tests of the web editor (npm run e2e): e2e/*.e2e.ts against `mapcan serve` (e2e/fixtures.ts).
// Chromium of Playwright (npx playwright install chromium); PLAYWRIGHT_CHANNEL=msedge or chrome uses an installed
// browser instead.
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  testMatch: "*.e2e.ts",
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    browserName: "chromium",
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    locale: "en-US",
    viewport: { width: 1280, height: 800 },
    trace: "retain-on-failure",
  },
});
