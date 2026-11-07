// Re-runs the baseline checks (B01-B46 and the screen tour) against an ALREADY BUILT project, with no pipeline and no model.
// Operator-started, not a CI gate:  SHIPWRIGHT_E2E_RECHECK_PROJECT=<built project> npm run recheck
// Optional: SHIPWRIGHT_E2E_RECHECK_OUT=<folder for the report> (default: <os tmp>/e2e-recheck). Nothing is written into the project.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { Checklist, parseChecklist } from "../src/checklist.js";
import { BASELINE_FIXTURE_NAME, expectedFile, fixtureDir } from "../src/fixture.js";
import { Report } from "../src/report.js";
import { runBaselineSuite, runStatic } from "../src/baseline/suite.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");
const repoRoot = path.resolve(projectRoot, "..", "..");

// @covers FR-01.06
test("re-check the baseline checks against a built project", async ({ page }) => {
  test.setTimeout(30 * 60_000);
  const project = process.env.SHIPWRIGHT_E2E_RECHECK_PROJECT ?? "";
  test.skip(!project, "operator-only: set SHIPWRIGHT_E2E_RECHECK_PROJECT to a built project folder");
  if (!fs.existsSync(path.join(project, "backend"))) throw new Error("Set SHIPWRIGHT_E2E_RECHECK_PROJECT to a built project folder (it holds backend/, board/, skills/).");
  const file = expectedFile(repoRoot, BASELINE_FIXTURE_NAME);
  const checklist = new Checklist(parseChecklist(fs.readFileSync(file, "utf8")));
  const out = process.env.SHIPWRIGHT_E2E_RECHECK_OUT || path.join(os.tmpdir(), "e2e-recheck");
  const report = new Report(out, { authSource: "none (re-check)", config: { project, mode: "re-check of a built project, no pipeline", checklist: checklist.describe(path.basename(file)) } }, checklist, fs.readFileSync(path.join(projectRoot, "report-template.md"), "utf8"));
  try {
    await runStatic(project, checklist);
    await runBaselineSuite({ project, fixtureDir: fixtureDir(repoRoot, BASELINE_FIXTURE_NAME), checklist, report, page });
  } finally {
    report.write("re-check");
    const rows = checklist.items.filter((i) => i.id.startsWith("B"));
    console.log(rows.map((i) => `${i.id} ${i.verdict}${i.verdict === "pass" ? "" : ` - ${i.evidence}`}`).join("\n"));
    console.log(`Re-check report: ${path.join(report.dir, "report.md")}`);
  }
  // a red B item makes the command exit non-zero, and an empty run cannot look like a pass
  const b = checklist.items.filter((i) => i.id.startsWith("B"));
  expect(b.some((i) => i.verdict !== "not evaluated")).toBe(true);
  expect(b.filter((i) => i.kind === "hard" && i.verdict !== "pass").map((i) => i.id)).toEqual([]);
});

