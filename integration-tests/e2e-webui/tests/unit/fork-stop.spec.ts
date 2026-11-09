// No browser, no model: the stop point of a partial run, the token read from the env file, the plugin identity of a fork.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { AUTH_KEYS, loadConfig } from "../../src/env.js";
import { pluginFingerprint } from "../../src/run-identity.js";
import { planResume } from "../../src/resume.js";
import { describeStop, parseStopAfter, stopReached } from "../../src/stop-after.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const base = { SHIPWRIGHT_E2E_PERMISSION_MODE: "acceptEdits", SHIPWRIGHT_E2E_WEBUI_DIR: os.tmpdir(), SHIPWRIGHT_E2E_MAX_MINUTES: "90" };

function project(tasks: object[]): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "stop-after-"));
  fs.writeFileSync(path.join(dir, "shipwright_run_config.json"), JSON.stringify({ phase_tasks: tasks }));
  return dir;
}

// @covers FR-01.06
test("a stop point is parsed strictly and reached only when every task of the phase is done", () => {
  expect(parseStopAfter("")).toBeNull();
  expect(parseStopAfter("build:04-board")).toEqual({ phase: "build", split: "04-board" });
  expect(describeStop(parseStopAfter("design")!)).toBe("design");
  for (const bad of ["build:", ":x", "Build", "build 04", "build:../x", "biuld", "build-all:1"]) expect(() => parseStopAfter(bad)).toThrow(/STOP_AFTER/);
  const dir = project([
    { phase: "build", splitId: "04-board", status: "done" },
    { phase: "build", splitId: "05-feedback", status: "in_progress" },
  ]);
  expect(stopReached(dir, { phase: "build", split: "04-board" })).toBe(true);
  expect(stopReached(dir, { phase: "build", split: "05-feedback" })).toBe(false);
  expect(stopReached(dir, { phase: "build", split: null })).toBe(false); // the phase has an open task
  const gap = project([{ phase: "build", splitId: "01", status: "done" }]); // the next split is not appended yet
  expect(stopReached(gap, { phase: "build", split: null })).toBe(false);
  const next = project([{ phase: "build", splitId: "01", status: "done" }, { phase: "test", splitId: null, status: "awaiting_launch" }]);
  expect(stopReached(next, { phase: "build", split: null })).toBe(true);
  const skipped = project([{ phase: "build", splitId: "01", status: "skipped" }, { phase: "test", splitId: null, status: "backlog" }]);
  expect(stopReached(skipped, { phase: "build", split: null })).toBe(true);
  expect(stopReached(dir, { phase: "test", split: null })).toBe(false); // no such task is not "done"
  expect(stopReached(path.join(dir, "missing"), { phase: "build", split: null })).toBe(false);
});

// @covers FR-01.04
test("the auth variables of the env file reach the run, the process env wins, other file values do not", () => {
  const [first] = AUTH_KEYS;
  const read = () => [...AUTH_KEYS.map((k) => `${k}=file-${k}`), "SOMETHING_ELSE=x"].join("\n");
  const fromFile = loadConfig(repo, { ...base }, read).env;
  for (const k of AUTH_KEYS) expect(fromFile[k]).toBe(`file-${k}`);
  const own = loadConfig(repo, { ...base, [first]: "from-process" }, read).env;
  expect(own[first]).toBe("from-process");
  expect(own.SOMETHING_ELSE).toBeUndefined();
  expect(loadConfig(repo, { ...base }, () => null).env[first]).toBeUndefined();
  expect(loadConfig(repo, { ...base, SHIPWRIGHT_E2E_STOP_AFTER: "design" }, () => null).stopAfter).toBe("design");
});

// @covers FR-01.06
test("a commit that only touches the harness keeps the plugin identity; a plugin change does not", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "identity-"));
  const git = (...a: string[]) => execFileSync("git", ["-C", dir, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", ...a], { encoding: "utf8" });
  git("init", "-q");
  for (const d of ["plugins", "shared", "tools"]) fs.mkdirSync(path.join(dir, d));
  for (const f of ["plugins/a.txt", "shared/b.txt", "tools/h.txt"]) fs.writeFileSync(path.join(dir, f), "1");
  git("add", "-A");
  git("commit", "-qm", "one");
  const first = pluginFingerprint(dir);
  expect(first).toMatch(/^plugins:[0-9a-f]{40} shared:[0-9a-f]{40}$/);
  fs.writeFileSync(path.join(dir, "tools/h.txt"), "2");
  git("commit", "-qam", "harness only");
  expect(pluginFingerprint(dir)).toBe(first);
  fs.writeFileSync(path.join(dir, "plugins/a.txt"), "2");
  git("commit", "-qam", "plugin change");
  expect(pluginFingerprint(dir)).not.toBe(first);
});

// @covers FR-01.06
test("a forked run folder names its origin in the resume note", () => {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "fork-work-"));
  const run = path.join(work, "run-fork123abc");
  for (const d of ["project", "home"]) fs.mkdirSync(path.join(run, d), { recursive: true });
  const identity = { fixture: "f", packageSha256: "p".repeat(64), profile: "x", commit: "plugins:a shared:b" };
  fs.writeFileSync(path.join(run, "run-manifest.json"), JSON.stringify({ ...identity, forkedFrom: { run: "run-VZQO3H", at: "build:04-board", commit: "ead65c94cbdbdbae" } }));
  expect(planResume(run, work, identity).note).toMatch(/^Fork of run-VZQO3H at build:04-board \(boundary commit ead65c94c\)\. Resumed from run-fork123abc/);
});
