// No model: the checks of the real-skill fixture variant (master-detail board, source adapter, S09) against an in-memory
// companion, the approved mockups in a real browser, and temp project folders.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { expect, test } from "@playwright/test";
import type { ApiAnswer, Call } from "../../src/board-api.js";
import { runRealApiChecks, type RealThreadState } from "../../src/board-api-real.js";
import { checkBoardTokens } from "../../src/board-dom.js";
import { checkMasterDetailShape, snapshotMasterDetail, type MasterDetailSnapshot } from "../../src/board-dom-real.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { activeFixture, FIXTURE_NAME, REAL_FIXTURE_NAME } from "../../src/fixture.js";
import { checkSelfContainedWithAdapter, findRecorded } from "../../src/project-checks-adapter.js";
import { checkSkillTriggers, projectSkillNames, skillsCalled, stagePluginCopy, TRIGGER_PHRASE } from "../../src/skill-trigger.js";
import { compareFonts, parseFontTokens, parseTokens } from "../../src/tokens.js";
import { variantFor } from "../../src/variant.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const fixtures = path.join(repo, "integration-tests", "fixtures");
const real = path.join(fixtures, REAL_FIXTURE_NAME);
const list = () => new Checklist(parseChecklist(fs.readFileSync(path.join(fixtures, `${REAL_FIXTURE_NAME}-expected-result.md`), "utf8")));
const verdict = (l: Checklist, id: string) => l.items.find((i) => i.id === id)!.verdict;
const guidelines = fs.readFileSync(path.join(real, "visual-guidelines.md"), "utf8");

// An in-memory companion that follows brief.md's Companion API; `flaw` breaks one documented rule.
type Thread = Record<string, unknown>;
function memoryCompanion(flaw: "none" | "no-summary" | "no-skip" | "any-source-kind" = "none"): Call {
  let threads: Thread[] = [];
  let sources: unknown[] = [];
  const ans = (status: number, json: unknown): ApiAnswer => ({ status, contentType: "application/json", text: JSON.stringify(json), json });
  const view = (t: Thread) => ({ ...t, ...(flaw === "no-summary" ? { summary: undefined } : {}) });
  return async (method, p, body) => {
    const url = new URL(p, "http://127.0.0.1");
    const b = (body ?? {}) as Record<string, unknown>;
    const m = /^\/api\/threads\/(\d+)(?:\/(draft|posted|skipped|feedback))?$/.exec(url.pathname);
    if (url.pathname === "/api/threads") {
      const s = url.searchParams.get("status");
      return ans(200, { threads: threads.filter((t) => !s || t.status === s).map(view) });
    }
    if (url.pathname === "/api/fetch") {
      if (threads.length > 0) return ans(200, { added: 0 });
      threads = Array.from({ length: 9 }, (_, i) => ({
        id: i + 1, platform: ["reddit", "hackernews", "linkedin"][i % 3], title: `Thread ${i + 1}`, status: i >= 7 ? "expired" : "new",
        summary: { question: "q", others: "o", angle: "a" }, comments: [{ author: "u", text: "t", depth: 0 }], draft: null, feedback: null,
      }));
      return ans(200, { added: 9 });
    }
    if (url.pathname === "/api/sources") {
      if (method === "PUT") {
        const next = (b.sources as { kind: string }[]) ?? [];
        if (flaw !== "any-source-kind" && next.some((s) => !["syften", "linkedin"].includes(s.kind))) return ans(400, { error: "Unknown source kind" });
        sources = next;
      }
      return ans(200, { sources });
    }
    if (m) {
      const t = threads.find((x) => x.id === Number(m[1]));
      if (!t) return ans(404, { error: `There is no thread ${m[1]}` });
      if (m[2] === "draft") { t.status = "drafted"; t.draft = `Hi ${t.title}`; }
      if (m[2] === "feedback") { if (t.status !== "drafted") return ans(409, { error: "Not drafted" }); t.feedback = b.feedback; }
      if (m[2] === "posted") { if (t.status !== "drafted") return ans(409, { error: "Not drafted" }); t.status = "posted"; }
      if (m[2] === "skipped") { if (flaw === "no-skip") return ans(404, { error: "no such route" }); t.status = "skipped"; }
      return ans(200, view(t));
    }
    return ans(404, { error: "Unknown route" });
  };
}

// @covers FR-01.06
test("fixture selection: default is the tabs fixture, the real one is opt-in, a typo is refused", () => {
  expect(activeFixture({})).toBe(FIXTURE_NAME);
  expect(activeFixture({ SHIPWRIGHT_E2E_FIXTURE: REAL_FIXTURE_NAME })).toBe(REAL_FIXTURE_NAME);
  expect(() => activeFixture({ SHIPWRIGHT_E2E_FIXTURE: "social-engagement" })).toThrow(/must be/);
  expect(variantFor(REAL_FIXTURE_NAME)).not.toBe(variantFor(FIXTURE_NAME));
});

