// The checks of the `social-engagement-baseline` fixture. `runStatic` needs only the project's files; `runBaselineSuite` also
// starts the built companion several times (fresh data folder, local fake servers for Syften and Apify, dummy tokens, a fixed
// clock), plays the agent over HTTP from seed/agent/run-synthetic.json, and drives the board in a browser. No real network, no real key.
import fs from "node:fs";
import path from "node:path";
import type { Browser, Page } from "@playwright/test";
import type { Checklist } from "../checklist.js";
import type { Report } from "../report.js";
import * as late from "./checks-board-late.js";
import * as board from "./checks-board.js";
import * as contract from "./checks-contract.js";
import * as fetchChecks from "./checks-fetch.js";
import * as layout from "./checks-layout.js";
import * as life from "./checks-lifecycle.js";
import * as runs from "./checks-runs.js";
import { secrecy } from "./checks-secrecy.js";
import { checkAdapterOnly, checkSkillText, checkStoreOnly } from "./checks-static.js";
import { resolvePython } from "./companion.js";
import { cleanDir, dummyTokens, loadSynthetic, scenario, tmpRootFor, TODAY, type Ctx, type Scenario } from "./ctx.js";
import { startFakeServices } from "./fake-services.js";
import { post } from "./http.js";
import { Probe } from "./probe.js";
import { standInFeedback, tourBaseline } from "./tour-baseline.js";

/** Records one item from a Probe; an exception inside the check is a failed item with the reason, never a crash of the run. */
export async function recordProbe(checklist: Checklist, id: string, body: (p: Probe) => Promise<void> | void): Promise<void> {
  const p = new Probe();
  try {
    await body(p);
  } catch (error) {
    p.expect("the check ran to its end", false, (error as Error).message.split("\n")[0]);
  }
  const v = p.verdict();
  checklist.record(id, v.pass ? "pass" : "fail", v.evidence);
}

/** B30, B31, B33: file checks. They run whether or not the pipeline finished. */
export async function runStatic(project: string, checklist: Checklist): Promise<void> {
  await recordProbe(checklist, "B30", (p) => checkStoreOnly(project, p));
  await recordProbe(checklist, "B31", (p) => checkAdapterOnly(project, p));
  await recordProbe(checklist, "B33", (p) => checkSkillText(project, p));
}

export interface SuiteInput {
  project: string;
  fixtureDir: string;
  checklist: Checklist;
  report: Report;
  page: Page;
}

const mockupState = async (api: Scenario["api"], ctx: Ctx) => {
  await post(api, "/api/runs", { items: ctx.synthetic });
  await post(api, "/api/status", { key: runs.K_POSTED, status: "posted", posted_url: "https://www.reddit.com/r/ExperiencedDevs/comments/1on3f8q/comment/mq2bZZ1/" });
  await post(api, "/api/status", { key: runs.K_SKIPPED, status: "skipped" });
};

export async function runBaselineSuite(input: SuiteInput): Promise<void> {
  const { project, fixtureDir, checklist } = input;
  const fake = await startFakeServices(path.join(fixtureDir, "seed", "recorded"));
  const ctx: Ctx = { project, fixtureDir, python: resolvePython(), tmpRoot: tmpRootFor(), fake, tokens: dummyTokens(), leaks: [], synthetic: loadSynthetic(fixtureDir) };
  const rec = (id: string, body: (p: Probe) => Promise<void>) => recordProbe(checklist, id, body);
  const onScenario = async (ids: string[], name: string, opts: Parameters<typeof scenario>[2], steps: [string, (s: Scenario, p: Probe) => Promise<void>][]) => {
    try {
      await scenario(ctx, name, opts, async (s) => { for (const [id, fn] of steps) await rec(id, (p) => fn(s, p)); });
    } catch (error) {
      for (const id of ids.filter((i) => checklist.items.find((x) => x.id === i)?.verdict === "not evaluated")) checklist.record(id, "fail", `the companion could not be run: ${(error as Error).message.split("\n")[0]}`);
    }
  };
  try {
    const [b01, b02, b03] = [new Probe(), new Probe(), new Probe()];
    try { await life.lifecycleStory(ctx, { b01, b02, b03 }); } catch (error) { for (const x of [b01, b02, b03]) x.expect("the lifecycle story ran to its end", false, (error as Error).message.split("\n")[0]); }
    for (const [id, p] of [["B01", b01], ["B02", b02], ["B03", b03]] as const) { const v = p.verdict(); checklist.record(id, v.pass ? "pass" : "fail", v.evidence); }
    await rec("B04", (p) => life.portInUse(ctx, p));
    await rec("B05", (p) => life.stalePidfile(ctx, p));
    await rec("B27", (p) => life.dataLocation(ctx, p));

    const secured = { fakeUrls: true, today: true, tokens: "both" as const };
    await onScenario(["B06", "B07", "B08", "B09", "B25"], "contract", secured, [
      ["B06", contract.headers], ["B07", contract.localAccess], ["B08", contract.badRequests], ["B09", contract.readRoutes], ["B25", contract.openRefusals],
    ]);
    await onScenario(["B24"], "config", {}, [["B24", contract.config]]);

    const fetchOpts = fetchChecks.fetchScenarioOpts(ctx);
    await onScenario(["B10", "B11", "B12"], "fetch", fetchOpts, [
      ["B10", (s, p) => fetchChecks.fetchSyften(ctx, s, p)], ["B11", (s, p) => fetchChecks.fetchLinkedin(ctx, s, p)], ["B12", (s, p) => fetchChecks.fetchThread(ctx, s, p)],
    ]);
    await rec("B13", async (p) => {
      await scenario(ctx, "failing", fetchOpts, (s) => fetchChecks.serviceFailures(ctx, s, p));
      await scenario(ctx, "notoken", { fakeUrls: true, today: true }, (s) => fetchChecks.missingTokens(ctx, s, p));
    });
    await onScenario(["B15"], "dedupe", fetchOpts, [["B15", (s, p) => fetchChecks.dedupe(ctx, s, p)]]);

    await onScenario(["B16", "B17", "B18", "B19", "B20", "B21", "B23"], "runs", { today: true }, [
      ["B16", (s, p) => runs.runStorage(ctx, s, p)], ["B17", (s, p) => runs.lint(ctx, s, p)], ["B18", (s, p) => runs.statusRules(ctx, s, p)], ["B19", (s, p) => runs.expiry(ctx, s, p)],
      ["B20", (s, p) => runs.feedbackSaved(ctx, s, p)], ["B21", (s, p) => runs.feedbackQueue(ctx, s, p)], ["B23", (s, p) => runs.lessons(ctx, s, p)],
    ]);
    try {
      await scenario(ctx, "layout", { today: true }, async (s) => {
        const [events, files] = [new Probe(), new Probe()];
        try { await layout.eventsAndLayout(ctx, s, events, files); } catch (error) { for (const x of [events, files]) x.expect("the story ran to its end", false, (error as Error).message.split("\n")[0]); }
        for (const [id, p] of [["B22", events], ["B26", files]] as const) { const v = p.verdict(); checklist.record(id, v.pass ? "pass" : "fail", v.evidence); }
      });
    } catch (error) {
      for (const id of ["B22", "B26"]) checklist.record(id, "fail", `the companion could not be run: ${(error as Error).message.split("\n")[0]}`);
    }
    await rec("B28", (p) => layout.corruptFile(ctx, p));

    await runBoard(ctx, input, rec);
    await rec("B14", (p) => secrecy(ctx, p));
  } finally {
    await fake.stop();
    cleanDir(ctx.tmpRoot);
  }
}

