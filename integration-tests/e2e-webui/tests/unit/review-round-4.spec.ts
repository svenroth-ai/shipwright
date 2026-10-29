// No model: review round 4 - S08 over a resumed run, whole-text gate vetoes, S02 platform mapping, S06 skips,
// H06 on unreadable answers, links anywhere in the provisioned home.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { httpCall, runApiChecks, type Call } from "../../src/board-api.js";
import { checkBoardShape, type BoardSnapshot } from "../../src/board-dom.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { FIXTURE_NAME, PLATFORMS } from "../../src/fixture.js";
import { appendRecord, GATE_LOG, loadRecords, wholeRun } from "../../src/gate-log.js";
import { checkGates, classifyGates } from "../../src/gates.js";
import { checkTestsRan } from "../../src/project-checks.js";
import { planResume, writeManifest, type RunIdentity } from "../../src/resume.js";
import { startStub } from "./stub-companion.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const expected = fs.readFileSync(path.join(repo, "integration-tests", "fixtures", `${FIXTURE_NAME}-expected-result.md`), "utf8");
const list = () => new Checklist(parseChecklist(expected));
const verdict = (l: Checklist, id: string) => l.items.find((i) => i.id === id)!.verdict;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-r4-"));
const option = (o: string, q = "Proceed?") => `terminal question answered with its first option "${o}" (${q})`;

// @covers FR-01.06
test("S08 judges the whole run: an unexpected gate of an earlier part still fails after a resume", () => {
  const run = tmp();
  try {
    appendRecord(run, "gate", option("Approve the design"));
    // the first part ended with an unexpected gate; the resumed part only answered an expected one
    appendRecord(run, "gate", option("Continue", "How to proceed?"));
    appendRecord(run, "gate", option("Approve the screens"));
    const whole = loadRecords(run);
    expect(whole.gates.length).toBe(3);
    const l = list();
    checkGates(whole.gates, whole.escalations, l);
    expect(verdict(l, "S08")).toBe("fail");

    const clean = tmp();
    try {
      appendRecord(clean, "gate", option("Approve the design"));
      appendRecord(clean, "gate", option("Approve the screens"));
      const l2 = list();
      checkGates(loadRecords(clean).gates, loadRecords(clean).escalations, l2);
      expect(verdict(l2, "S08")).toBe("pass");
      appendRecord(clean, "escalation", "No progress for 20 minutes");
      expect(loadRecords(clean).escalations).toEqual(["No progress for 20 minutes"]);
      fs.appendFileSync(path.join(clean, GATE_LOG), "not json\n");
      expect(loadRecords(clean).escalations.length).toBe(2); // an unreadable line fails closed
    } finally {
      fs.rmSync(clean, { recursive: true, force: true });
    }
    expect(loadRecords(path.join(run, "nowhere"))).toEqual({ gates: [], escalations: [] });
  } finally {
    fs.rmSync(run, { recursive: true, force: true });
  }
});

// @covers FR-01.01
test("gates: the veto reads the question too, and catches 'do not approve' forms", () => {
  expect(classifyGates([option("Approve", "Skip the design review?")]).unexpected.length).toBe(1);
  expect(classifyGates([option("Approve", "Waive the check and approve?")]).unexpected.length).toBe(1);
  for (const o of ["Do not approve", "Don't approve", "Disapprove"]) expect(classifyGates([option(o)]).unexpected.length, o).toBe(1);
  expect(classifyGates([option("Approve the design", "Approve the design, or how do you want to proceed?")]).unexpected).toEqual([]);
});

// @covers FR-01.06
test("S02: badges must tie to the API threads - fewer badges, an unmappable platform or an uncounted tab fails", () => {
  const ok: BoardSnapshot = {
    tabs: [...PLATFORMS], chatInputs: [], chatPanels: [], tokens: {},
    badgesByTab: { Reddit: ["new", "posted"], "Hacker News": ["new"], LinkedIn: ["drafted"] },
  };
  const run = (perPlatform: Record<string, number>) => { const l = list(); checkBoardShape(ok, l, perPlatform); return verdict(l, "S02"); };
  expect(run({ reddit: 2, hackernews: 1, linkedin: 1 })).toBe("pass");
  expect(run({ reddit: 3, hackernews: 1, linkedin: 1 })).toBe("fail"); // fewer badges than threads
  expect(run({ reddit: 2, hackernews: 1, linkedin: 1, mastodon: 1 })).toBe("fail"); // no tab for this platform
  expect(run({ reddit: 2, hackernews: 1 })).toBe("fail"); // the LinkedIn tab has no API count
  expect(run({})).toBe("pass"); // the API listed no threads: nothing to tie
});