// @covers FR-01.06
test("real API checks: a faithful companion passes H06-H11, H14 and S07; each flaw fails its own item", async () => {
  const ok = list();
  const { state } = await runRealApiChecks(memoryCompanion(), ok);
  for (const id of ["H06", "H07", "H08", "H09", "H10", "H11", "H14", "S07"]) expect(verdict(ok, id), id).toBe("pass");
  expect(state.posted).toBe(1);
  expect(state.platformOf[1]).toBe("reddit");
  const cases: [Parameters<typeof memoryCompanion>[0], string][] = [["no-summary", "H07"], ["no-skip", "H09"], ["any-source-kind", "H10"]];
  for (const [flaw, id] of cases) {
    const l = list();
    await runRealApiChecks(memoryCompanion(flaw), l);
    expect(verdict(l, id), `${flaw} -> ${id}`).toBe("fail");
  }
});

// @covers FR-01.06
test("font tokens: the real guidelines declare Inter and Geist Mono; a served stack passes on its first family only", () => {
  const fonts = parseFontTokens(guidelines);
  expect(fonts).toEqual({ "--font-family": "Inter", "--font-mono": "Geist Mono" });
  expect(compareFonts(fonts, { "--font-family": "Inter,system-ui,sans-serif", "--font-mono": '"Geist Mono",ui-monospace' }).mismatches).toEqual([]);
  expect(compareFonts(fonts, { "--font-family": "system-ui, Inter", "--font-mono": "" }).mismatches).toHaveLength(2);
});

// @covers FR-01.06
test("master-detail board in a real browser: the approved mockups satisfy S01, S02 and S04 (colours, sizes and fonts)", async ({ page }) => {
  const declared = parseTokens(guidelines);
  const fonts = parseFontTokens(guidelines);
  // The static page 03 shows one thread (the drafted pricing one), so both ids the harness opens (fresh and drafted) point at that title; id 3 is never opened.
  const state: RealThreadState = {
    posted: 3, drafted: 2, fresh: 1, perPlatform: {},
    titles: { 1: "How are you pricing AI dev tools like Shipwright for small teams?", 2: "How are you pricing AI dev tools like Shipwright for small teams?", 3: "Any integrations between Shipwright and Jira?" },
    platformOf: { 1: "reddit", 2: "reddit", 3: "reddit" },
  };
  await page.goto(pathToFileURL(path.join(real, "mockups", "03-reply-draft.html")).href);
  const snap = await snapshotMasterDetail(page, [...Object.keys(declared), ...Object.keys(fonts)], state);
  const l = list();
  checkMasterDetailShape(snap, l);
  checkBoardTokens(snap, declared, l, fonts);
  expect(["S01", "S02", "S04"].map((id) => verdict(l, id))).toEqual(["pass", "pass", "pass"]);

  // Each flaw fails S02/S04 on its own: a Keywords tab, a missing status, no Copy reply, a wrong font.
  const base: MasterDetailSnapshot = { ...snap };
  const run = (s: MasterDetailSnapshot) => { const x = list(); checkMasterDetailShape(s, x); return verdict(x, "S02"); };
  expect(run({ ...base, keywordsTab: true })).toBe("fail");
  expect(run({ ...base, filterOptions: base.filterOptions.filter((o) => !o.includes("expired")) })).toBe("fail");
  expect(run({ ...base, copyReply: false })).toBe("fail");
  expect(run({ ...base, listBesideThread: false })).toBe("fail");
  expect(run({ ...base, switcher: ["Reddit 4", "Hacker News 3"] })).toBe("fail");
  const l2 = list();
  checkBoardTokens({ ...snap, tokens: { ...snap.tokens, "--font-family": "system-ui" } }, declared, l2, fonts);
  expect(verdict(l2, "S04")).toBe("fail");
  await page.goto(pathToFileURL(path.join(real, "mockups", "05-sources.html")).href);
  const sources = await snapshotMasterDetail(page, [], state);
  expect(sources.keywordsTab, "sources are a panel, not a Keywords tab").toBe(false);
});

