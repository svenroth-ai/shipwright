// How the harness drives the built board: the platform switch, the status filter, the thread list. Everything is found by role,
// label and visible text (the approved mockups are the contract), never by class names the building agent may have chosen. The one attribute taken from the approved mockups is `data-k` (the thread key on a list row).
import type { Locator, Page } from "@playwright/test";
import { arr, obj, str, type Obj } from "./http.js";

export const PLATFORM_LABEL: Record<string, string> = { linkedin: "LinkedIn", reddit: "Reddit", hn: "Hacker News", x: "X" };
export interface Count { name: string; count: number }

/** "Hacker News2" / "Open 6" / "Posted\n1" into name and number. */
export function parseCount(text: string): Count | null {
  const m = /^(.*?)\s*(\d+)$/s.exec(text.trim().replace(/\s+/g, " "));
  return m && m[1].trim() ? { name: m[1].replace(/^Status:\s*/i, "").trim(), count: Number(m[2]) } : null;
}

export async function openBoard(page: Page, origin: string, hash = ""): Promise<void> {
  await page.goto(`${origin}/${hash}`, { waitUntil: "domcontentloaded" });
  await page.getByRole("tab").first().waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForTimeout(400);
}

export async function readTabs(page: Page): Promise<Count[]> {
  const texts = await page.getByRole("tab").allInnerTexts();
  return texts.map(parseCount).filter((c): c is Count => c !== null);
}

const filterButton = (page: Page) => page.locator('[aria-haspopup="listbox"]').first();
export const filterLabel = async (page: Page): Promise<Count | null> => parseCount(await filterButton(page).innerText());

/** Options of the status filter with their counts (the list is opened and closed again). */
export async function filterOptions(page: Page): Promise<Count[]> {
  await filterButton(page).click();
  await page.getByRole("option").first().waitFor({ state: "visible", timeout: 5000 });
  const texts = await page.getByRole("option").allInnerTexts();
  await page.keyboard.press("Escape");
  return texts.map(parseCount).filter((c): c is Count => c !== null);
}

export async function setFilter(page: Page, name: string): Promise<void> {
  await filterButton(page).click();
  await page.getByRole("option", { name: new RegExp(`^\\s*${name}\\b`, "i") }).first().click();
  await page.waitForTimeout(300);
}

export async function pickPlatform(page: Page, platform: string): Promise<void> {
  await page.getByRole("tab", { name: new RegExp(`^\\s*${PLATFORM_LABEL[platform] ?? platform}\\b`) }).first().click();
  await page.waitForTimeout(250);
}

/** The text a list row shows for a thread: the title, else the first characters of the post text. */
export function rowTitle(item: Obj): string {
  const post = obj(item.post);
  return (str(post.title) || str(post.text)).slice(0, 60);
}

/**
 * The visible list row of a thread. A bare text lookup finds the thread's title first in the hidden <option> of the phone
 * picker (it repeats every title) and the click then times out; rows carry the thread key in `data-k` (the approved mockups do too).
 */
export function listRow(page: Page, item: Obj): Locator {
  const key = str(item.key);
  const rows = key ? page.locator(`[data-k="${key.replace(/["\\]/g, "\\$&")}"]`) : page.locator("[data-k]").filter({ hasText: rowTitle(item) });
  return rows.filter({ visible: true }).first();
}

/** Visible elements whose own text matches `re`; hidden ones (a banner not yet shown, an unselected option) do not count. */
export const visibleText = (page: Page, re: RegExp): Locator => page.getByText(re).filter({ visible: true });

/** Opens a thread the way a person does: filter All, the thread's platform, the visible row of the thread. */
export async function openThread(page: Page, item: Obj, filter = "All"): Promise<void> {
  if (str(item.platform) === "") throw new Error("the thread this check needs is not in the stored items");
  await setFilter(page, filter);
  await pickPlatform(page, str(item.platform));
  await listRow(page, item).click({ timeout: 8000 });
  await page.waitForTimeout(500);
}

export const mainText = async (page: Page): Promise<string> => {
  const main = page.locator("main");
  return (await main.count()) > 0 ? main.first().innerText() : page.locator("body").innerText();
};

/** Visible elements without element children whose text matches `re`. */
export function leafCount(page: Page, source: string, flags = ""): Promise<number> {
  return page.evaluate(({ source: s, flags: f }) => {
    const re = new RegExp(s, f);
    return [...document.querySelectorAll("body *")].filter((e) => e.children.length === 0 && (e.getClientRects().length > 0) && re.test((e.textContent ?? "").trim())).length;
  }, { source, flags });
}

export const findItem = (items: Obj[], key: string): Obj => items.find((i) => i.key === key) ?? {};
export const itemsOf = (json: unknown): Obj[] => arr(obj(json).items ?? obj(json).threads).map(obj);
