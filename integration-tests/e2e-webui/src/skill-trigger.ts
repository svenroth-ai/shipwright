// S09 (soft): does the built plugin's skill trigger in a real Claude session on a trigger phrase? A headless `claude -p`
// session loads the project as a plugin, gets one phrase and may use the Skill tool only; the stream is read for a Skill
// call. Opt-in (`SHIPWRIGHT_E2E_SKILL_TRIGGER=1`): it needs a login and costs one short model call. Fixed argv, no shell.
// The project is model-written data: it is loaded as a plugin directory, never executed by this module.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";

export const TRIGGER_PHRASE = "open the social engagement board";

/** Skill names called in a `--output-format stream-json` transcript (assistant tool_use blocks named Skill). Pure. */
export function skillsCalled(streamJson: string): string[] {
  const out: string[] = [];
  for (const line of streamJson.split(/\r?\n/)) {
    let event: { type?: string; message?: { content?: unknown } };
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    if (event.type !== "assistant" || !Array.isArray(event.message?.content)) continue;
    for (const block of event.message!.content as { type?: string; name?: string; input?: { skill?: unknown } }[]) {
      if (block?.type === "tool_use" && block.name === "Skill") out.push(String(block.input?.skill ?? ""));
    }
  }
  return out;
}

export interface TriggerRun {
  stdout: string;
  status: number | null;
  error?: string;
}
export type Runner = (projectPath: string, phrase: string, env: NodeJS.ProcessEnv) => TriggerRun;

export const runClaude: Runner = (projectPath, phrase, env) => {
  const r = spawnSync("claude", ["-p", phrase, "--output-format", "stream-json", "--verbose", "--plugin-dir", projectPath, "--allowedTools", "Skill", "--max-turns", "2"],
    { cwd: projectPath, env, encoding: "utf8", timeout: 180_000, maxBuffer: 16 * 1024 * 1024 });
  return { stdout: r.stdout ?? "", status: r.status, error: r.error?.message };
};

/** Names under which the project's own skills can be called: `<skill>` and `<plugin>:<skill>` (the provisioned home has other plugins' skills too). */
export function projectSkillNames(projectPath: string): Set<string> {
  const names = new Set<string>();
  let plugin = "";
  try {
    plugin = String((JSON.parse(fs.readFileSync(path.join(projectPath, ".claude-plugin", "plugin.json"), "utf8")) as { name?: unknown }).name ?? "");
  } catch {
    // no readable manifest: only the bare skill names count
  }
  try {
    for (const e of fs.readdirSync(path.join(projectPath, "skills"), { withFileTypes: true })) {
      if (!e.isDirectory() || !fs.existsSync(path.join(projectPath, "skills", e.name, "SKILL.md"))) continue;
      names.add(e.name);
      if (plugin) names.add(`${plugin}:${e.name}`);
    }
  } catch {
    // no skills folder
  }
  return names;
}

/** Records S09: observed when a skill of the project was called, fail-soft otherwise; "not evaluated" when not asked for or the run could not be made. */
export function checkSkillTriggers(projectPath: string, checklist: Checklist, env: NodeJS.ProcessEnv, run: Runner = runClaude): void {
  if (env.SHIPWRIGHT_E2E_SKILL_TRIGGER !== "1") {
    checklist.record("S09", "not evaluated", "not run: set SHIPWRIGHT_E2E_SKILL_TRIGGER=1 to check the trigger in a headless Claude session");
    return;
  }
  const r = run(projectPath, TRIGGER_PHRASE, env);
  if (r.error || r.stdout.trim() === "") {
    const shim = r.error && /ENOENT/.test(r.error) && process.platform === "win32" ? " (on Windows an npm `claude.cmd` shim needs a shell; a native claude.exe on PATH works)" : "";
    checklist.record("S09", "not evaluated", `the session could not be run: ${r.error ?? `no output (exit ${r.status})`}${shim}`);
    return;
  }
  const all = skillsCalled(r.stdout);
  const own = projectSkillNames(projectPath);
  const mine = all.filter((s) => own.has(s));
  const others = all.filter((s) => !own.has(s));
  checklist.record("S09", mine.length > 0 ? "observed" : "fail",
    mine.length > 0 ? `phrase "${TRIGGER_PHRASE}" called the project's skill: ${mine.join(", ")}${others.length ? `; other skills called: ${others.join(", ")}` : ""}`
      : `phrase "${TRIGGER_PHRASE}" did not call a skill of the project within 2 turns (${[...own].join(", ") || "no skills found"}); skills called: ${all.join(", ") || "none"} (exit ${r.status})`);
}
