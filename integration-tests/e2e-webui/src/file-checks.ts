// The checks that read the finished project from disk (no browser): moved out of the spec so it stays under the file cap.
import path from "node:path";
import { runStatic } from "./baseline/suite.js";
import type { Checklist } from "./checklist.js";
import { checkProjectFiles, listHtml, readScreenshotCheck, recordScreenshotCheck } from "./progress.js";
import { checkPluginShape, checkScreensComposed, checkTestsRan } from "./project-checks.js";
import type { Report } from "./report.js";
import { checkSkillTriggers } from "./skill-trigger.js";
import type { variantFor } from "./variant.js";

export interface FileCheckInput {
  projectPath: string;
  fixtureDir: string;
  checklist: Checklist;
  report: Report;
  /** The baseline fixture runs the static suite; the other fixtures bring a variant. */
  variant: ReturnType<typeof variantFor> | null;
  tempHome: string;
}

export async function runFileChecks({ projectPath, fixtureDir, checklist, report, variant, tempHome }: FileCheckInput): Promise<void> {
  checkProjectFiles(projectPath, fixtureDir, checklist);
  const shot = readScreenshotCheck(projectPath);
  report.setScreenshotCheck(shot.summary);
  recordScreenshotCheck(checklist, shot);
  checkPluginShape(projectPath, checklist);
  checkScreensComposed(projectPath, listHtml(path.join(fixtureDir, "mockups")), checklist);
  if (variant) variant.selfContained(projectPath, checklist);
  else await runStatic(projectPath, checklist);
  checkTestsRan(projectPath, checklist);
  if (checklist.items.some((i) => i.id === "S09")) {
    checkSkillTriggers(projectPath, checklist, { ...process.env, HOME: tempHome, USERPROFILE: tempHome }, undefined, variant ? undefined : "open the reply board");
  }
}
