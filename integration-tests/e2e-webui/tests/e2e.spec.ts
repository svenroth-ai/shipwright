// Operator-started real end-to-end run: Brief package -> chat-first app, driven through the WebUI like a person.
// NOT a CI gate: it uses a real agent (tokens, wall-clock). See README.md for the operator procedure.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { AuthError, copyLogin, pickAuthSource, realHomeDir, scrubStaleLogins, type AuthSource } from "../src/auth.js";
import { runChatScript } from "../src/chat.js";
import { Checklist, parseChecklist } from "../src/checklist.js";
import * as ui from "../src/driver.js";
import { ConfigError, loadConfig } from "../src/env.js";
import { IDLE_MINUTES, IdleWatch } from "../src/idle.js";
import { checkProjectFiles, fileActivity, phaseSignature, readRunState } from "../src/progress.js";
import { provisionHome } from "../src/provision.js";
import { Report } from "../src/report.js";
import { Shutdown } from "../src/shutdown.js";
import { BUILD_STEP_TIMEOUT_MS, startStack, checkWebuiDir } from "../src/stack.js";
import { tourApp } from "../src/tour.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");
const repoRoot = path.resolve(projectRoot, "..", "..");
const fixtureDir = path.join(repoRoot, "integration-tests", "fixtures", "social-engagement");
const expectedFile = path.join(repoRoot, "integration-tests", "fixtures", "social-engagement-expected-result.md");
const POLL_MS = 15_000;
const PROFILE = "chat-first-json";

function onPath(names: string[]): boolean {
  const dirs = (process.env.PATH ?? "").split(path.delimiter);
  return dirs.some((d) => names.some((n) => d && fs.existsSync(path.join(d, n))));
}

function gitInit(dir: string): void {
  const git = ["-c", "user.name=e2e", "-c", "user.email=e2e@example.com"];
  execFileSync("git", ["-C", dir, "init", "-q"], { stdio: "ignore" });
  execFileSync("git", ["-C", dir, ...git, "commit", "-q", "--allow-empty", "-m", "baseline"], { stdio: "ignore" });
}