async function runBoard(ctx: Ctx, input: SuiteInput, rec: (id: string, body: (p: Probe) => Promise<void>) => Promise<void>): Promise<void> {
  const ids = ["B35", "B36", "B37", "B38", "B39", "B40", "B41", "B42", "B43", "B44", "B45", "B46"];
  const browser: Browser | null = input.page.context().browser();
  if (!browser) return void ids.forEach((id) => input.checklist.record(id, "fail", "no browser to drive"));
  try {
    await scenario(ctx, "board", { today: true }, async (s) => {
      await mockupState(s.api, ctx);
      const note = await standInFeedback(s, input.fixtureDir);
      const newPage = async (width = 1280): Promise<Page> => {
        const c = await browser.newContext({ viewport: { width, height: 900 }, permissions: ["clipboard-read", "clipboard-write"] });
        // the browser may only talk to the app itself: nothing in a model-written page can reach the real internet
        await c.route("**/*", (r) => (/^https?:\/\/(127\.0\.0\.1|localhost)[:/]/.test(r.request().url()) || !/^https?:/.test(r.request().url()) ? r.fallback() : r.abort()));
        return c.newPage();
      };
      const page = await newPage();
      const b: board.BoardEnv = { page, newPage, origin: s.c.origin, api: s.api, items: await board.refresh(s.api), guidelines: fs.readFileSync(path.join(input.fixtureDir, "visual-guidelines.md"), "utf8"), fixtureDir: input.fixtureDir };
      try {
        const steps: [string, (p: Probe) => Promise<void>][] = [
          ["B35", (p) => board.masterDetail(b, p)], ["B36", (p) => board.keyboardAndHash(b, p)], ["B37", (p) => board.threadView(b, p)],
          ["B38", (p) => board.commentCount(b, p)], ["B39", (p) => board.copyAndOpen(b, p)], ["B40", (p) => board.feedbackOnBoard(b, p)],
          ["B41", (p) => board.statusOnBoard(b, p)], ["B42", (p) => board.phone(b, p)], ["B43", (p) => board.tokens(b, p)],
        ];
        for (const [id, fn] of steps) await rec(id, fn);
        b.items = await board.refresh(s.api);
        await input.report.step("Baseline board: state prepared by the stand-in agent", null, `Synthetic run stored, ${runs.K_POSTED} posted, ${runs.K_SKIPPED} skipped, clock ${TODAY}. ${note}`.trim());
        try {
          await tourBaseline(b, await page.context().newPage(), input.fixtureDir, input.report);
        } catch (error) {
          await input.report.step("Baseline screen tour stopped", null, `The tour could not finish: ${(error as Error).message.split(String.fromCharCode(10))[0]}`);
        }
        await rec("B44", (p) => board.versionBanner(b, p));
        await rec("B45", (p) => late.longXDraft(b, p, ctx));
        await rec("B46", (p) => late.reviewLine(b, p, ctx));
      } finally {
        await page.context().close();
      }
    });
  } catch (error) {
    for (const id of ids.filter((i) => input.checklist.items.find((x) => x.id === i)?.verdict === "not evaluated")) input.checklist.record(id, "fail", `the board could not be checked: ${(error as Error).message.split("\n")[0]}`);
  }
}
