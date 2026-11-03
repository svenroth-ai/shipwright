// The screen tour of the baseline fixture: one app screenshot beside each approved mockup. Every screen of screen-map.json has a
// recipe that brings the board into the state the mockup shows (select a thread, pick a filter, narrow the window) and then CHECKS
// a marker of that state. A state that cannot be reached is written into the report; the wrong screenshot is never attached.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import type { Page } from "@playwright/test";
import { findItem, mainText, openBoard, openThread, rowTitle, setFilter } from "./board-ui.js";
import type { BoardEnv } from "./checks-board.js";
import { post, str } from "./http.js";
import type { Report } from "../report.js";

export interface Reach { reached: boolean; note: string; page?: Page }
type Recipe = (b: BoardEnv) => Promise<Reach>;
const ok = (note: string, page?: Page): Reach => ({ reached: true, note, page });
const no = (note: string): Reach => ({ reached: false, note });
const text = async (p: Page, re: RegExp) => re.test(await mainText(p));

export const RECIPES: Record<string, Recipe> = {
  "list-thread": async (b) => {
    await openBoard(b.page, b.origin);
    await setFilter(b.page, "Open");
    return (await text(b.page, /Our angle/)) ? ok("The Open list with the first thread selected.") : no("the first thread did not show its summary");
  },
  "draft-card": async (b) => {
    await openBoard(b.page, b.origin);
    await openThread(b.page, findItem(b.items, "reddit:1oq7k2m"));
    await b.page.getByText(/Jump to the draft/i).first().click({ timeout: 4000 }).catch(() => undefined);
    return (await b.page.getByText(/^Draft reply/i).count()) > 0 ? ok("reddit:1oq7k2m opened at its draft card.") : no("no 'Draft reply' card on the opened thread");
  },
  posted: async (b) => {
    await openBoard(b.page, b.origin);
    await setFilter(b.page, "Posted");
    return (await text(b.page, /posted/i)) && (await text(b.page, /mq2bZZ1|Reopen/)) ? ok("The Posted filter with the posted thread.") : no("the Posted filter did not show a posted thread");
  },
  "feedback-saved": async (b) => {
    await openBoard(b.page, b.origin);
    await openThread(b.page, findItem(b.items, FEEDBACK_SCREENS.open.key));
    const fb = feedbackFromMockup(mockupHtml(b.fixtureDir, FEEDBACK_SCREENS.open.mockup), "open");
    return fb && (await mainText(b.page)).includes(fb.text.slice(0, 30)) ? ok("hn:46080002 with its open feedback entry (created by the stand-in agent from the mockup's text).") : no("the open feedback entry of mockup 04 was not shown on hn:46080002");
  },
  expired: async (b) => {
    await openBoard(b.page, b.origin);
    await setFilter(b.page, "Expired");
    const gone = b.items.find((i) => i.status === "expired");
    return gone && (await mainText(b.page)).includes(rowTitle(gone).slice(0, 30)) ? ok("The Expired filter, listing an expired thread.") : no("the Expired filter did not list an expired thread");
  },
  "x-count": async (b) => {
    await openBoard(b.page, b.origin);
    await openThread(b.page, b.items.find((i) => i.platform === "x") ?? {});
    return (await text(b.page, /\d+\s*\/\s*280/)) ? ok("The X thread with its character count.") : no("the X thread showed no n/280 count");
  },
  "phone-picker": async (b) => {
    const page = await b.newPage(390);
    await openBoard(page, b.origin);
    return (await page.locator("select").first().isVisible().catch(() => false)) ? ok("The board at 390 px width.", page) : (await page.context().close(), no("no thread picker at 390 px width"));
  },
};

const unescape = (s: string): string => s.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

/** A feedback entry of an approved mockup: the person's note and, for a closed entry, the agent's closing note. */
export function feedbackFromMockup(html: string, chip: "open" | "applied"): { text: string; note: string } | null {
  const m = new RegExp(`<span class="chip ${chip}">${chip}</span>[^<]*</div>\\s*<pre>([^<]+)</pre>(?:\\s*<div class="h">\\s*(?:\\u2192|&rarr;)\\s*([^<]+)</div>)?`).exec(html);
  return m ? { text: unescape(m[1]).trim(), note: unescape(m[2] ?? "").trim() } : null;
}

const mockupHtml = (fixtureDir: string, name: string): string => fs.readFileSync(path.join(fixtureDir, "mockups", name), "utf8");
export const FEEDBACK_SCREENS = { applied: { mockup: "01-list-thread.html", key: "reddit:1oq7k2m" }, open: { mockup: "04-feedback-saved.html", key: "hn:46080002" } } as const;

/** The stand-in agent's feedback state of the mockups: a closed entry on reddit:1oq7k2m (mockup 01), an open one on hn:46080002 (mockup 04). Returns what could not be made. */
export async function standInFeedback(b: Pick<BoardEnv, "api">, fixtureDir: string): Promise<string> {
  const missing: string[] = [];
  for (const chip of ["applied", "open"] as const) {
    const { mockup, key } = FEEDBACK_SCREENS[chip];
    const fb = feedbackFromMockup(mockupHtml(fixtureDir, mockup), chip);
    if (!fb) { missing.push(`${mockup} holds no ${chip} feedback entry in the expected markup`); continue; }
    const made = await post(b.api, "/api/feedback", { key, text: fb.text });
    if (chip === "applied") await post(b.api, `/api/feedback/${str((made.json as { id?: string }).id)}/resolve`, { status: "applied", note: fb.note || "Done." });
  }
  return missing.length ? `Stand-in feedback not created: ${missing.join("; ")}.` : "";
}

export async function tourBaseline(b: BoardEnv, mock: Page, fixtureDir: string, report: Report): Promise<void> {
  const screens = (JSON.parse(fs.readFileSync(path.join(fixtureDir, "screen-map.json"), "utf8")) as { screens: { id: string; mockup: string }[] }).screens;
  for (const screen of screens) {
    let reach: Reach;
    try {
      const recipe = RECIPES[screen.id];
      reach = recipe ? await recipe(b) : no(`the harness has no recipe for the screen id '${screen.id}'`);
    } catch (error) {
      reach = no((error as Error).message.split("\n")[0]);
    }
    const file = `mockup-${screen.id}.png`;
    await mock.goto(pathToFileURL(path.join(fixtureDir, "mockups", screen.mockup)).href);
    await mock.screenshot({ path: path.join(report.dir, file), fullPage: true, timeout: 30_000 });
    if (reach.reached) await report.step(`Screen ${screen.id}`, reach.page ?? b.page, `First image: approved mockup. Second image: built screen. ${reach.note}`, [file]);
    else await report.step(`Screen ${screen.id}`, null, `STATE NOT REACHED: ${reach.note}. No built-screen image is attached; only the approved mockup is shown, so no wrong screen is compared.`, [file]);
    if (reach.page) await reach.page.context().close();
  }
}
