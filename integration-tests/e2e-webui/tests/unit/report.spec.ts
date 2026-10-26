// No browser, no model: report writer, checklist parser, idle watch and the chat hard checks.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { runChatScript, type ChatMap, type Send } from "../../src/chat.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { IdleWatch } from "../../src/idle.js";
import { Report } from "../../src/report.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const fixtures = path.join(repo, "integration-tests", "fixtures");
const expected = fs.readFileSync(path.join(fixtures, "social-engagement-expected-result.md"), "utf8");
const template = fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "report-template.md"), "utf8");
const chatMap = JSON.parse(fs.readFileSync(path.join(fixtures, "social-engagement", "chat-map.json"), "utf8")) as ChatMap;

// @covers FR-01.04
test("the committed checklist has hard and soft items with the ids the spec records", () => {
  const items = parseChecklist(expected);
  expect(items.filter((i) => i.kind === "hard").map((i) => i.id)).toEqual(
    ["H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08", "H09", "H10", "H11"]);
  expect(items.filter((i) => i.kind === "soft").length).toBeGreaterThan(3);
});

// @covers FR-01.04
test("report: every placeholder of the committed template is filled, screenshots are linked", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-rep-"));
  try {
    const list = new Checklist(parseChecklist(expected));
    list.record("H01", "pass", "run status: complete");
    const report = new Report(dir, { authSource: "env token", config: { permission_mode: "plan" } }, list, template);
    const shot = { screenshot: async (o: { path: string }) => fs.writeFileSync(o.path, "png") };
    await report.step("Task page after launch", shot);
    await report.step("Broken shot", { screenshot: async () => { throw new Error("boom"); } });
    report.gate("design review approved");
    report.escalation("idle");
    const file = report.write("aborted");
    const text = fs.readFileSync(file, "utf8");
    expect(text).not.toMatch(/\{\{[A-Z_]+\}\}/);
    expect(text).toContain("Result: aborted");
    expect(text).toContain("![Task page after launch](01-task-page-after-launch.png)");
    expect(fs.existsSync(path.join(report.dir, "01-task-page-after-launch.png"))).toBe(true);
    expect(text).toContain("screenshot failed: boom");
    expect(text).toContain("| H01 | hard |");
    expect(text).toContain("env token");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("idle watch: only a changing snapshot counts as progress", () => {
  let now = 0;
  const watch = new IdleWatch(20 * 60_000, () => now);
  expect(watch.observe("a")).toBe(true);
  now = 19 * 60_000;
  expect(watch.observe("b")).toBe(true);
  now = 38 * 60_000;
  expect(watch.observe("b")).toBe(true);
  now = 39 * 60_000;
  expect(watch.observe("b")).toBe(false);
});

function fakeApp(): Send {
  const status: Record<number, string> = {};
  let fetched = false;
  let keywords = "";
  return async (message) => {
    const m = message.toLowerCase();
    if (m.startsWith("fetch")) {
      const reply = fetched ? "0 new threads" : "9 new threads";
      fetched = true;
      return { reply, pane: { board: true } };
    }
    const id = Number(/\d+/.exec(m)?.[0]);
    if (m.startsWith("show")) return id === 99 ? { reply: "There is no thread 99", pane: {} } : { reply: `Thread ${id}`, pane: { id } };
    if (m.startsWith("draft")) { status[id] = "drafted"; return { reply: "Draft stored", pane: { id, draft: "Hi", status: "drafted" } }; }
    if (m.startsWith("mark")) {
      if (status[id] !== "drafted") return { reply: "Only a drafted thread can be marked", pane: {} };
      status[id] = "posted";
      return { reply: "Thread marked posted", pane: { id, status: "posted" } };
    }
    keywords = message.split(":")[1] ?? "";
    return { reply: `Keywords: ${keywords}`, pane: { keywords } };
  };
}

// @covers FR-01.04
test("chat hard checks pass against a faithful app and fail against a broken one", async () => {
  const good = new Checklist(parseChecklist(expected));
  await runChatScript(fakeApp(), chatMap, good);
  const verdicts = Object.fromEntries(good.items.filter((i) => i.kind === "hard").map((i) => [i.id, i.verdict]));
  for (const id of ["H06", "H07", "H08", "H09", "H10", "H11"]) expect(verdicts[id], id).toBe("pass");

  const bad = new Checklist(parseChecklist(expected));
  const app = fakeApp();
  await runChatScript(async (m) => (m.startsWith("mark") ? { reply: "Thread marked posted", pane: { status: "posted" } } : app(m)), chatMap, bad);
  expect(bad.items.find((i) => i.id === "H09")!.verdict).toBe("fail");

  const down = new Checklist(parseChecklist(expected));
  const log = await runChatScript(async () => { throw new Error("connection refused"); }, chatMap, down);
  expect(log.every((e) => e.error)).toBe(true);
  expect(down.items.find((i) => i.id === "H11")!.verdict).toBe("fail");
});

// @covers FR-01.04
test("project file checks: complete project passes H01-H04, a missing screen fails H04", async () => {
  const { checkProjectFiles } = await import("../../src/progress.js");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-proj-"));
  try {
    const mockups = path.join(fixtures, "social-engagement", "mockups");
    const designs = path.join(dir, ".shipwright", "designs");
    fs.mkdirSync(path.join(designs, "uploads"), { recursive: true });
    fs.mkdirSync(path.join(designs, "screens"), { recursive: true });
    for (const m of fs.readdirSync(mockups)) {
      fs.copyFileSync(path.join(mockups, m), path.join(designs, "uploads", m));
      fs.copyFileSync(path.join(mockups, m), path.join(designs, "screens", m));
    }
    fs.writeFileSync(path.join(dir, "shipwright_run_config.json"),
      JSON.stringify({ status: "complete", profile: "chat-first-json", brief_dir: "brief", phase_tasks: [] }));
    const ok = new Checklist(parseChecklist(expected));
    checkProjectFiles(dir, path.join(fixtures, "social-engagement"), ok);
    expect(["H01", "H02", "H03", "H04"].map((id) => ok.items.find((i) => i.id === id)!.verdict)).toEqual(["pass", "pass", "pass", "pass"]);
    fs.rmSync(path.join(designs, "screens", "05-keywords.html"));
    const bad = new Checklist(parseChecklist(expected));
    checkProjectFiles(dir, path.join(fixtures, "social-engagement"), bad);
    expect(bad.items.find((i) => i.id === "H04")!.verdict).toBe("fail");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("screenshot check from the Test phase fills S03 and the report; absent reads as not recorded", async () => {
  const { readScreenshotCheck, recordScreenshotCheck } = await import("../../src/progress.js");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-shot-"));
  try {
    const absent = readScreenshotCheck(dir);
    expect(absent.status).toBe("not recorded");
    const none = new Checklist(parseChecklist(expected));
    recordScreenshotCheck(none, absent);
    expect(none.items.find((i) => i.id === "S03")!.verdict).toBe("not evaluated");

    fs.writeFileSync(path.join(dir, "shipwright_test_results.json"), JSON.stringify({ screenshot_check: {
      applies: true, status: "pass", metric: "grid-luma-occupancy-diff-ratio", tolerance: 0.15, passed: 1, total: 1,
      screens: [{ mockup: "01-board-new.html", route: "/", status: "pass", diff_ratio: 0.02 }] } }));
    const got = readScreenshotCheck(dir);
    expect(got.summary).toContain("tolerance: 0.15");
    expect(got.summary).toContain("01-board-new.html (/): pass, diff_ratio 0.02");
    const list = new Checklist(parseChecklist(expected));
    recordScreenshotCheck(list, got);
    expect(list.items.find((i) => i.id === "S03")!.verdict).toBe("pass");
    const report = new Report(dir, { authSource: "env token", config: {} }, list, template);
    report.setScreenshotCheck(got.summary);
    expect(report.render("x")).toContain("diff_ratio 0.02");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
