// Operator-started real end-to-end run: Brief package -> skill-backed board app, driven through the WebUI like a person.
// NOT a CI gate: it uses a real agent (tokens, wall-clock). See README.md for the operator procedure.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { AuthError, authEnv, copyLogin, pickAuthSource, realHomeDir, scrubStaleLogins, type AuthSource } from "../src/auth.js";
import { httpCall } from "../src/board-api.js";
import { Checklist, parseChecklist } from "../src/checklist.js";
import * as ui from "../src/driver.js";
import { ConfigError, loadConfig } from "../src/env.js";
import { activeFixture, PROFILE, type FixtureName, expectedFile as expectedPath, fixtureDir as fixturePath } from "../src/fixture.js";
import { follow, waitForTask } from "../src/follow.js";
import { appendRecord, loadRecords, wholeRun } from "../src/gate-log.js";
import { checkGates } from "../src/gates.js";
import { checkProjectFiles, listHtml, readScreenshotCheck, recordScreenshotCheck } from "../src/progress.js";
import { checkPluginShape, checkScreensComposed, checkTestsRan } from "../src/project-checks.js";
import { checkSkillTriggers } from "../src/skill-trigger.js";
import { variantFor } from "../src/variant.js";
import { acquireLock, addLockPid, markFinished, markPipelineStarted, planResume, releaseLock, writeManifest, type ResumePlan, type RunIdentity } from "../src/resume.js";
import { provisionHome } from "../src/provision.js";
import { Report } from "../src/report.js";
import { packageDigest, pluginFingerprint } from "../src/run-identity.js";
import { Shutdown } from "../src/shutdown.js";
import { BUILD_STEP_TIMEOUT_MS, startStack, checkWebuiDir } from "../src/stack.js";
import { tourBoard } from "../src/tour.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(here, "..");
const repoRoot = path.resolve(projectRoot, "..", "..");
const TEARDOWN_MARGIN_MS = 15 * 60_000; // room after the run budget for the report and the shutdown
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

function onPath(names: string[]): boolean {
  const dirs = (process.env.PATH ?? "").split(path.delimiter);
  return dirs.some((d) => names.some((n) => d && fs.existsSync(path.join(d, n))));
}

function gitInit(dir: string): void {
  const git = ["-c", "user.name=e2e", "-c", "user.email=e2e@example.com"];
  execFileSync("git", ["-C", dir, "init", "-q"], { stdio: "ignore" });
  execFileSync("git", ["-C", dir, "config", "user.name", "e2e"], { stdio: "ignore" });
  execFileSync("git", ["-C", dir, "config", "user.email", "e2e@example.invalid"], { stdio: "ignore" });
  execFileSync("git", ["-C", dir, ...git, "commit", "-q", "--allow-empty", "-m", "baseline"], { stdio: "ignore" });
}

