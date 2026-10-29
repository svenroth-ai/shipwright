// The fixture the operator run builds from, and the profile it must resolve to. One place, so the spec, the
// project checks and the unit tests cannot drift apart. Paths are resolved from the repo root.
import path from "node:path";

export const FIXTURE_NAME = "social-engagement-board";
export const PROFILE = "skill-companion-app";
/** Platforms of the fixture's board, in tab order. */
export const PLATFORMS = ["Reddit", "Hacker News", "LinkedIn"] as const;
export const STATUSES = ["new", "drafted", "posted"] as const;

export function fixtureDir(repoRoot: string): string {
  return path.join(repoRoot, "integration-tests", "fixtures", FIXTURE_NAME);
}

export function expectedFile(repoRoot: string): string {
  return path.join(repoRoot, "integration-tests", "fixtures", `${FIXTURE_NAME}-expected-result.md`);
}