// @covers FR-01.04
test("brief package to a working chat-first app through the WebUI", async ({ page }) => {
  test.setTimeout(0);
  // 1. Refuse to start without the operator inputs and an authentication source (no defaults).
  let cfg;
  let authSource: AuthSource;
  const realHome = realHomeDir();
  try {
    cfg = loadConfig(repoRoot);
    authSource = pickAuthSource(process.env, realHome);
  } catch (error) {
    if (error instanceof ConfigError || error instanceof AuthError) throw new Error(error.message);
    throw error;
  }
  if (!onPath(["claude", "claude.exe", "claude.cmd"])) throw new Error("Refusing to start: the claude binary is not on PATH.");
  const notReady = checkWebuiDir(cfg.webuiDir);
  if (notReady.length > 0) throw new Error(`Refusing to start: WebUI checkout not ready (npm ci in server/ and client/): ${notReady.join(", ")}`);

  const deadline = Date.now() + cfg.maxMinutes * 60_000; // one overall deadline, from the start of the run
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const runDir = path.join(cfg.workdir, `run-${stamp}`);
  const tempHome = path.join(runDir, "home");
  const projectPath = path.join(runDir, "project");
  fs.mkdirSync(tempHome, { recursive: true });
  fs.mkdirSync(projectPath, { recursive: true });

  const checklist = new Checklist(parseChecklist(fs.readFileSync(expectedFile, "utf8")));
  const template = fs.readFileSync(path.join(projectRoot, "report-template.md"), "utf8");
  const report = new Report(
    path.join(cfg.workdir, "e2e-report"),
    {
      authSource,
      config: {
        permission_mode: cfg.permissionMode,
        max_minutes: String(cfg.maxMinutes),
        webui_dir_source: cfg.sources.SHIPWRIGHT_E2E_WEBUI_DIR,
        permission_mode_source: cfg.sources.SHIPWRIGHT_E2E_PERMISSION_MODE,
        max_minutes_source: cfg.sources.SHIPWRIGHT_E2E_MAX_MINUTES,
        workdir_source: cfg.sources.SHIPWRIGHT_E2E_WORKDIR,
        env_file: cfg.envFileFound ? "found" : "not found",
        project: projectPath,
      },
    },
    checklist,
    template,
  );

  let status = "aborted";
  let login: { remove(): void } | null = null;
  let stop: (() => Promise<void>) | null = null;
  let killServer: (() => void) | null = null;
  // One idempotent shutdown path: kill the server, then delete the copied login, on every exit path.
  const shutdown = new Shutdown();
  // A signal skips the finally below, so the report is also written from the shutdown path.
  let reportWritten = false;
  shutdown.add(() => { if (!reportWritten) report.write("interrupted"); });
  shutdown.add(() => killServer?.());
  shutdown.add(() => login?.remove());
  // The API-key approval record (last 20 characters of the key) lives in .claude.json: remove it too.
  shutdown.add(() => fs.rmSync(path.join(tempHome, ".claude.json"), { force: true }));
  shutdown.install();
  try {
    const scrubbed = scrubStaleLogins(cfg.workdir, (cfg.maxMinutes + 60) * 60_000);
    if (scrubbed > 0) report.escalation(`Removed ${scrubbed} stale login copy/copies left by an earlier run that was killed.`);
    // 2. Provision the temp HOME and start the second WebUI instance.
    if (authSource === "copied login") login = copyLogin(realHome, tempHome);
    const key = process.env.ANTHROPIC_API_KEY ?? "";
    provisionHome({
      repoRoot, tempHome, projectPath, permissionMode: cfg.permissionMode,
      apiKeyTail: authSource === "env key" ? key.slice(-20) : undefined,
    });
    gitInit(projectPath);
    const stack = await startStack({
      webuiDir: cfg.webuiDir, repoRoot, home: tempHome,
      extraEnv: { SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL: "1" },
    });
    stop = stack.stop;
    killServer = stack.killSync;
    const base = stack.baseUrl;
    await page.goto(base);
    await report.step("WebUI built and started (second instance, temp HOME)", page,
      `Base URL ${base}. Build took ${(stack.buildMs / 60_000).toFixed(1)} min (each build step is limited to ${BUILD_STEP_TIMEOUT_MS / 60_000} min; the overall budget of ${cfg.maxMinutes} min started at the beginning of the run).`);

    // 3. Create the project through the expert wizard, place the package, start "New pipeline".
    await ui.createProject(page, base, "social-engagement-e2e", projectPath, PROFILE);
    const projectId = await ui.findProjectId(page.request, base, projectPath);
    fs.cpSync(fixtureDir, path.join(projectPath, "brief"), { recursive: true });
    await ui.openBoard(page, base, projectId);
    await report.step("Project created, Brief package placed in brief/", page);
    await ui.startPipeline(page, "Build the social engagement desk", "Build the app from the approved Brief package: /shipwright-run --brief brief/");
    await report.step("New pipeline, package handed over", page);
    await ui.launchPipeline(page);

    // 4. Follow the phases, answer gates, until complete, failed, idle or out of budget.
    const taskId = await waitForTask(page, base, projectId);
    if (taskId) await page.goto(`${base}/tasks/${taskId}`);
    await report.step("Task page after launch", page);
    status = await follow(page, base, projectPath, deadline, cfg.maxMinutes, report);

    // 5. Hard file checks, then the built app (only when the run completed).
    checkProjectFiles(projectPath, fixtureDir, checklist);
    if (status === "complete") {
      await ui.openBoard(page, base, projectId);
      const app = await ui.openPreview(page);
      const origin = new URL(app.url()).origin;
      const health = await fetch(`${origin}/api/health`, { signal: AbortSignal.timeout(30_000) }).then((r) => r.status, () => 0);
      checklist.record("H05", health === 200 ? "pass" : "fail", `GET /api/health -> ${health}`);
      await runChatScript(async (message) => {
        const res = await fetch(`${origin}/api/chat`, {
          method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ message }), signal: AbortSignal.timeout(60_000),
        });
        return (await res.json()) as { reply: string; pane: unknown };
      }, JSON.parse(fs.readFileSync(path.join(fixtureDir, "chat-map.json"), "utf8")), checklist);
      await tourApp(app, await page.context().newPage(), fixtureDir, report);
    }
    const open = checklist.hardOpen();
    status = status === "complete" && open.length === 0 ? "complete, all hard items hold" : `${status}; hard items open: ${open.map((i) => i.id).join(", ") || "none"}`;
    await report.step("Finished", page, status);
  } catch (error) {
    status = `failed: ${(error as Error).message.split("\n")[0]}`;
    report.escalation(status);
    await report.step("Run stopped by an error", page.isClosed() ? null : page, status);
    throw error;
  } finally {
    // The report is written on every exit path, and the copied login is deleted on every exit path.
    try {
      report.write(status);
      reportWritten = true;
    } finally {
      shutdown.run();
      shutdown.uninstall();
    }
    await stop?.();
    console.log(`E2E report: ${path.join(report.dir, "report.md")}`);
  }
  expect(checklist.hardOpen().map((i) => i.id)).toEqual([]);
});

async function waitForTask(page: Page, base: string, projectId: string): Promise<string | null> {
  for (let i = 0; i < 40; i += 1) {
    const id = await ui.findTaskId(page.request, base, projectId);
    if (id) return id;
    await page.waitForTimeout(3000);
  }
  return null;
}

async function follow(page: Page, base: string, projectPath: string, deadline: number, maxMinutes: number, report: Report): Promise<string> {
  const idle = new IdleWatch(IDLE_MINUTES * 60_000);
  let lastPhases = "";
  while (Date.now() < deadline) {
    const state = readRunState(projectPath);
    const phases = phaseSignature(state);
    if (phases !== lastPhases) {
      lastPhases = phases;
      await report.step(`Phase state: ${phases}`, page);
    }
    if (state.status === "complete" || state.status === "failed") return state.status;
    for (const done of await ui.answerGates(page)) {
      report.gate(done);
      await report.step(`Gate answered: ${done}`, page);
    }
    const terminal = await page.locator(".xterm-rows").first().innerText({ timeout: 2000 }).catch(() => "");
    if (!idle.observe(`${phases}|${fileActivity(projectPath)}|${terminal.slice(-2000)}`)) {
      const inbox = await page.context().newPage();
      const prompt = await ui.pendingPrompt(inbox, base);
      report.escalation(`No progress for ${IDLE_MINUTES} minutes; pending prompt the spec cannot answer: ${prompt ? "yes (see inbox screenshot)" : "none found in the inbox"}.`);
      await report.step("Idle abort: inbox", inbox);
      await report.step("Idle abort", page, "No new phase, task state, file change or terminal output.");
      return "idle-abort";
    }
    await page.waitForTimeout(POLL_MS);
  }
  report.escalation(`Wall-clock budget of ${maxMinutes} minutes used up.`);
  await report.step("Budget used up", page);
  return "out-of-budget";
}
