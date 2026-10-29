// No model: gates (S08), resume, the tour targets and the review-round hardening of the project checks.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { httpCall } from "../../src/board-api.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { FIXTURE_NAME } from "../../src/fixture.js";
import { checkGates, classifyGates } from "../../src/gates.js";
import { findExternalUse, findSeed } from "../../src/project-checks.js";
import { markFinished, planResume, ResumeError, writeManifest, type RunIdentity } from "../../src/resume.js";
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
    writeManifest(run, id); // a fresh manifest: not finished
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
