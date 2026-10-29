// Run resume: a stopped run (idle abort, budget, crash) leaves its run folder behind. Restarting from scratch costs
// 70-80 minutes, so the operator may name that folder (SHIPWRIGHT_E2E_RESUME_RUN) and the spec continues in it.
// A resumed run must not mix states: the folder is reused ONLY when it records the same fixture, package hash,
// profile and plugin commit as this run. Anything else is refused. The folder is operator input and untrusted:
// it must be a direct, non-link run-* child of the workdir.
import fs from "node:fs";
import path from "node:path";

export const MANIFEST_NAME = "run-manifest.json";
export const LOCK_NAME = "run.lock";

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

/** The spec calls this after "New pipeline" was clicked: only then may a resumed run skip that click. A run-config in the folder proves nothing (the pipeline itself can write one). */
export function markPipelineStarted(runDir: string): void {
  const file = path.join(runDir, MANIFEST_NAME);
  const m = readJson(file);
  if (m) fs.writeFileSync(file, JSON.stringify({ ...m, pipelineStarted: new Date().toISOString() }, null, 2), { mode: 0o600 });
}

const alive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === "EPERM"; // exists, but not ours
  }
};

/** Pids a lock names: the spec process and, once the WebUI is up, its server (the agent runs under it and outlives a killed spec). */
function lockedPids(runDir: string): number[] {
  const l = readJson(path.join(runDir, LOCK_NAME));
  const all = [l?.pid, ...(Array.isArray(l?.pids) ? (l.pids as unknown[]) : [])].map(Number);
  return all.filter((n) => Number.isInteger(n) && n > 0);
}

const STALE_HINT = `If no e2e process is running (a pid can be reused by an unrelated program), delete ${LOCK_NAME} in the run folder.`;

/** One live run per folder: the lock names the spec process (and later the WebUI server). A lock whose processes are all gone is stale and taken over. */
export function acquireLock(runDir: string, pid: number = process.pid): void {
  const live = lockedPids(runDir).filter((p) => p !== pid && alive(p));
  if (live.length > 0) throw new ResumeError(`Refusing to use ${path.basename(runDir)}: process ${live[0]} of an earlier run is still alive. Stop it first. ${STALE_HINT}`);
  fs.writeFileSync(path.join(runDir, LOCK_NAME), JSON.stringify({ pid, pids: [] }), { mode: 0o600 });
}

/** Adds the WebUI server pid, so a hard-killed spec whose server and agent keep running still blocks a resume. */
export function addLockPid(runDir: string, pid: number | undefined, owner: number = process.pid): void {
  if (pid === undefined) return;
  const file = path.join(runDir, LOCK_NAME);
  if (Number(readJson(file)?.pid) === owner) fs.writeFileSync(file, JSON.stringify({ pid: owner, pids: [pid] }), { mode: 0o600 });
}

export function releaseLock(runDir: string, pid: number = process.pid): void {
  const file = path.join(runDir, LOCK_NAME);
  if (Number(readJson(file)?.pid) === pid) fs.rmSync(file, { force: true });
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
  if (earlier.commit === "unknown" || current.commit === "unknown") {
    throw new ResumeError("Refusing to resume: the plugin commit is unknown (git failed), so the run cannot be tied to this checkout.");
  }
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
  const live = lockedPids(asked).filter(alive);
  if (live.length > 0) throw new ResumeError(`Refusing to resume: process ${live[0]} of the earlier run is still alive. ${STALE_HINT}`);
  if (earlier.finished) throw new ResumeError("Refusing to resume: the earlier run already finished all its checks; start a new run.");
  const brief = readJson(path.join(projectPath, "brief", "brief.json"));
  const packageThere = brief !== null && brief.package_sha256 === current.packageSha256;
  if (fs.existsSync(path.join(projectPath, "brief")) && !packageThere) {
    throw new ResumeError("Refusing to resume: brief/ in the project is not the package of this run.");
  }

  const reused = ["temp HOME", "project folder"];
  if (packageThere) reused.push("package copy in brief/");
  const started = config !== null && typeof earlier.pipelineStarted === "string";
  if (started) reused.push(`pipeline already started (status ${String(config?.status)})`);
  return {
    runDir: asked, tempHome, projectPath,
    skipPackageCopy: packageThere,
    skipStartPipeline: started,
    reused,
    note: `Resumed from ${path.basename(asked)} (commit ${current.commit}, package ${current.packageSha256.slice(0, 12)}). Steps reused: ${reused.join(", ")}. Not reused: the WebUI instance and every check (they run again).`,
  };
}
