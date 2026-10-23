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

  test("a new encoding starts with its own fields, and a bit field gets flags", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "pressure");
    const encoding = page.getByRole("combobox", { name: "Encoding" });
    await expect(field(page, "Factor (scale)")).toHaveValue("0.01");

    // number → enum: factor, unit and range go with the former encoding
    await encoding.selectOption("enum");
    await expect(field(page, "Factor (scale)")).toHaveCount(0);
    await expect(page.getByLabel("Unit", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Values" })).toBeVisible();

    // enum → bitfield: the flags table, and a flag added from it
    await encoding.selectOption("bitfield");
    await page.getByRole("button", { name: "+ Flag" }).click();
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    const yaml = page.locator(".yaml-editor textarea");
    await expect(yaml).toHaveValue(/ {16}encoding: bitfield\n {16}byte: 2\n {16}byte_length: 2\n {16}flags:\n {18}- bit: 0\n/);
    await expect(yaml).not.toHaveValue(/factor: 0\.01|unit: bar/);
    // No conflicts left between the encoding and its fields
    await expect(page.getByText("✓ map is valid")).toBeVisible();
  });

  test("the bit layout adds signals on purpose only, and outlines the selected one", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state");
    const cell = (bit: number) => page.locator(`.bg-cell[title="bit ${bit}"]`);
    const yamlText = async () => {
      await page.getByRole("button", { name: "YAML", exact: true }).click();
      const text = await page.locator(".yaml-editor textarea").inputValue();
      await page.getByRole("button", { name: "Editor", exact: true }).click();
      return text;
    };
    const signals = (text: string) => (text.match(/^ {14}- name: /gm) ?? []).length;
    const before = signals(await yamlText());

    // A click on a free bit adds nothing
    await cell(60).click();
    expect(signals(await yamlText())).toBe(before);
    // A drag over two free bits adds a 2-bit signal, a double click a 1-bit one
    await cell(63).hover();
    await page.mouse.down();
    await cell(62).hover();
    await page.mouse.up();
    await expect(page.getByRole("heading", { name: /^Signal signal/ })).toBeVisible();
    await select(page, "pump_state");
    await cell(60).dblclick();
    await expect.poll(async () => signals(await yamlText())).toBe(before + 2);

    // The selected signal: a contour around its bits, the others dimmed, no visible handles
    await select(page, "pressure");
    await expect(cell(16)).toHaveClass(/\bsel-r\b/);
    await expect(cell(23)).toHaveClass(/\bsel-l\b/);
    await expect(cell(24)).toHaveClass(/\bsel-r\b/);
    await expect(cell(32)).not.toHaveClass(/\bselected\b/);
    expect(await cell(32).evaluate((e) => getComputedStyle(e).opacity)).toBe("0.55");
    expect(await cell(16).locator(".grip").evaluate((e) => getComputedStyle(e).backgroundColor)).toBe("rgba(0, 0, 0, 0)");
  });

  test("the first click on a signal in the layout selects it, only the selected one is moved", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state");
    const cell = (bit: number) => page.locator(`.bg-cell[title="bit ${bit}"]`);
    const drag = async (from: number, to: number) => {
      await cell(from).hover();
      await page.mouse.down();
      await cell(to).hover();
      await page.mouse.up();
    };
    // temperature (byte 4) not selected: the drag only selects it
    await drag(33, 34);
    await expect(page.getByRole("heading", { name: /temperature/ })).toBeVisible();
    await expect(cell(32)).toHaveClass(/\bselected\b/);
    await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
    // selected: the same drag moves it by a bit
    await drag(33, 34);
    await expect(cell(33)).toHaveClass(/\bselected\b/);
    await expect(cell(32)).not.toHaveClass(/\bselected\b/);
  });

  test("Esc in a signal goes back to its frame, a field being typed in is written first", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "pressure");
    await field(page, "Identifier").fill("pressure_new");
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: /^Frame pump_state/ })).toBeVisible();
    await expect(page.locator("aside").getByText("pressure_new")).toBeVisible();
    // Esc in a frame stays there
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: /^Frame pump_state/ })).toBeVisible();
  });

  test("a name typed in the form goes to its own signal when another one is clicked in the layout", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "pressure");
    const name = field(page, "Identifier");
    await name.fill("pressure_new");
    await page.locator('.bg-cell[title="bit 32"]').click();
    await expect(page.getByRole("heading", { name: /temperature/ })).toBeVisible();
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    const yaml = page.locator(".yaml-editor textarea");
    await expect(yaml).toHaveValue(/- name: pressure_new\b/);
    await expect(yaml).toHaveValue(/- name: temperature\b/);
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

test.describe("a map with floats of implied length", () => {
  test.use({ files: { "vehicle-can.yaml": "examples/vehicle-can.yaml" }, open: "vehicle-can.yaml" });

  test("a float changed to an enum keeps its position and the layouts stay", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "BMS", "bms_status", "pack_voltage");
    await page.getByRole("combobox", { name: "Encoding" }).selectOption("enum");
    await expect(page.getByText("✓ map is valid")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Frame layout/ })).toBeVisible();
    await expect(page.getByLabel("Length, bits")).toHaveValue("32");
    await page.getByRole("combobox", { name: "Encoding" }).selectOption("number");
    await expect(page.getByLabel("Length, bits")).toHaveValue("32");
    await expect(page.getByText("✓ map is valid")).toBeVisible();
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
