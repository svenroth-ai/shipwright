// Walks the built board in the browser: one screenshot per approved screen, each beside its mockup. The hard checks
// already ran (board-api.ts, board-dom.ts); a click that cannot be made here is recorded in the step, never fatal.
// The data the earlier API checks left behind decides what each screen shows (posted, drafted, untouched thread).
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import type { Page } from "@playwright/test";
import type { ThreadState } from "./board-api.js";
import type { Report } from "./report.js";

interface ScreenMap {
  screens: { id: string; mockup: string }[];
}

/** What to open on the board for each screen id of the fixture's screen-map.json. */
export function openTarget(screenId: string, state: ThreadState): { thread?: number; text?: RegExp } {
  const byThread = (id: number | null) => (id === null ? {} : { thread: id });
  switch (screenId) {
    case "thread-detail":
    case "thread": return byThread(state.fresh);
    case "reply-draft": return byThread(state.drafted);
    case "thread-posted": return byThread(state.posted);
    case "keywords": return { text: /keywords/i };
    case "sources": return { text: /sources/i };
    default: return {};
  }
}

export async function tourBoard(app: Page, mockPage: Page, origin: string, fixtureDir: string, state: ThreadState, report: Report): Promise<void> {
  const screenMap = JSON.parse(fs.readFileSync(path.join(fixtureDir, "screen-map.json"), "utf8")) as ScreenMap;
  for (const screen of screenMap.screens) {
    let note = "First image: approved mockup. Second image: built screen.";
    try {
      await app.goto(origin, { waitUntil: "domcontentloaded" });
      const target = openTarget(screen.id, state);
      if (target.thread !== undefined) {
        // The thread may sit under another platform's tab: try the tabs until its title is visible.
        const title = state.titles[target.thread] ?? "";
        const tabs = await app.getByRole("tab").all();
        for (const tab of [null, ...tabs]) {
          if (tab) await tab.click({ timeout: 5000 });
          if (await app.getByText(title).first().isVisible().catch(() => false)) break;
        }
        await app.getByText(title).first().click({ timeout: 10_000 });
      } else if (target.text) {
        await app.getByText(target.text).first().click({ timeout: 10_000 });
      }
      await app.waitForTimeout(800);
    } catch (error) {
      note += ` The screen state could not be reached: ${(error as Error).message.split("\n")[0]}`;
    }
    const file = `mockup-${screen.id}.png`;
    await mockPage.goto(pathToFileURL(path.join(fixtureDir, "mockups", screen.mockup)).href);
    await mockPage.screenshot({ path: path.join(report.dir, file), fullPage: true, timeout: 30_000 });
    await report.step(`Screen ${screen.id}`, app, note, [file]);
  }
}
