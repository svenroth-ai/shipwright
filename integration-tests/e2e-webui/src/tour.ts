// Walks the built app in the browser: one screenshot per chat command, each beside the approved mockup.
// The hard checks already ran over the API (chat.ts); a missing chat box here is recorded, never fatal.
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import type { Page } from "@playwright/test";
import { commandFor, type ChatMap } from "./chat.js";
import type { Report } from "./report.js";

interface ScreenMap {
  screens: { id: string; mockup: string }[];
}

const COMMANDS = ["fetch-matches", "show-thread", "draft-reply", "mark-posted", "set-keywords"];

export async function tourApp(app: Page, mockPage: Page, fixtureDir: string, report: Report): Promise<void> {
  const chatMap = JSON.parse(fs.readFileSync(path.join(fixtureDir, "chat-map.json"), "utf8")) as ChatMap;
  const screenMap = JSON.parse(fs.readFileSync(path.join(fixtureDir, "screen-map.json"), "utf8")) as ScreenMap;
  await report.step("Built app, first view", app, `URL: ${app.url()}`);

  for (const id of COMMANDS) {
    const say = commandFor(chatMap, id);
    const screenId = chatMap.capabilities.find((c) => c.id === id)?.screen ?? id;
    const mockup = screenMap.screens.find((s) => s.id === screenId)?.mockup;
    let note = `Chat command: \`${say}\`. First image: approved mockup. Second image: built screen.`;
    try {
      const box = app.getByRole("textbox").first();
      await box.fill(say, { timeout: 10_000 });
      await box.press("Enter");
      await app.waitForTimeout(1500);
    } catch (error) {
      note += ` The chat box could not be driven: ${(error as Error).message.split("\n")[0]}`;
    }
    const images: string[] = [];
    if (mockup) {
      const file = `mockup-${screenId}.png`;
      await mockPage.goto(pathToFileURL(path.join(fixtureDir, "mockups", mockup)).href);
      await mockPage.screenshot({ path: path.join(report.dir, file), fullPage: true });
      images.push(file);
    }
    await report.step(`Screen ${screenId}`, app, note, images);
  }
}