// @covers FR-01.06
test("S02 with the run's data: counts that read 0, or a skipped/expired status that is never rendered, fail; a page needs the click to show the thread", async ({ page }) => {
  const state: RealThreadState = { posted: 1, drafted: 1, fresh: 1, perPlatform: { reddit: 4, hackernews: 4, linkedin: 4 }, titles: { 1: "How are you pricing AI dev tools like Shipwright for small teams?" }, platformOf: { 1: "reddit" } };
  const clickState: RealThreadState = { ...state, titles: { 1: "A click reveals me" } };
  await page.goto(pathToFileURL(path.join(real, "mockups", "03-reply-draft.html")).href);
  const base = await snapshotMasterDetail(page, [], state);
  const run = (s: MasterDetailSnapshot, per: Record<string, number>) => { const l = list(); checkMasterDetailShape(s, l, per); return verdict(l, "S02"); };
  const withSkipped = { ...base, badgesByTab: Object.fromEntries(Object.entries(base.badgesByTab).map(([n, b]) => [n, [...b, "skipped"]])) };
  expect(run(base, state.perPlatform), "no skipped badge anywhere").toBe("fail");
  expect(run(withSkipped, state.perPlatform)).toBe("pass");
  expect(run({ ...withSkipped, switcher: ["Reddit 0", "Hacker News 0", "LinkedIn 0"] }, state.perPlatform)).toBe("fail");

  const reveal = "document.getElementById(`d`).innerHTML = `<h2>A click reveals me</h2>`; return false";
  const body = (revealed: boolean) => `<div role="tablist"><button role="tab">Reddit 4</button></div><nav><a id="row" href="#" ${revealed ? `onclick="${reveal}"` : ""}>A click reveals me</a></nav><main id="d"></main>`;
  await page.setContent(body(true));
  expect((await snapshotMasterDetail(page, [], clickState)).listBesideThread).toBe(true);
  await page.setContent(body(false));
  expect((await snapshotMasterDetail(page, [], clickState)).listBesideThread, "the row does nothing").toBe(false);
});

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-real-"));
const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};
const day = (n: number) => new Date(Date.UTC(2026, 9, 29) - n * 86_400_000).toISOString();
/** `aged`: the first item of every platform is 40 days older than the rest (two or more are needed overall). */
const recorded = (root: string, perPlatform = 3, aged = true, fields: { url?: boolean } = {}) => {
  const when = (i: number) => day(i === 0 && aged ? 40 : i);
  const mk = (backend: string) => Array.from({ length: perPlatform }, (_, i) => ({ id: i, item: { ...(fields.url === false ? {} : { item_url: `u${i}` }), backend, title: `t${i}`, timestamp: when(i) } }));
  write(root, "seed/recorded/syften.json", JSON.stringify([...mk("reddit"), ...mk("hackernews")]));
  write(root, "seed/recorded/apify_linkedin.json", JSON.stringify(Array.from({ length: perPlatform }, (_, i) => ({ id: i, linkedinUrl: `l${i}`, content: `c${i}`, postedAt: { date: when(i) } }))));
};

