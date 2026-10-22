// User flows of the web editor in a browser, each against a `mapcan serve` of its own (fixtures.ts).
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, mapcan, openEditor, repo, test } from "./fixtures";

const tree = (page: Page) => page.locator("aside");

/** Select a node in the tree by the texts of the nodes on the way to it (a node's children open with a click). */
async function select(page: Page, ...labels: string[]): Promise<void> {
  for (const label of labels) await tree(page).getByText(label, { exact: false }).first().click();
}

const field = (page: Page, label: string) => page.getByRole("textbox", { name: label });

test.describe("a map opened by mapcan serve", () => {
  test.use({ files: { "minimal.yaml": "examples/minimal.yaml" }, open: "minimal.yaml" });

  test("a field edited in the form goes to the YAML, is saved, survives a reload and is undone", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "pressure");
    await expect(page.getByRole("heading", { name: "Signal pressure" })).toBeVisible();

    const factor = field(page, "Factor (scale)");
    await expect(factor).toHaveValue("0.01");
    await factor.fill("0.02");
    await factor.press("Enter");
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();

    await page.getByRole("button", { name: "YAML", exact: true }).click();
    await expect(page.locator(".yaml-editor textarea")).toHaveValue(/\n {16}factor: 0\.02\n/);
    await page.getByRole("button", { name: "Editor", exact: true }).click();

    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
    expect(readFileSync(join(editor.dir, "minimal.yaml"), "utf8")).toMatch(/\n {16}factor: 0\.02\n/);

    // A reload of the page keeps the server's undo history
    await page.reload();
    await select(page, "PMP · Pump", "pump_state", "pressure");
    await expect(field(page, "Factor (scale)")).toHaveValue("0.02");
    await page.getByRole("button", { name: "↶" }).click();
    await expect(field(page, "Factor (scale)")).toHaveValue("0.01");
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeEnabled();
  });

  test("the export preview renders the map", async ({ page, editor }) => {
    await openEditor(page, editor);
    await page.getByRole("button", { name: "Export ▾" }).click();
    await page.getByRole("button", { name: "Markdown", exact: false }).click();
    await expect(page.locator(".md-preview")).toContainText("pump_state");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Export ▾" }).click();
    await page.getByRole("button", { name: "HTML", exact: false }).click();
    await expect(page.frameLocator(".preview-frame").getByText("pump_state").first()).toBeVisible();
  });
});

test.describe("the start screen", () => {
  test("an example is copied to the working folder and opens", async ({ page, editor }) => {
    await page.goto(editor.url);
    await page.getByRole("button", { name: "Minimal" }).click();
    await expect(page.getByRole("heading", { name: "Save a copy of the example" })).toBeVisible();
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(page.getByText("Validation").first()).toBeVisible();
    await expect(tree(page).getByText("Demo bus")).toBeVisible();
    expect(readFileSync(join(editor.dir, "minimal.yaml"), "utf8")).toContain("name: pump_state");
  });

  test("a map is opened in the file dialog, and a validation message selects its node", async ({ page, editor }) => {
    const broken = readFileSync(join(repo, "examples", "minimal.yaml"), "utf8").replace("factor: 0.01\n", "factor: 0,01\n");
    writeFileSync(join(editor.dir, "broken.yaml"), broken);
    await page.goto(editor.url);
    await page.getByRole("button", { name: "Open…" }).click();
    await page.getByText("broken.yaml").dblclick();
    const message = page.locator(".diag-panel li.error").filter({ hasText: "number-comma" });
    await expect(message).toBeVisible();
    await message.click();
    await expect(page.getByRole("heading", { name: "Signal pressure" })).toBeVisible();
  });

  test("a DBC file is imported as a map next to it (#128)", async ({ page, editor }) => {
    execFileSync(mapcan, ["export", "dbc", join(repo, "examples", "minimal.yaml"), "-o", join(editor.dir, "demo.dbc")]);
    await page.goto(editor.url);
    await page.getByRole("button", { name: "Import DBC…" }).click();
    await expect(page.getByRole("heading", { name: "Import DBC" })).toBeVisible();
    await page.getByText("demo.dbc").click();
    await page.getByRole("button", { name: "Import", exact: true }).click();
    const warnings = page.getByRole("heading", { name: "Imported with warnings" });
    await expect(warnings.or(page.getByText("Validation").first())).toBeVisible();
    if (await warnings.isVisible()) await page.getByRole("button", { name: "Close", exact: true }).click();
    await expect(tree(page).getByText("Pump", { exact: true })).toBeVisible();
    expect(existsSync(join(editor.dir, "demo.yaml"))).toBe(true);
  });
});