// @covers FR-01.06
test("brief package to a working skill-backed board app through the WebUI", async ({ page }) => {
  // 1. Refuse to start without the operator inputs and an authentication source (no defaults).
  let cfg;
  let authSource: AuthSource;
  let FIXTURE_NAME: FixtureName; // SHIPWRIGHT_E2E_FIXTURE from the process env or the env file; the default is the tabs fixture
  const realHome = realHomeDir();
  try {
    cfg = loadConfig(repoRoot);
    authSource = pickAuthSource(process.env, realHome);
    FIXTURE_NAME = activeFixture({ SHIPWRIGHT_E2E_FIXTURE: cfg.fixture });
  } catch (error) {
    if (error instanceof ConfigError || error instanceof AuthError) throw new Error(error.message);
    throw error;
  }
  const variant = variantFor(FIXTURE_NAME);
  const fixtureDir = fixturePath(repoRoot, FIXTURE_NAME);
  const expectedFile = expectedPath(repoRoot, FIXTURE_NAME);
  // MAX_MINUTES is a real limit: the test timeout follows it, with room left for the report and the shutdown.
  test.setTimeout(cfg.maxMinutes * 60_000 + TEARDOWN_MARGIN_MS);
  if (!onPath(["claude", "claude.exe", "claude.cmd"])) throw new Error("Refusing to start: the claude binary is not on PATH.");
  const notReady = checkWebuiDir(cfg.webuiDir);
  if (notReady.length > 0) throw new Error(`Refusing to start: WebUI checkout not ready (npm ci in server/ and client/): ${notReady.join(", ")}`);

  const deadline = Date.now() + cfg.maxMinutes * 60_000; // one overall deadline, from the start of the run
  // The run folder gets an unpredictable name (mkdtemp, prefix run- is what the stale-login scrub scans) and owner-only rights.
  fs.mkdirSync(cfg.workdir, { recursive: true, mode: 0o700 });
  // Identity of this run: a resumed run is only accepted from a folder that recorded the same one (src/resume.ts).
  const identity: RunIdentity = {
    fixture: FIXTURE_NAME, profile: PROFILE, commit: pluginFingerprint(repoRoot),
    packageSha256: packageDigest(repoRoot, fixtureDir), // computed from the files, not the hash brief.json claims
  };
  let resume: ResumePlan | null = null;
  if (cfg.resumeRun) {
    try {
      resume = planResume(cfg.resumeRun, cfg.workdir, identity);
    } catch (error) {
      throw new Error((error as Error).message);
    }
  }
  const runDir = resume ? resume.runDir : fs.mkdtempSync(path.join(cfg.workdir, "run-"));
  const tempHome = path.join(runDir, "home");
  const projectPath = path.join(runDir, "project");
  fs.mkdirSync(tempHome, { recursive: true, mode: 0o700 });
  fs.mkdirSync(projectPath, { recursive: true, mode: 0o700 });
  if (!resume) writeManifest(runDir, identity);
  acquireLock(runDir);

  const checklist = new Checklist(parseChecklist(fs.readFileSync(expectedFile, "utf8")));
  const earlierRun = loadRecords(runDir);
  const template = fs.readFileSync(path.join(projectRoot, "report-template.md"), "utf8");
  const report = new Report(
    path.join(cfg.workdir, "e2e-report"),
    {
      authSource,
      commit: identity.commit,
      config: {
        permission_mode: cfg.permissionMode,
        max_minutes: String(cfg.maxMinutes),
        webui_dir_source: cfg.sources.SHIPWRIGHT_E2E_WEBUI_DIR,
        permission_mode_source: cfg.sources.SHIPWRIGHT_E2E_PERMISSION_MODE,
        max_minutes_source: cfg.sources.SHIPWRIGHT_E2E_MAX_MINUTES,
        workdir_source: cfg.sources.SHIPWRIGHT_E2E_WORKDIR,
        env_file: cfg.envFileFound ? "found" : "not found",
        project: projectPath,
        resume_run_source: cfg.sources.SHIPWRIGHT_E2E_RESUME_RUN,
        fixture: FIXTURE_NAME,
        fixture_source: cfg.sources.SHIPWRIGHT_E2E_FIXTURE === "unset" ? "unset (default)" : cfg.sources.SHIPWRIGHT_E2E_FIXTURE,
      },
    },
    checklist,
    template,
  );
  report.sink = (kind, text) => appendRecord(runDir, kind, text);
  if (earlierRun.gates.length + earlierRun.escalations.length > 0) {
    await report.step("Resume: gates and escalations of the earlier part", null, `${earlierRun.gates.length} gate(s), ${earlierRun.escalations.length} escalation(s) are judged with this part (S08).`);
  }

  let housekeeping = ""; // not an escalation: S08 judges the run, not the scrub of an earlier run's leftovers
  let initialStatus = "";
  let status = "aborted";
  let login: { remove(): void } | null = null;
  let stop: (() => Promise<void>) | null = null;
  let killServer: (() => void) | null = null;
  // One idempotent shutdown path: kill the server, then delete the copied login, on every exit path.
  const shutdown = new Shutdown();
  // A signal skips the finally below, so the report is also written from the shutdown path.
  let reportWritten = false;
  shutdown.add(() => { if (!reportWritten) report.write("interrupted"); });
  // Order matters: the whole server process tree goes first, only then the secrets are deleted.
  const wipe = () => {
    login?.remove();
    fs.rmSync(path.join(tempHome, ".claude", ".credentials.json"), { force: true });
    // The API-key approval record (last 20 characters of the key) lives in .claude.json.
    fs.rmSync(path.join(tempHome, ".claude.json"), { force: true });
  };
  shutdown.add(() => releaseLock(runDir));
  shutdown.add(() => killServer?.());
  shutdown.add(wipe);
  shutdown.install();
  try {
    const scrubbed = scrubStaleLogins(cfg.workdir, (cfg.maxMinutes + 60) * 60_000);
    if (scrubbed > 0) housekeeping = `Removed ${scrubbed} stale login copy/copies left by an earlier run that was killed.`;
    // 2. Provision the temp HOME and start the second WebUI instance.
    if (authSource === "copied login") login = copyLogin(realHome, tempHome);
    const key = process.env.ANTHROPIC_API_KEY ?? "";
    provisionHome({
      repoRoot, tempHome, projectPath, permissionMode: cfg.permissionMode,
      apiKeyTail: authSource === "env key" ? key.slice(-20) : undefined,
    });
    if (!fs.existsSync(path.join(projectPath, ".git"))) gitInit(projectPath);
    if (resume) report.setResume(resume.note);
    const stack = await startStack({
      webuiDir: cfg.webuiDir, repoRoot, home: tempHome,
      extraEnv: { ...authEnv(authSource, process.env), SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL: "1" },
      deadline,
    });
    stop = stack.stop;
    killServer = stack.killSync;
    addLockPid(runDir, stack.pid);
    const base = stack.baseUrl;
    await page.goto(base);
    await report.step("WebUI built and started (second instance, temp HOME)", page,
      `Base URL ${base}. Build took ${(stack.buildMs / 60_000).toFixed(1)} min (each build step is limited to ${BUILD_STEP_TIMEOUT_MS / 60_000} min; the overall budget of ${cfg.maxMinutes} min started at the beginning of the run).`);

    // 3. Create the project through the expert wizard (a resumed run reuses it when the WebUI still lists it), place the
    //    package, start "New pipeline". A resumed run skips what the earlier run already did (src/resume.ts).
    const known = resume ? await ui.findProjectId(page.request, base, projectPath).catch(() => null) : null;
    if (!known) await ui.createProject(page, base, `${FIXTURE_NAME}-e2e`, projectPath, PROFILE);
    const projectId = known ?? (await ui.findProjectId(page.request, base, projectPath));
    if (!resume?.skipPackageCopy) fs.cpSync(fixtureDir, path.join(projectPath, "brief"), { recursive: true });
    await ui.openBoard(page, base, projectId);
    await report.step("Project ready, Brief package in brief/", page, [resume?.note, housekeeping].filter(Boolean).join(" "));
    if (resume?.skipStartPipeline) {
      await report.step("Resume: the pipeline was already started, New pipeline not clicked again", null);
    } else {
      await ui.startPipeline(page, "Build the social engagement board", "Build the app from the approved Brief package: /shipwright-run --brief brief/");
      markPipelineStarted(runDir); // the task exists from here on: a resume must not click "New pipeline" again
      await report.step("New pipeline, package handed over", page);
      await ui.launchPipeline(page);
    }

    // 4. Follow the phases, answer gates, until complete, failed, idle or out of budget.
    const taskId = await waitForTask(page, base, projectId);
    if (taskId) await page.goto(`${base}/tasks/${taskId}`);
    // A resumed task may already be launched (or its pipeline over): no launch button is then not an error.
    const hasLaunch = await page.getByTestId("cta-launch-in-terminal").waitFor({ state: "visible", timeout: 10_000 }).then(() => true, () => false);
    if (resume?.skipStartPipeline && !hasLaunch) {
      await report.step("Resume: no launch button on the task page, the task was already launched", page);
    } else {
      await ui.startTaskSession(page, async (attempt) => {
        const state = await ui.taskStateText(page.request, base, taskId);
        await report.step(`Launch button missing (attempt ${attempt} of 3)`, page, `Task ${taskId ?? "?"}: ${state}.${attempt < 3 ? " Reloading the task page." : " Giving up."}`);
      });
    }
    await report.step("Task page after launch", page);
    status = await follow(page, base, projectId, projectPath, deadline, cfg.maxMinutes, report);
    initialStatus = status;

    // 5. Hard file checks, then the built app (only when the run completed).
    checkProjectFiles(projectPath, fixtureDir, checklist);
    const shot = readScreenshotCheck(projectPath);
    report.setScreenshotCheck(shot.summary);
    recordScreenshotCheck(checklist, shot);
    const mockups = listHtml(path.join(fixtureDir, "mockups"));
    checkPluginShape(projectPath, checklist);
    checkScreensComposed(projectPath, mockups, checklist);
    variant.selfContained(projectPath, checklist);
    checkTestsRan(projectPath, checklist);
    if (checklist.items.some((i) => i.id === "S09")) checkSkillTriggers(projectPath, checklist, { ...process.env, HOME: tempHome, USERPROFILE: tempHome });
    if (status === "complete") {
      await ui.openBoard(page, base, projectId);
      // The Test phase used the throw-away data folder of this fixed port; move it aside so H06-H10 start fresh.
      const used = path.join(projectPath, ".dev-data");
      if (fs.existsSync(used)) {
        try {
          fs.renameSync(used, `${used}.before-e2e-${Date.now()}`);
          await report.step("Test-phase data folder moved aside before the preview", null, ".dev-data was renamed so the API checks start from a fresh folder.");
        } catch (error) {
          report.escalation(`The Test-phase data folder could not be moved aside (${(error as Error).message.split("\n")[0]}); H06 will show the folder was not fresh.`);
        }
      }
      const app = await ui.openPreview(page);
      const url = new URL(app.url());
      if (!LOOPBACK.has(url.hostname)) throw new Error(`The preview opened ${url.origin}, which is not loopback; the API checks only talk to 127.0.0.1.`);
      const origin = url.origin;
      await report.step("App preview opened", app, `Preview origin: ${origin}`);
      const call = httpCall(origin);
      const health = await call("GET", "/api/health").then((r) => r.status, () => 0);
      checklist.record("H05", health === 200 ? "pass" : "fail", `GET /api/health -> ${health}`);
      const { state } = await variant.api(call, checklist);
      await app.goto(origin, { waitUntil: "domcontentloaded" });
      await variant.board(app, fs.readFileSync(path.join(fixtureDir, "visual-guidelines.md"), "utf8"), state, checklist);
      await tourBoard(app, await page.context().newPage(), origin, fixtureDir, state, report);
    }
    // Earlier part as loaded at start + this run's memory; gates.jsonl is not re-read (the agent can reach it).
    const judged = wholeRun(earlierRun, report.gateList(), report.escalationList());
    checkGates(judged.gates, judged.escalations, checklist);
    const open = checklist.hardOpen();
    status = status === "complete" && open.length === 0 ? "complete, all hard items hold" : `${status}; hard items open: ${open.map((i) => i.id).join(", ") || "none"}`;
    await report.step("Finished", page, status);
    // Only a pipeline that really ended is finished; an idle abort or a spent budget stays resumable.
    if (initialStatus === "complete" || initialStatus === "failed") markFinished(runDir);
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
    wipe(); // second pass, once the server has really stopped
    console.log(`E2E report: ${path.join(report.dir, "report.md")}`);
  }
  expect(checklist.hardOpen().map((i) => i.id)).toEqual([]);
});