// @covers FR-01.06
test("S05 variant: only the adapter may name a service; the adapter must define fetch_items; recorded answers must be complete", () => {
  const root = tmp();
  try {
    write(root, "backend/server.py", "from sources import fetch_items\nHOST = 'http://127.0.0.1:3911'\n");
    write(root, "backend/sources/__init__.py", "import os\nURL = 'https://syften.com/api/v1/items'\nTOKEN = os.environ.get('SYFTEN_TOKEN')\ndef fetch_items(sources):\n    return []\n");
    recorded(root);
    const l = list();
    checkSelfContainedWithAdapter(root, l);
    expect(verdict(l, "S05"), l.items.find((i) => i.id === "S05")!.evidence).toBe("pass");
    expect(findRecorded(root).perPlatform).toEqual({ reddit: 3, hackernews: 3, linkedin: 3 });

    write(root, "board/app.js", "fetch('https://api.apify.com/v2/acts')\n"); // outside the adapter
    const l2 = list();
    checkSelfContainedWithAdapter(root, l2);
    expect(verdict(l2, "S05")).toBe("fail");
    expect(l2.items.find((i) => i.id === "S05")!.evidence).toMatch(/outside the adapter.*api\.apify\.com/);
    fs.rmSync(path.join(root, "board"), { recursive: true });

    write(root, "backend/sources/__init__.py", "URL = 'https://syften.com/api/v1/items'\n"); // no fetch_items
    const l3 = list();
    checkSelfContainedWithAdapter(root, l3);
    expect(verdict(l3, "S05")).toBe("fail");

    write(root, "backend/sources/__init__.py", "def fetch_items(s):\n    return []\n");
    recorded(root, 2); // two per platform is too few
    const l4 = list();
    checkSelfContainedWithAdapter(root, l4);
    expect(verdict(l4, "S05")).toBe("fail");
    fs.rmSync(path.join(root, "seed"), { recursive: true });
    const l5 = list();
    checkSelfContainedWithAdapter(root, l5);
    expect(l5.items.find((i) => i.id === "S05")!.evidence).toMatch(/recorded answers missing/);

    // Entries that lack documented fields are not counted, and a set with no old item gives the board no expired thread.
    recorded(root, 3, true, { url: false });
    expect(findRecorded(root).perPlatform).toEqual({ reddit: 0, hackernews: 0, linkedin: 3 });
    recorded(root, 3, false);
    expect(findRecorded(root)).toMatchObject({ total: 9, old: 0 });
    const l6 = list();
    checkSelfContainedWithAdapter(root, l6);
    expect(verdict(l6, "S05")).toBe("fail");
    recorded(root);
    expect(findRecorded(root).old).toBeGreaterThanOrEqual(2);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

const stream = (...blocks: object[]) => blocks.map((content) => JSON.stringify({ type: "assistant", message: { content: [content] } })).join("\n");

// @covers FR-01.06
test("S09: reads Skill calls from a stream, is not run unless asked for, and never fails the run (soft)", () => {
  const called = stream({ type: "text", text: "ok" }, { type: "tool_use", name: "Skill", input: { skill: "social-engagement" } }, { type: "tool_use", name: "Bash", input: {} });
  expect(skillsCalled(`not json\n${called}`)).toEqual(["social-engagement"]);
  expect(skillsCalled(stream({ type: "text", text: "no skill" }))).toEqual([]);

  const proj = tmp();
  write(proj, ".claude-plugin/plugin.json", JSON.stringify({ name: "social-engagement-app" }));
  write(proj, "skills/social-engagement/SKILL.md", "# skill");
  const off = list();
  checkSkillTriggers(proj, off, {}, () => { throw new Error("must not run"); });
  expect(verdict(off, "S09")).toBe("not evaluated");

  const phrases: string[] = [];
  const hit = list();
  checkSkillTriggers(proj, hit, { SHIPWRIGHT_E2E_SKILL_TRIGGER: "1" }, (_p, phrase) => { phrases.push(phrase); return { stdout: called, status: 0 }; });
  expect(verdict(hit, "S09")).toBe("observed");
  expect(phrases).toEqual([TRIGGER_PHRASE]);
  expect(projectSkillNames(proj)).toEqual(new Set(["social-engagement", "social-engagement-app:social-engagement"]));

  // Another plugin's skill in the provisioned home is not the project's skill.
  const foreign = list();
  const other = stream({ type: "tool_use", name: "Skill", input: { skill: "shipwright-preview:preview" } });
  checkSkillTriggers(proj, foreign, { SHIPWRIGHT_E2E_SKILL_TRIGGER: "1" }, () => ({ stdout: other, status: 0 }));
  expect(verdict(foreign, "S09")).toBe("fail");
  expect(foreign.items.find((i) => i.id === "S09")!.evidence).toMatch(/shipwright-preview:preview/);

  const miss = list();
  checkSkillTriggers(proj, miss, { SHIPWRIGHT_E2E_SKILL_TRIGGER: "1" }, () => ({ stdout: stream({ type: "text", text: "hi" }), status: 0 }));
  expect(verdict(miss, "S09")).toBe("fail");
  const broken = list();
  checkSkillTriggers(proj, broken, { SHIPWRIGHT_E2E_SKILL_TRIGGER: "1" }, () => ({ stdout: "", status: null, error: "spawn claude ENOENT" }));
  expect(verdict(broken, "S09")).toBe("not evaluated");
  expect(broken.hardOpen().map((i) => i.id)).not.toContain("S09");
  fs.rmSync(proj, { recursive: true, force: true });
});

// @covers FR-01.06
test("S09 loads a scratch copy of the project: skills and a hook-free manifest only, nothing the model wrote that could run", () => {
  const proj = tmp();
  write(proj, ".claude-plugin/plugin.json", JSON.stringify({ name: "app", hooks: "hooks/hooks.json", mcpServers: {}, description: "kept" }));
  write(proj, "skills/board/SKILL.md", "# skill");
  write(proj, "hooks/hooks.json", "{}");
  write(proj, "hooks/run.py", "print('x')");
  write(proj, ".mcp.json", "{}");
  write(proj, "commands/c.md", "x");
  const copy = stagePluginCopy(proj);
  try {
    expect(copy).not.toBe(proj);
    expect(fs.readdirSync(copy).sort()).toEqual([".claude-plugin", "skills"]);
    expect(fs.existsSync(path.join(copy, "skills", "board", "SKILL.md"))).toBe(true);
    const manifest = JSON.parse(fs.readFileSync(path.join(copy, ".claude-plugin", "plugin.json"), "utf8"));
    expect(manifest).toEqual({ name: "app", description: "kept" });
  } finally {
    fs.rmSync(copy, { recursive: true, force: true });
  }
});
