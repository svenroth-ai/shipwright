// No model: gates (S08), resume, the tour targets and the review-round hardening of the project checks.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { httpCall } from "../../src/board-api.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { FIXTURE_NAME } from "../../src/fixture.js";
import { checkGates, classifyGates } from "../../src/gates.js";
import { checkSelfContained, findExternalUse, findSeed } from "../../src/project-checks.js";
import { acquireLock, addLockPid, LOCK_NAME, markFinished, markPipelineStarted, planResume, releaseLock, ResumeError, writeManifest, type RunIdentity } from "../../src/resume.js";
import { packageDigest, pluginFingerprint } from "../../src/run-identity.js";
import { openTarget } from "../../src/tour.js";
import { startStub } from "./stub-companion.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const expected = fs.readFileSync(path.join(repo, "integration-tests", "fixtures", `${FIXTURE_NAME}-expected-result.md`), "utf8");
const list = () => new Checklist(parseChecklist(expected));
const verdict = (l: Checklist, id: string) => l.items.find((i) => i.id === id)!.verdict;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-board-"));
const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};

// @covers FR-01.01
test("gates (S08) are classified by meaning, not wording; an exemption or an unknown gate fails", () => {
  const ok = ["design review approved", "terminal question answered with its first option \"Approve screens\" (Do you approve the screens?)",
    "terminal question answered with its first option \"Approve mockups\" (Approve the mockups?)", "launched the next pipeline phase"];
  expect(classifyGates(ok).unexpected).toEqual([]);
  const l = list();
  checkGates(ok, [], l);
  expect(verdict(l, "S08")).toBe("pass");
  const odd = ["terminal question answered with its first option \"Commit earlier output first\" (Approve the design, or how do you want to proceed?)"];
  expect(classifyGates(odd).unexpected.length).toBe(1); // the question mentions approve; the option chosen does not
  expect(classifyGates(["terminal question answered with its first option \"Submit answers\" (Ready to submit?)"]).unexpected).toEqual([]);
  expect(classifyGates(["terminal question answered with its first option \"Continue\" (How to proceed?)"]).unexpected.length).toBe(1);
  expect(classifyGates(["Complete with exemption"]).unexpected.length).toBe(1);
  for (const o of ["Not approved", "Reject the screens", "Skip the design review"]) expect(classifyGates([`terminal question answered with its first option "${o}" (Proceed?)`]).unexpected.length, o).toBe(1);
  const l2 = list();
  checkGates(ok, ["No progress for 20 minutes"], l2);
  expect(verdict(l2, "S08")).toBe("fail");
});