// @covers FR-01.06
test("S06: skipped tests count toward the total, a gap or a failure does not", () => {
  const dir = tmp();
  try {
    const put = (unit: object, e2e: object) => fs.writeFileSync(path.join(dir, "shipwright_test_results.json"), JSON.stringify({ unit, e2e }));
    const run = () => { const l = list(); checkTestsRan(dir, l); return verdict(l, "S06"); };
    put({ passed: 3, skipped: 1, total: 4 }, { passed: 2, total: 2 });
    expect(run()).toBe("pass");
    put({ passed: 2, skipped: 1, total: 4 }, { passed: 2, total: 2 });
    expect(run()).toBe("fail"); // one test unaccounted for
    put({ passed: 3, skipped: 1, failed: 1, total: 4 }, { passed: 2, total: 2 });
    expect(run()).toBe("fail");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("H06 needs a readable list before the fetch and a 200 on both fetches", async () => {
  const stub = await startStub({}, false);
  try {
    const real = httpCall(stub.origin);
    const run = async (call: Call) => { const l = list(); await runApiChecks(call, l); return verdict(l, "H06"); };
    expect(await run(real)).toBe("pass");
    const stub2 = await startStub({}, false);
    try {
      let lists = 0;
      const broken: Call = async (m, p, b) => (m === "GET" && p === "/api/threads" && lists++ === 0 ? { status: 500, contentType: "application/json", text: "{}", json: {} } : httpCall(stub2.origin)(m, p, b));
      expect(await run(broken)).toBe("fail"); // freshness unproven
    } finally {
      await stub2.close();
    }
    const stub3 = await startStub({}, false);
    try {
      let fetches = 0;
      const second: Call = async (m, p, b) => (p === "/api/fetch" && ++fetches === 2 ? { status: 500, contentType: "application/json", text: "{\"added\":0}", json: { added: 0 } } : httpCall(stub3.origin)(m, p, b));
      expect(await run(second)).toBe("fail");
    } finally {
      await stub3.close();
    }
  } finally {
    await stub.close();
  }
});

// @covers FR-01.06
test("resume refuses a link anywhere the provisioning writes: plugins/cache and the plugin files", () => {
  const work = tmp();
  const id: RunIdentity = { fixture: FIXTURE_NAME, profile: "skill-companion-app", commit: "c1", packageSha256: "a".repeat(64) };
  try {
    const target = path.join(work, "elsewhere");
    fs.mkdirSync(target, { recursive: true });
    fs.writeFileSync(path.join(target, "f.json"), "{}");
    for (const [n, name] of [["cache", "cache"], ["cache/shipwright", "shipwright"], ["installed_plugins.json", "installed_plugins.json"]] as const) {
      const run = path.join(work, `run-L${name.replace(/\W/g, "")}`);
      fs.mkdirSync(path.join(run, "project"), { recursive: true });
      fs.mkdirSync(path.join(run, "home", ".claude", "plugins", ...(n === "cache/shipwright" ? ["cache"] : [])), { recursive: true });
      writeManifest(run, id);
      try {
        fs.symlinkSync(n === "installed_plugins.json" ? path.join(target, "f.json") : target, path.join(run, "home", ".claude", "plugins", n), n === "installed_plugins.json" ? "file" : "junction");
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "EPERM") return; // links need a privilege on some hosts
        throw error;
      }
      expect(() => planResume(run, work, id), n).toThrow(/is a link/);
    }
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("S06: an all-skipped suite or a runner that reports failure does not pass", () => {
  const dir = tmp();
  try {
    const put = (unit: object, e2e: object) => fs.writeFileSync(path.join(dir, "shipwright_test_results.json"), JSON.stringify({ unit, e2e }));
    const run = () => { const l = list(); checkTestsRan(dir, l); return verdict(l, "S06"); };
    put({ passed: 0, skipped: 5, total: 5 }, { passed: 2, total: 2 });
    expect(run()).toBe("fail");
    put({ passed: 3, total: 3 }, { passed: 0, skipped: 2, total: 2 });
    expect(run()).toBe("fail");
    put({ passed: 5, total: 5, success: false }, { passed: 2, total: 2 });
    expect(run()).toBe("fail"); // pytest "5 passed, 2 errors"
    put({ passed: 5, total: 5 }, { passed: 2, total: 2, exit_code: 1 });
    expect(run()).toBe("fail");
    put({ passed: 5, total: 5, success: true, exit_code: 0 }, { passed: 2, total: 2, exit_code: 0 });
    expect(run()).toBe("pass");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("S08 evidence is the earlier part loaded at start plus this run's memory, not a later re-read of the file", () => {
  const run = tmp();
  try {
    appendRecord(run, "gate", option("Approve the design"));
    const atStart = loadRecords(run);
    // the agent under test tampers with the file during the run
    fs.writeFileSync(path.join(run, GATE_LOG), "");
    const judged = wholeRun(atStart, [option("Continue", "How to proceed?")], ["No progress for 20 minutes"]);
    expect(judged.gates.length).toBe(2);
    const l = list();
    checkGates(judged.gates, judged.escalations, l);
    expect(verdict(l, "S08")).toBe("fail");
    expect(loadRecords(run)).toEqual({ gates: [], escalations: [] }); // the wiped file would have shown nothing
  } finally {
    fs.rmSync(run, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("resume refuses an unknown plugin commit", () => {
  const work = tmp();
  try {
    const unknown: RunIdentity = { fixture: FIXTURE_NAME, profile: "skill-companion-app", commit: "unknown", packageSha256: "a".repeat(64) };
    const run = path.join(work, "run-Unk1");
    fs.mkdirSync(path.join(run, "project"), { recursive: true });
    fs.mkdirSync(path.join(run, "home"), { recursive: true });
    writeManifest(run, unknown);
    expect(() => planResume(run, work, unknown)).toThrow(/commit is unknown/);
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
});
