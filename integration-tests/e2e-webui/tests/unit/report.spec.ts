// No browser, no model: report writer, checklist parser, idle watch, terminal menus and the project file checks.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { FIXTURE_NAME } from "../../src/fixture.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { IdleWatch } from "../../src/idle.js";
import { Report } from "../../src/report.js";
import { isDangerousOperationPrompt, needsTerminalAnswer, readTerminalMenu, wantsExemption } from "../../src/terminal-gate.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const fixtures = path.join(repo, "integration-tests", "fixtures");
const expected = fs.readFileSync(path.join(fixtures, `${FIXTURE_NAME}-expected-result.md`), "utf8");
const template = fs.readFileSync(path.resolve(import.meta.dirname, "..", "..", "report-template.md"), "utf8");

// @covers FR-01.06
test("terminal menu: the highlighted first option with its footer, recorded, never twice in 15 seconds", () => {
  const approve = ["Do you approve the mockups?", "❯ 1. Approve mockups", "2. I have feedback", "Enter to select"].join("\n");
  const commit = ["How should I handle the failing check?", "❯ 1. Commit earlier output first", "2. Leave it", "Enter to select"].join("\n");
  expect(needsTerminalAnswer(approve, 0, 1_000_000)).toBe(true);
  expect(readTerminalMenu(commit)).toEqual({ question: "How should I handle the failing check?", option: "Commit earlier output first" });
  expect(needsTerminalAnswer(commit, 990_000, 1_000_000)).toBe(false);
  expect(needsTerminalAnswer(approve.replace("Enter to select", ""), 0, 1_000_000)).toBe(false);
  const scrolled = ["you whether to complete over it.", "2. Stop the run", "Enter to select"].join("\n");
  expect(needsTerminalAnswer(scrolled, 0, 1_000_000)).toBe(true);
  expect(readTerminalMenu(scrolled)?.option).toContain("scrolled out of view");
  expect(needsTerminalAnswer("no menu here", 0, 1_000_000)).toBe(false);
  const firstIsExemption = ["❯ 1. Complete with exemption", "2. Stop the run", "Enter to select"].join("\n");
  expect(wantsExemption(firstIsExemption)).toBe(false);
  const danger = ["Dangerous rm operation on possibly-empty variable path:", "Do you want to proceed?", "❯ 1. Yes", "2. No"].join("\n");
  expect(isDangerousOperationPrompt(danger)).toBe(true);
  expect(isDangerousOperationPrompt(danger.replace("Dangerous rm", "Plain rm"))).toBe(false);
  expect(needsTerminalAnswer(danger, 0, 1_000_000)).toBe(false);
  const exemption = ["2. Complete with exemption", "3. Stop the run", "Enter to select · Esc to cancel"].join("\n");
  expect(wantsExemption(exemption)).toBe(true);
  expect(wantsExemption(exemption.replace("Complete with exemption", "Something"))).toBe(false);
  const submit = ["Review your answers", "Ready to submit your answers?", "❯ 1. Submit answers", "2. Cancel"].join("\n");
  expect(readTerminalMenu(submit)?.option).toBe("Submit answers");
});

// @covers FR-01.06
test("the committed checklist has hard and soft items with the ids the spec records", () => {
  const items = parseChecklist(expected);
  expect(items.filter((i) => i.kind === "hard").map((i) => i.id)).toEqual(
    ["H01", "H02", "H03", "H04", "H05", "H06", "H07", "H08", "H09", "H10", "H11", "H12", "H13", "S01", "S02", "S04", "S05", "S06", "S07", "S08"]);
  expect(items.filter((i) => i.kind === "soft").map((i) => i.id)).toEqual(["S03"]);
});

// @covers FR-01.06
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

// @covers FR-01.06
test("report: the folder name is unpredictable, owner-only on POSIX, and two reports never share a folder", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-rep-"));
  try {
    const when = new Date("2026-01-02T03:04:05.678Z");
    const meta = { authSource: "env token", config: {} };
    const list = new Checklist(parseChecklist(expected));
    const a = new Report(path.join(root, "e2e-report"), meta, list, template, when);
    const b = new Report(path.join(root, "e2e-report"), meta, list, template, when);
    expect(a.dir).not.toBe(b.dir);
    expect(path.basename(a.dir)).toMatch(/^2026-01-02T03-04-05-678Z-[A-Za-z0-9]{6}$/);
    if (process.platform !== "win32") {
      expect(fs.statSync(a.dir).mode & 0o777).toBe(0o700);
      expect(fs.statSync(a.write("complete")).mode & 0o777).toBe(0o600);
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("checklist: a backslash and a pipe in a cell are both escaped, every occurrence", () => {
  const list = new Checklist(parseChecklist(expected));
  list.record("H01", "pass", "a\\|b | c\\d \\ e|f");
  const row = list.toMarkdown().split("\n").find((l) => l.startsWith("| H01 |")) ?? "";
  expect(row).toContain("a\\\\\\|b \\| c\\\\d \\\\ e\\|f");
});

// @covers FR-01.06
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

// @covers FR-01.06
test("project file checks: complete project passes H01-H04, a missing screen fails H04", async () => {
  const { checkProjectFiles } = await import("../../src/progress.js");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-proj-"));
  try {
    const mockups = path.join(fixtures, FIXTURE_NAME, "mockups");
    const designs = path.join(dir, ".shipwright", "designs");
    fs.mkdirSync(path.join(designs, "uploads"), { recursive: true });
    fs.mkdirSync(path.join(designs, "screens"), { recursive: true });
    for (const m of fs.readdirSync(mockups)) {
      fs.copyFileSync(path.join(mockups, m), path.join(designs, "uploads", m));
      fs.copyFileSync(path.join(mockups, m), path.join(designs, "screens", m));
    }
    fs.writeFileSync(path.join(dir, "shipwright_run_config.json"),
      JSON.stringify({ status: "complete", profile: "skill-companion-app", brief_dir: "brief", phase_tasks: [] }));
    const ok = new Checklist(parseChecklist(expected));
    checkProjectFiles(dir, path.join(fixtures, FIXTURE_NAME), ok);
    expect(["H01", "H02", "H03", "H04"].map((id) => ok.items.find((i) => i.id === id)!.verdict)).toEqual(["pass", "pass", "pass", "pass"]);
    fs.rmSync(path.join(designs, "screens", "05-keywords.html"));
    const bad = new Checklist(parseChecklist(expected));
    checkProjectFiles(dir, path.join(fixtures, FIXTURE_NAME), bad);
    expect(bad.items.find((i) => i.id === "H04")!.verdict).toBe("fail");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
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