// @covers FR-01.06
test("resume: accepted only for the same run identity, a direct run-* child, not complete; refused otherwise", () => {
  const work = tmp();
  const id: RunIdentity = { fixture: FIXTURE_NAME, profile: "skill-companion-app", commit: "abc123", packageSha256: "f".repeat(64) };
  try {
    const run = path.join(work, "run-Ab12Cd");
    fs.mkdirSync(path.join(run, "home"), { recursive: true });
    fs.mkdirSync(path.join(run, "project", "brief"), { recursive: true });
    writeManifest(run, id);
    write(run, "project/brief/brief.json", JSON.stringify({ package_sha256: id.packageSha256 }));
    write(run, "project/shipwright_run_config.json", JSON.stringify({ status: "in_progress" }));
    markPipelineStarted(run);
    const plan = planResume(run, work, id);
    expect(plan.skipPackageCopy).toBe(true);
    expect(plan.skipStartPipeline).toBe(true);
    expect(plan.note).toContain("Resumed from run-Ab12Cd");

    expect(() => planResume(run, work, { ...id, commit: "other" })).toThrow(/commit: earlier abc123, now other/);
    expect(() => planResume(run, work, { ...id, packageSha256: "0".repeat(64) })).toThrow(ResumeError);
    expect(() => planResume(path.join(work, "..", "elsewhere", "run-Ab12Cd"), work, id)).toThrow(/direct child/);
    expect(() => planResume(path.join(work, "notarun"), work, id)).toThrow(/run-<id>/);
    expect(() => planResume(path.join(work, "run-Missing"), work, id)).toThrow(/does not exist/);

    write(run, "project/shipwright_run_config.json", JSON.stringify({ status: "complete" }));
    expect(planResume(run, work, id).skipStartPipeline).toBe(true); // pipeline done, checks not: still resumable
    markFinished(run);
    expect(() => planResume(run, work, id)).toThrow(/already finished/);
    writeManifest(run, id); // a fresh manifest: not finished (and not started)
    write(run, "project/shipwright_run_config.json", JSON.stringify({ status: "failed" }));
    write(run, "project/brief/brief.json", JSON.stringify({ package_sha256: "0".repeat(64) }));
    expect(() => planResume(run, work, id)).toThrow(/not the package/);

    const noManifest = path.join(work, "run-Zz9");
    fs.mkdirSync(noManifest);
    expect(() => planResume(noManifest, work, id)).toThrow(/run-manifest/);
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("tour: each fixture screen opens the thread or view whose state the API checks left behind", () => {
  const state = { posted: 1, drafted: 3, fresh: 4, titles: {}, perPlatform: {} };
  expect(openTarget("board", state)).toEqual({});
  expect(openTarget("thread-detail", state)).toEqual({ thread: 4 });
  expect(openTarget("reply-draft", state)).toEqual({ thread: 3 });
  expect(openTarget("thread-posted", state)).toEqual({ thread: 1 });
  expect(openTarget("keywords", state).text?.source).toMatch(/keywords/i);
  expect(openTarget("thread-posted", { ...state, posted: null })).toEqual({});
});

// @covers FR-01.06
test("review round 3: refusing options, loopback IPv6 and protocol-relative URLs, linked run folders, redirects", async () => {
  expect(classifyGates(['terminal question answered with its first option "Disapprove the design" (Approve?)']).unexpected.length).toBe(1);
  expect(classifyGates(['terminal question answered with its first option "I have feedback" (Approve the mockups?)']).unexpected.length).toBe(1);
  const dir = tmp();
  try {
    write(dir, "backend/a.py", "URL = 'http://[::1]:3911/api'\n");
    write(dir, "board/index.html", '<link href="//fonts.example-cdn.net/x.css"><script src="wss://live.example-cdn.net/s"></script>\n');
    const hits = findExternalUse(dir, ["backend/a.py", "board/index.html"]);
    expect(hits.length).toBe(2);
    expect(hits.join(" ")).toContain("fonts.example-cdn.net");
    expect(findSeed(dir)).toBeNull(); // only seed/matches.json counts
    write(dir, "tests/fixtures/matches.json", JSON.stringify([{ platform: "reddit" }]));
    expect(findSeed(dir)).toBeNull();
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
  const work = tmp();
  const id: RunIdentity = { fixture: FIXTURE_NAME, profile: "skill-companion-app", commit: "c1", packageSha256: "a".repeat(64) };
  try {
    const target = path.join(work, "elsewhere");
    fs.mkdirSync(path.join(target, "x"), { recursive: true });
    const run = path.join(work, "run-Link1");
    fs.mkdirSync(path.join(run, "project"), { recursive: true });
    writeManifest(run, id);
    try {
      fs.symlinkSync(target, path.join(run, "home"), "junction");
      expect(() => planResume(run, work, id)).toThrow(/is a link/);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EPERM") throw error; // links need a privilege on some hosts
    }
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
  const stub = await startStub();
  try {
    expect((await httpCall(stub.origin)("GET", "/api/health")).status).toBe(200);
    // a redirect to somewhere else is reported as it is, never followed
    expect((await httpCall(stub.origin)("GET", "/api/redirect")).status).toBe(302);
  } finally {
    await stub.close();
  }
});

// @covers FR-01.06
test("resume: a run-config alone does not skip New pipeline; a live process of the earlier run blocks resume and use", () => {
  const work = tmp();
  const id: RunIdentity = { fixture: FIXTURE_NAME, profile: "skill-companion-app", commit: "abc123", packageSha256: "f".repeat(64) };
  try {
    const run = path.join(work, "run-Lk01");
    fs.mkdirSync(path.join(run, "home"), { recursive: true });
    fs.mkdirSync(path.join(run, "project"), { recursive: true });
    writeManifest(run, id);
    write(run, "project/shipwright_run_config.json", JSON.stringify({ status: "in_progress" }));
    expect(planResume(run, work, id).skipStartPipeline).toBe(false); // config without the recorded click
    markPipelineStarted(run);
    expect(planResume(run, work, id).skipStartPipeline).toBe(true);

    acquireLock(run, process.pid);
    expect(() => planResume(run, work, id)).toThrow(/still alive/); // our own pid is alive
    expect(() => acquireLock(run, process.pid + 1)).toThrow(/still alive/);
    releaseLock(run, process.pid + 1); // not the holder: no effect
    expect(fs.existsSync(path.join(run, LOCK_NAME))).toBe(true);
    releaseLock(run);
    expect(fs.existsSync(path.join(run, LOCK_NAME))).toBe(false);
    // The spec died (stale pid) but the WebUI server it started is alive: still blocked.
    write(run, LOCK_NAME, JSON.stringify({ pid: 2_000_000_000, pids: [process.pid] }));
    expect(() => planResume(run, work, id)).toThrow(/still alive/);
    write(run, LOCK_NAME, JSON.stringify({ pid: process.pid }));
    addLockPid(run, 2_000_000_001); // recorded next to the owner
    expect(JSON.parse(fs.readFileSync(path.join(run, LOCK_NAME), "utf8")).pids).toEqual([2_000_000_001]);
    fs.rmSync(path.join(run, LOCK_NAME));
    write(run, LOCK_NAME, JSON.stringify({ pid: 2_000_000_000 })); // stale: no such process
    expect(planResume(run, work, id).runDir).toBe(path.resolve(run));
    acquireLock(run); // taken over
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("run identity: uncommitted plugin changes change the fingerprint; the package hash is computed from the files", () => {
  expect(pluginFingerprint(repo)).toMatch(/^[0-9a-f]{40}(\+[0-9a-f]{16})?$/);
  const fixtureDir = path.join(repo, "integration-tests", "fixtures", FIXTURE_NAME);
  const recorded = (JSON.parse(fs.readFileSync(path.join(fixtureDir, "brief.json"), "utf8")) as { package_sha256: string }).package_sha256;
  expect(packageDigest(repo, fixtureDir)).toBe(recorded);
  const probe = path.join(repo, "plugins", "e2e-identity-probe.txt");
  const before = pluginFingerprint(repo);
  try {
    fs.writeFileSync(probe, "one");
    const one = pluginFingerprint(repo);
    fs.writeFileSync(probe, "two");
    const two = pluginFingerprint(repo);
    expect(new Set([before, one, two]).size).toBe(3);
  } finally {
    fs.rmSync(probe, { force: true });
  }
});

// @covers FR-01.06
test("gates (S08): a run that answered no gate fails", () => {
  const l = list();
  checkGates([], [], l);
  expect(verdict(l, "S08")).toBe("fail");
});

// @covers FR-01.06
test("S05 sees scheme-less and protocol-relative external use, not file names or loopback", () => {
  const root = tmp();
  try {
    write(root, "hooks/pull.py", 'import requests\nrequests.get("api.example-svc.io/v1")\nrequests.get("localhost:3911/api")\nopen("data.json")\n');
    write(root, "board/index.html", '<style>@import "//fonts.example-cdn.net/x.css"; a{background:url(//cdn.example-cdn.net/b.png)}</style>');
    write(root, "backend/ok.py", 'fetch = lambda u: u\nfetch("seed.json")\nfetch("icons.svg")\nfetch("127.0.0.1:3911")\n');
    const hits = findExternalUse(root, ["hooks/pull.py", "board/index.html", "backend/ok.py"]);
    expect(hits.map((h) => h.split(" reaches ")[1]).sort()).toEqual(["api.example-svc.io", "cdn.example-cdn.net", "fonts.example-cdn.net"]);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("S05 ignores generated reports and tests, and still scans a hook at the plugin root", () => {
  const root = tmp();
  try {
    write(root, "playwright-report/index.html", '<script src="https://cdn.example-cdn.net/viewer.js"></script>');
    write(root, "tests/test_x.py", 'URL = "https://example-tests.io/x"\n');
    write(root, "backend/server.py", "print('ok')\n");
    write(root, "seed/matches.json", JSON.stringify(["reddit", "hackernews", "linkedin"].flatMap((p) => [1, 2, 3].map(() => ({ platform: p })))));
    const l = list();
    checkSelfContained(root, l);
    expect(verdict(l, "S05")).toBe("pass");
    write(root, "hooks/run.sh", 'curl https://leak.example-cdn.net/x\n');
    const l2 = list();
    checkSelfContained(root, l2);
    expect(verdict(l2, "S05")).toBe("fail");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
