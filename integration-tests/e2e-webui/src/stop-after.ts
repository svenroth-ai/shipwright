// SHIPWRIGHT_E2E_STOP_AFTER=<phase>[:<split>] ends a run once that phase task is done, so one area can be replayed
// (a fork of an earlier run, then only the phase under test) without waiting for the rest of the pipeline.
import fs from "node:fs";
import path from "node:path";

/** The pipeline phases a task can have; an unknown name would never be reached and the run would silently go to the end. */
export const PHASES = ["project", "design", "plan", "build", "test", "security", "deploy", "changelog"];

export const STOPPED_PREFIX = "stopped-after";

export interface StopSpec {
  phase: string;
  split: string | null;
}

/** "build:04-board" or "design"; anything else is refused at start, so a typo cannot silently run the whole pipeline. */
export function parseStopAfter(raw: string): StopSpec | null {
  if (raw.trim() === "") return null;
  const m = /^([a-z][a-z-]*)(?::([A-Za-z0-9][A-Za-z0-9_-]*))?$/.exec(raw.trim());
  if (!m) throw new Error(`Refusing to start: SHIPWRIGHT_E2E_STOP_AFTER must look like build:04-board or design, got "${raw.slice(0, 60)}".`);
  if (!PHASES.includes(m[1])) throw new Error(`Refusing to start: SHIPWRIGHT_E2E_STOP_AFTER names the unknown phase "${m[1]}" (one of ${PHASES.join(", ")}).`);
  return { phase: m[1], split: m[2] ?? null };
}

export const describeStop = (s: StopSpec): string => (s.split ? `${s.phase}:${s.split}` : s.phase);

const finished = (t: Record<string, unknown>): boolean => t.status === "done" || t.status === "skipped"; // the pipeline counts both as finished

/**
 * True once every task of the phase (of the split, when one is named) is finished and at least one exists. The pipeline
 * appends a phase's next split only after the previous one is done, so a stop on a whole phase also needs proof that the
 * phase is over: a task of another phase after it, or a completed pipeline.
 */
export function stopReached(projectPath: string, spec: StopSpec): boolean {
  try {
    const raw = JSON.parse(fs.readFileSync(path.join(projectPath, "shipwright_run_config.json"), "utf8")) as { status?: string; phase_tasks?: Record<string, unknown>[] };
    const tasks = raw.phase_tasks ?? [];
    const own = tasks.filter((t) => t.phase === spec.phase && (spec.split === null || (t.splitId ?? null) === spec.split));
    if (own.length === 0 || !own.every(finished)) return false;
    if (spec.split !== null) return true;
    const lastOwn = Math.max(...own.map((t) => tasks.indexOf(t)));
    return tasks.slice(lastOwn + 1).some((t) => t.phase !== spec.phase) || raw.status === "complete";
  } catch {
    return false;
  }
}
