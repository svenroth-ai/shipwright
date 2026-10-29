// The fixture the operator run builds from, and the profile it must resolve to. One place, so the spec, the
// project checks and the unit tests cannot drift apart. Paths are resolved from the repo root.
//
// Two fixtures exist: `social-engagement-board` (tabs, local seed; the default, unchanged) and
// `social-engagement-real` (master-detail, source adapter with recorded answers). `SHIPWRIGHT_E2E_FIXTURE` picks one;
// the board checks S02, S04 and S05 then run in the matching form (src/variant.ts).
import path from "node:path";

export const FIXTURE_NAME = "social-engagement-board";
export const REAL_FIXTURE_NAME = "social-engagement-real";
export const PROFILE = "skill-companion-app";
/** Platforms of the fixture's board, in tab order. */
export const PLATFORMS = ["Reddit", "Hacker News", "LinkedIn"] as const;
export const STATUSES = ["new", "drafted", "posted"] as const;
/** Statuses a list row of the real-skill variant can show (`expired` is derived from the age, never stored). */
export const REAL_STATUSES = ["new", "drafted", "posted", "skipped", "expired"] as const;

export type FixtureName = typeof FIXTURE_NAME | typeof REAL_FIXTURE_NAME;

/** The fixture this run uses. An unknown name is refused, not defaulted: a typo must not silently run the other app. */
export function activeFixture(env: NodeJS.ProcessEnv = process.env): FixtureName {
  const name = (env.SHIPWRIGHT_E2E_FIXTURE ?? "").trim();
  if (name === "") return FIXTURE_NAME;
  if (name === FIXTURE_NAME || name === REAL_FIXTURE_NAME) return name;
  throw new Error(`SHIPWRIGHT_E2E_FIXTURE must be ${FIXTURE_NAME} or ${REAL_FIXTURE_NAME}, got "${name}".`);
}

export function fixtureDir(repoRoot: string, name: string = FIXTURE_NAME): string {
  return path.join(repoRoot, "integration-tests", "fixtures", name);
}

export function expectedFile(repoRoot: string, name: string = FIXTURE_NAME): string {
  return path.join(repoRoot, "integration-tests", "fixtures", `${name}-expected-result.md`);
}
