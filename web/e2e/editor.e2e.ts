// User flows of the web editor in a browser, each against a `mapcan serve` of its own (fixtures.ts).
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, mapcan, openEditor, repo, test } from "./fixtures";

const tree = (page: Page) => page.locator("aside");

/** Select a node in the tree by the texts of the nodes on the way to it (a closed node on the way opens with its twisty). */
async function select(page: Page, ...labels: string[]): Promise<void> {
  for (const [i, label] of labels.entries()) {
    const row = tree(page).locator(".tree-row").filter({ has: page.getByText(label, { exact: false }) }).first();
    await row.click();
    const twisty = row.locator(".twisty");
    if (i < labels.length - 1 && (await twisty.textContent())?.includes("▸")) await twisty.click();
  }
}

const field = (page: Page, label: string) => page.getByRole("textbox", { name: label });

test.describe("a map opened by mapcan serve", () => {
  test.use({ files: { "minimal.yaml": "examples/minimal.yaml" }, open: "minimal.yaml" });

  test("a field edited in the form goes to the YAML, is saved, survives a reload and is undone", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "pressure");
    await expect(page.getByRole("heading", { name: "Object pressure" })).toBeVisible();

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

  test("a click selects a frame without opening it, a click on the selected frame or its twisty does", async ({ page, editor }) => {
    await openEditor(page, editor);
    await tree(page).getByText("PMP · Pump").click();
    const frame = tree(page).locator(".tree-row").filter({ hasText: "pump_state" });
    const pressure = tree(page).getByText("pressure", { exact: true });
    await frame.click();
    await expect(page.getByRole("heading", { name: /^Frame pump_state/ })).toBeVisible();
    await expect(pressure).toHaveCount(0);
    await frame.click();
    await expect(pressure).toBeVisible();
    await frame.locator(".twisty").click();
    await expect(pressure).toHaveCount(0);
    await frame.locator(".twisty").click();
    await expect(pressure).toBeVisible();
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
    await page.getByRole("button", { name: "+ Field" }).click();
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    const yaml = page.locator(".yaml-editor textarea");
    await expect(yaml).toHaveValue(/ {16}encoding: bitfield\n {16}byte: 2\n {16}byte_length: 2\n {16}flags:\n {18}- bit: 0\n/);
    await expect(yaml).not.toHaveValue(/factor: 0\.01|unit: bar/);
    // No conflicts left between the encoding and its fields
    await expect(page.getByText("✓ map is valid")).toBeVisible();
  });

  test("the bit layout adds signals on purpose only, and dims the others around the selected one", async ({ page, editor }) => {
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
    await expect(page.getByRole("heading", { name: /^Object object/ })).toBeVisible();
    await select(page, "pump_state");
    await cell(60).dblclick();
    await expect.poll(async () => signals(await yamlText())).toBe(before + 2);

    // The selected signal keeps its color without a contour, the others are dimmed, no visible handles
    await select(page, "pressure");
    await expect(cell(16)).toHaveClass(/\bselected\b/);
    expect(await cell(16).evaluate((e) => getComputedStyle(e).opacity)).toBe("1");
    expect(await cell(16).evaluate((e) => getComputedStyle(e, "::after").content)).toBe("none");
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

  test("the multiplexing of a frame is set in the frame: its selector among its signals (#149)", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state");
    const selector = page.getByRole("combobox", { name: /Selector \(mux\)/ });
    await expect(selector).toHaveValue("");
    // Only what has a value table: the enum and the field of the bit field, not the numbers
    await expect(selector.locator("option")).toHaveText(["off — no multiplexing", "mode", "alarms · sensor_state"]);
    await selector.selectOption({ label: "mode" });
    await expect(page.locator(".mux-bar")).toContainText("mode");
    // The selector is not chosen in the signal form any more; a switched signal names its selector values there
    await select(page, "pump_state", "pressure");
    await expect(page.getByRole("checkbox", { name: /mux selector/ })).toHaveCount(0);
    const mux = field(page, "mux (selector values)");
    await mux.fill("1");
    await mux.press("Enter");
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    await expect(page.locator(".yaml-editor textarea")).toHaveValue(/multiplexer: true[\s\S]*mux: 1/);
    await page.getByRole("button", { name: "Editor", exact: true }).click();

    // Off: after a question, the selector values of the signals go too
    await select(page, "pump_state");
    await selector.selectOption("");
    await page.getByRole("button", { name: "Turn off" }).click();
    await page.getByRole("button", { name: "YAML", exact: true }).click();
    await expect(page.locator(".yaml-editor textarea")).not.toHaveValue(/multiplexer|mux:/);
  });

  test("flags of a bit field move by dragging in the layout and together from the table (#150)", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "PMP · Pump", "pump_state", "alarms");
    const yaml = async () => {
      await page.getByRole("button", { name: "YAML", exact: true }).click();
      const text = await page.locator(".yaml-editor textarea").inputValue();
      await page.getByRole("button", { name: "Editor", exact: true }).click();
      return text;
    };
    // All flags one bit higher, in one step
    await page.getByRole("checkbox", { name: "Tick all flags" }).check();
    await page.getByRole("button", { name: "bit +1" }).click();
    await expect.poll(yaml).toMatch(/name: overheat, bit: 1[\s\S]*name: dry_run, bit: 2[\s\S]*name: sensor_state, bit: 5/);

    // In the layout (alarms is byte 1): a click selects a flag, a drag moves the selected one
    const cell = (bit: number) => page.locator(`.bg-cell[title="bit ${bit}"]`);
    await cell(9).click();
    await expect(page.getByRole("heading", { name: /^Flag overheat/ })).toBeVisible();
    await cell(9).hover();
    await page.mouse.down();
    await cell(12).hover();
    await page.mouse.up();
    await expect.poll(yaml).toMatch(/name: overheat, bit: 4/);
    // Over another flag it does not go
    await cell(12).hover();
    await page.mouse.down();
    await cell(13).hover();
    await page.mouse.up();
    await expect.poll(yaml).toMatch(/name: overheat, bit: 4/);
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

test.describe("a map with a table of value_tables in an included file", () => {
  test.use({ files: { "tractor.yaml": "examples/tractor/tractor.yaml",
                      "powertrain.yaml": "examples/tractor/powertrain.yaml" }, open: "tractor.yaml" });

  test("a signal shows the values of its named table, which opens in the YAML tab (#143)", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "CAB · Cab controller", "Cab controls", "PTO request");
    const card = page.locator("section.card", { hasText: "Values from table “switch_states”" });
    await expect(card).toBeVisible();
    // The values come from powertrain.yaml, read-only
    for (const name of ["OFF", "ON", "ERROR", "NOT_AVAILABLE"]) {
      await expect(card.locator(`input[value="${name}"]`)).toBeVisible();
    }
    await expect(card.locator("input").first()).toHaveAttribute("readonly", "");
    await expect(card.getByRole("button", { name: "+ Value" })).toHaveCount(0);
    await expect(card).toContainText("used by signals and flags: 3");
    await card.getByRole("button", { name: "Open in YAML" }).click();
    await expect(page.locator(".gutter .in-node, textarea").first()).toBeVisible();
    await expect(page.getByText("powertrain.yaml").first()).toBeVisible();
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
    await expect(page.getByRole("heading", { name: "Object pressure" })).toBeVisible();
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

test.describe("the object dictionary of a CANopen bus and its devices (#151)", () => {
  test.use({ files: { "od.yaml": "tests/data/canopen-od.yaml" }, open: "od.yaml" });

  const indices = async (page: Page) => (await page.locator(".od-table tr.od-obj td:nth-child(2)").allTextContents()).map((s) => s.split(":")[0]);

  test("SDO uses the shared bit grid and offers descriptions without editable properties", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "Drive", "drive_sdo_rx");
    await expect(page.locator(".sdo-structure .bitgrid")).toBeVisible();
    await expect(page.locator(".sdo-structure .bg-lock")).toHaveCount(4);
    await expect(page.locator(".node-editor .form-rows")).toHaveCount(0);
    await expect(page.locator(".sdo-structure")).toContainText("SDO transfers the objects described");
    await page.locator(".sdo-structure .bg-cell").first().click();
    await expect(page.locator(".sdo-details")).toContainText("WRITE_4_BYTES");
    await page.locator(".sdo-structure .bg-cell").nth(8).click();
    await expect(page.locator(".sdo-details")).toContainText("16-bit index");
    await expect(page.locator(".sdo-details input, .sdo-details select")).toHaveCount(0);
  });

  test("object kind is changed in the dictionary independently of data type", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "Drive");
    await page.getByRole("button", { name: "Object dictionary" }).click();
    const row = page.locator("tr.od-obj").filter({ has: page.locator(".od-name", { hasText: /^map_version$/ }) });
    await expect(row.locator("td").nth(1)).toHaveText("0x2000:00");
    await row.getByRole("combobox", { name: "Object type" }).selectOption("record");
    await expect(row.getByRole("combobox", { name: "Object type" })).toHaveValue("record");
    await expect(page.locator("tr.od-entry").first().locator("td").nth(1)).toHaveText("0x2000:01");
    await row.getByRole("combobox", { name: "Object type" }).selectOption("var");
    await row.locator(".od-name").click();
    const type = page.getByRole("combobox", { name: /Data type/ });
    await expect(type).toHaveValue("unsigned8");
    await expect(type.locator('option[value="array"], option[value="record"]')).toHaveCount(0);
  });
  const area = (page: Page, title: string) => page.locator("tbody").filter({ has: page.locator("tr.od-area", { hasText: title }) });

  test("the bus lists its objects under the headings of the index areas, the standard ones with a tick", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "Bus");
    await page.getByRole("button", { name: "Object dictionary" }).click();
    await expect(page.getByRole("heading", { name: /^Object dictionary Bus/ })).toBeVisible();
    await expect.poll(() => indices(page)).toEqual(["0x100A", "0x1018", "0x2000"]);
    await expect(page.locator("tr.od-area").filter({ hasText: "Overall manufacturer area" })).toBeVisible();
    // A standard object not in the map: its tick puts it there
    await page.getByRole("checkbox", { name: "Include device_type in the map" }).check();
    await expect.poll(() => indices(page)).toEqual(["0x1000", "0x100A", "0x1018", "0x2000"]);
    // An area folds under its heading
    await page.locator("tr.od-area").filter({ hasText: "Communication profile" }).click();
    await expect.poll(() => indices(page)).toEqual(["0x2000"]);
    // The + of an area adds an object at its first free index; a click on it opens its form
    await area(page, "Standardized device profiles").getByRole("button", { name: "New object" }).click();
    await expect.poll(() => indices(page)).toEqual(["0x2000", "0x6000"]);
    await page.locator(".od-table .od-name", { hasText: /^object$/ }).click();
    await expect(page.getByRole("heading", { name: /^Object object/ })).toBeVisible();
    await expect(page.getByRole("combobox", { name: /Data type/ })).toHaveValue("unsigned8");
  });

  test("a device has its manufacturer area with the bus's objects there, locked", async ({ page, editor }) => {
    await openEditor(page, editor);
    await select(page, "Drive");
    await page.getByRole("button", { name: "Object dictionary" }).click();
    await expect(page.getByRole("heading", { name: /^Object dictionary Drive/ })).toBeVisible();
    await expect(page.locator("tr.od-area")).toHaveCount(1);
    await expect.poll(() => indices(page)).toEqual(["0x2000", "0x2100"]);
    const own = page.locator("tr.od-obj").filter({ hasText: "instead of the bus's" });
    await expect(own).toContainText("map_version");
    // An array opened to its entries; a double click renames an entry in place
    await page.locator("tr.od-group .od-twisty").click();
    await page.locator("tr.od-entry .od-name", { hasText: "max_speed" }).dblclick();
    const rename = page.locator("tr.od-entry").getByRole("textbox", { name: "Identifier" });
    await rename.fill("speed_limit");
    await rename.press("Enter");
    await expect(page.locator("tr.od-entry .od-name", { hasText: "speed_limit" })).toBeVisible();
  });
});
