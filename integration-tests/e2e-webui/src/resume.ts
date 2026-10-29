// Run resume: a stopped run (idle abort, budget, crash) leaves its run folder behind. Restarting from scratch costs
// 70-80 minutes, so the operator may name that folder (SHIPWRIGHT_E2E_RESUME_RUN) and the spec continues in it.
// A resumed run must not mix states: the folder is reused ONLY when it records the same fixture, package hash,
// profile and plugin commit as this run. Anything else is refused. The folder is operator input and untrusted:
// it must be a direct, non-link run-* child of the workdir.
import fs from "node:fs";
import path from "node:path";

export const MANIFEST_NAME = "run-manifest.json";

export interface RunIdentity {
  fixture: string;
  packageSha256: string;
  profile: string;
  /** git HEAD of the checkout whose plugins the run loads. */
  commit: string;
}

export interface ResumePlan {
  runDir: string;
  tempHome: string;
  projectPath: string;
  /** Steps of the first part that are skipped because the earlier run did them. */
  skipPackageCopy: boolean;
  skipStartPipeline: boolean;
  reused: string[];
  note: string;
}

export class ResumeError extends Error {}

export function writeManifest(runDir: string, identity: RunIdentity, now: Date = new Date()): void {
  fs.writeFileSync(path.join(runDir, MANIFEST_NAME), JSON.stringify({ ...identity, created: now.toISOString() }, null, 2), { mode: 0o600 });
}

/** The spec calls this when every check ran: only then is a folder "done" and no longer resumable. */
export function markFinished(runDir: string): void {
  const file = path.join(runDir, MANIFEST_NAME);
  const m = readJson(file);
  if (m) fs.writeFileSync(file, JSON.stringify({ ...m, finished: new Date().toISOString() }, null, 2), { mode: 0o600 });
}

function readJson(file: string): Record<string, unknown> | null {
  try {
    const v = JSON.parse(fs.readFileSync(file, "utf8")) as unknown;
    return v && typeof v === "object" ? (v as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Validates the folder and says which steps can be skipped. Throws ResumeError with the reason. */
export function planResume(requested: string, workdir: string, current: RunIdentity): ResumePlan {
  const work = fs.realpathSync(path.resolve(workdir));
  const asked = path.resolve(requested);
  if (path.dirname(asked) !== path.resolve(workdir) && path.dirname(asked) !== work) {
    throw new ResumeError(`Refusing to resume: ${requested} is not a direct child of the workdir ${workdir}.`);
  }
  if (!/^run-[A-Za-z0-9]+$/.test(path.basename(asked))) throw new ResumeError("Refusing to resume: the folder name must be run-<id>.");
  let stat: fs.Stats;
  try {
    stat = fs.lstatSync(asked);
  } catch {
    throw new ResumeError(`Refusing to resume: ${requested} does not exist.`);
  }
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw new ResumeError("Refusing to resume: the run folder must be a real directory, not a link.");

  const earlier = readJson(path.join(asked, MANIFEST_NAME));
  if (!earlier) throw new ResumeError(`Refusing to resume: ${MANIFEST_NAME} is missing or unreadable (the earlier run did not record its identity).`);
  const differs = (["fixture", "packageSha256", "profile", "commit"] as const)
    .filter((k) => earlier[k] !== current[k])
    .map((k) => `${k}: earlier ${String(earlier[k])}, now ${current[k]}`);
  if (differs.length > 0) throw new ResumeError(`Refusing to resume: the earlier run differs from this one (${differs.join("; ")}).`);

  const projectPath = path.join(asked, "project");
  const tempHome = path.join(asked, "home");
  if (!fs.existsSync(projectPath) || !fs.existsSync(tempHome)) throw new ResumeError("Refusing to resume: the folder has no project/ and home/.");
  for (const sub of [projectPath, tempHome, path.join(tempHome, ".claude"), path.join(tempHome, ".claude", ".credentials.json"), path.join(tempHome, ".claude.json"), path.join(tempHome, ".claude", "settings.json"), path.join(tempHome, ".claude", "plugins"), path.join(tempHome, ".gitconfig"),
    ...["installed_plugins.json", "known_marketplaces.json", "cache", "cache/shipwright"].map((n) => path.join(tempHome, ".claude", "plugins", n))]) {
    // home/ is where the login is copied to and deleted from: a link there could point at the real HOME.
    if (fs.lstatSync(sub, { throwIfNoEntry: false })?.isSymbolicLink()) throw new ResumeError(`Refusing to resume: ${path.basename(sub)} inside the run folder is a link.`);
  }
  const config = readJson(path.join(projectPath, "shipwright_run_config.json"));
  // A completed PIPELINE is resumable while the checks after it have not finished (a crash during preview or checks).
  if (earlier.finished) throw new ResumeError("Refusing to resume: the earlier run already finished all its checks; start a new run.");
  const brief = readJson(path.join(projectPath, "brief", "brief.json"));
  const packageThere = brief !== null && brief.package_sha256 === current.packageSha256;
  if (fs.existsSync(path.join(projectPath, "brief")) && !packageThere) {
    throw new ResumeError("Refusing to resume: brief/ in the project is not the package of this run.");
  }

  const reused = ["temp HOME", "project folder"];
  if (packageThere) reused.push("package copy in brief/");
  if (config) reused.push(`pipeline already started (status ${String(config.status)})`);
  return {
    runDir: asked, tempHome, projectPath,
    skipPackageCopy: packageThere,
    skipStartPipeline: config !== null,
    reused,
    note: `Resumed from ${path.basename(asked)} (commit ${current.commit}, package ${current.packageSha256.slice(0, 12)}). Steps reused: ${reused.join(", ")}. Not reused: the WebUI instance and every check (they run again).`,
  };
}
