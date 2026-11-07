// No model: the board helpers (tab counts, status filter, picker) read the approved mockups correctly, so the selectors the
// checks use are the ones the approved design offers. The mockups are static pages opened from disk.
import path from "node:path";
import { pathToFileURL } from "node:url";
import { expect, test } from "@playwright/test";
import { filterLabel, filterOptions, readTabs, setFilter } from "../../src/baseline/board-ui.js";
import { BASELINE_FIXTURE_NAME } from "../../src/fixture.js";

const mockups = path.resolve(import.meta.dirname, "..", "..", "..", "fixtures", BASELINE_FIXTURE_NAME, "mockups");
const open = (name: string) => pathToFileURL(path.join(mockups, name)).href;

// @covers FR-01.06
test("the platform switch and the status filter of mockup 01 read as the brief's counts", async ({ page }) => {
  await page.goto(open("01-list-thread.html"));
  expect((await readTabs(page)).map((t) => [t.name, t.count])).toEqual([["LinkedIn", 2], ["Reddit", 1], ["Hacker News", 2], ["X", 1]]);
  expect(await filterLabel(page)).toEqual({ name: "Open", count: 6 });
  // The mockup is a static render without the dropdown script: show the listbox as the built board would after the click.
  await page.evaluate(() => { (document.getElementById("ddmenu") as HTMLElement).hidden = false; });
  expect((await filterOptions(page)).map((o) => [o.name, o.count])).toEqual([["Open", 6], ["Posted", 1], ["Skipped", 1], ["Expired", 3], ["All", 11]]);
  await setFilter(page, "Posted"); // clicks the option (a no-op on the static page, but the option must be findable by role and name)
});

// @covers FR-01.06
test("mockup 07 offers the phone picker the check looks for", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(open("07-phone-picker.html"));
  expect(await page.locator("select").first().isVisible()).toBe(true);
  expect(await page.getByRole("button", { name: "Previous thread" }).count()).toBe(1);
  expect(await page.getByRole("button", { name: "Next thread" }).count()).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(390);
});
