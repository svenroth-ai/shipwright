// Reads the run's on-disk state in the temp project: phase and task states, file activity, and the hard
// checklist items that need no browser (H01-H04). The spec owns the project directory, so it reads it directly.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";

export interface RunState {
  status: string;
  phases: { phase: string; status: string }[];
  raw: Record<string, unknown> | null;
}

export function readRunState(projectPath: string): RunState {
  const file = path.join(projectPath, "shipwright_run_config.json");
  if (!fs.existsSync(file)) return { status: "missing", phases: [], raw: null };
  try {
    const raw = JSON.parse(fs.readFileSync(file, "utf8")) as Record<string, unknown>;
    const tasks = Array.isArray(raw.phase_tasks) ? (raw.phase_tasks as Record<string, unknown>[]) : [];
    return {
      status: String(raw.status ?? "unknown"),
      phases: tasks.map((t) => ({ phase: String(t.phase ?? "?"), status: String(t.status ?? "?") })),
      raw,
    };
  } catch {
    return { status: "unreadable", phases: [], raw: null };
  }
}

const SKIP = new Set([".git", "node_modules", ".venv", "__pycache__", ".pytest_cache"]);

/** File count and newest modification time: any agent write counts as progress, whatever the terminal shows. */
export function fileActivity(root: string, limit = 5000): string {
  let count = 0;
  let newest = 0;
  const stack = [root];
  while (stack.length > 0 && count < limit) {
    const dir = stack.pop()!;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      if (SKIP.has(e.name)) continue;
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        stack.push(full);
      } else {
        count += 1;
        try {
          newest = Math.max(newest, fs.statSync(full).mtimeMs);
        } catch {
          // file vanished while walking
        }
      }
    }
  }
  return `${count}:${Math.floor(newest)}`;
}

export function phaseSignature(state: RunState): string {
  return `${state.status}|${state.phases.map((p) => `${p.phase}=${p.status}`).join(",")}`;
}

export function listHtml(dir: string): string[] {
  return fs.existsSync(dir) ? fs.readdirSync(dir).filter((f) => f.endsWith(".html")).sort() : [];
}

/** H01-H04: run complete, profile and package recorded, mockups byte-identical, screens present. */
export function checkProjectFiles(projectPath: string, fixtureDir: string, checklist: Checklist): void {
  const state = readRunState(projectPath);
  checklist.record("H01", state.status === "complete" ? "pass" : "fail", `run status: ${state.status}`);

  const raw = state.raw ?? {};
  const blob = JSON.stringify(raw);
  const profileOk = blob.includes("chat-first-json");
  const packageOk = blob.includes("brief_dir") || blob.includes("brief_package");
  checklist.record("H02", profileOk && packageOk ? "pass" : "fail", `profile named: ${profileOk}; package recorded: ${packageOk}`);

  const mockups = listHtml(path.join(fixtureDir, "mockups"));
  const uploads = path.join(projectPath, ".shipwright", "designs", "uploads");
  const identical = mockups.length > 0 && mockups.every((m) => {
    const copy = path.join(uploads, m);
    return fs.existsSync(copy) && fs.readFileSync(copy).equals(fs.readFileSync(path.join(fixtureDir, "mockups", m)));
  });
  checklist.record("H03", identical ? "pass" : "fail", `${mockups.length} approved mockups compared with designs/uploads`);

  const screens = listHtml(path.join(projectPath, ".shipwright", "designs", "screens"));
  const missing = mockups.filter((m) => !screens.includes(m));
  checklist.record("H04", mockups.length > 0 && missing.length === 0 ? "pass" : "fail",
    missing.length === 0 ? `${screens.length} screens, one per approved mockup` : `no screen for: ${missing.join(", ")}`);
}

export interface ScreenshotCheck {
  status: string;
  summary: string;
}

/** The B3c screenshot check the Test phase recorded in the project's shipwright_test_results.json. */
export function readScreenshotCheck(projectPath: string): ScreenshotCheck {
  const none = { status: "not recorded", summary: "not recorded (no screenshot_check block in shipwright_test_results.json)" };
  try {
    const file = path.join(projectPath, "shipwright_test_results.json");
    const block = (JSON.parse(fs.readFileSync(file, "utf8")) as { screenshot_check?: Record<string, unknown> }).screenshot_check;
    if (!block || typeof block !== "object") return none;
    const screens = Array.isArray(block.screens) ? (block.screens as Record<string, unknown>[]) : [];
    const lines = [
      `status: ${String(block.status)}; metric: ${String(block.metric)}; tolerance: ${String(block.tolerance)}; passed ${String(block.passed)} of ${String(block.total)}`,
      ...screens.map((s) => `- ${String(s.mockup)} (${String(s.route)}): ${String(s.status)}, diff_ratio ${String(s.diff_ratio)}`),
    ];
    return { status: String(block.status), summary: lines.join("\n") };
  } catch {
    return none;
  }
}

/** Fills soft item S03 from the recorded check; an absent check stays "not evaluated". */
export function recordScreenshotCheck(checklist: Checklist, check: ScreenshotCheck): void {
  if (check.status === "not recorded") return checklist.record("S03", "not evaluated", "screenshot check not recorded");
  checklist.record("S03", check.status === "pass" ? "pass" : "fail", `Test phase screenshot check: ${check.status}`);
}
