// Accessibility of the main screens with axe-core. The rules the editor does not meet yet are listed in KNOWN and
// tracked in #80; any other violation fails the test, so the editor does not get worse meanwhile.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, openEditor, test } from "./fixtures";

const KNOWN = new Set([
  "color-contrast",                 // muted texts and the colors of the bit layout
  "page-has-heading-one",
  "region",                         // the validation panel is outside the landmarks
  "landmark-no-duplicate-banner",   // the header of a dialog
  "landmark-unique",
]);

async function check(page: Page, screen: string): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).analyze();
  const found = violations.filter((v) => !KNOWN.has(v.id))
    .map((v) => `${screen}: ${v.id} (${v.impact}) ${v.help}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
  expect(found).toEqual([]);
}

test("the start screen", async ({ page, editor }) => {
  await page.goto(editor.url);
  await expect(page.getByRole("button", { name: "Open…" })).toBeVisible();
  await check(page, "start screen");
});

test.describe("a map", () => {
  test.use({ files: { "minimal.yaml": "examples/minimal.yaml" }, open: "minimal.yaml" });

  test("the editor, a signal, the file dialog and the YAML tab", async ({ page, editor }) => {
    await openEditor(page, editor);
    await check(page, "document");
    const tree = page.locator("aside");
    // A click selects a frame, a second one opens it (#146)
    for (const label of ["PMP · Pump", "pump_state", "pump_state", "pressure"]) await tree.getByText(label).first().click();
    await expect(page.getByRole("heading", { name: "Signal pressure" })).toBeVisible();
    await check(page, "signal");
    await page.getByRole("button", { name: "File ▾" }).click();
    await page.getByRole("button", { name: "Open…" }).click();
    await check(page, "file dialog");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    await check(page, "YAML tab");
  });
});
