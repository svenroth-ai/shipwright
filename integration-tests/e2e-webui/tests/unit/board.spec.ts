// No model: the board-app checks (API, board page, project files, gates, resume) against a stub companion.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { httpCall, runApiChecks } from "../../src/board-api.js";
import { checkBoardShape, checkBoardTokens, snapshotBoard, type BoardSnapshot } from "../../src/board-dom.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { FIXTURE_NAME, PLATFORMS } from "../../src/fixture.js";
import { checkPluginShape, checkScreensComposed, checkSelfContained, checkTestsRan, compareScreens, findExternalUse, findSeed } from "../../src/project-checks.js";
import { compareTokens, normalise, parseTokens } from "../../src/tokens.js";
import { startStub, type Flaws } from "./stub-companion.js";
import { isAuthFailure } from "../../src/terminal-gate.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const fixtures = path.join(repo, "integration-tests", "fixtures");
const expected = fs.readFileSync(path.join(fixtures, `${FIXTURE_NAME}-expected-result.md`), "utf8");
const list = () => new Checklist(parseChecklist(expected));
const verdict = (l: Checklist, id: string) => l.items.find((i) => i.id === id)!.verdict;
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-board-"));
const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};

// @covers FR-01.06
test("API checks: a faithful companion passes H06-H11 and S07 on a fresh data folder; a used one fails H06", async () => {
  for (const withThreads of [false]) {
    const stub = await startStub({}, withThreads);
    try {
      const l = list();
      const { log, state } = await runApiChecks(httpCall(stub.origin), l);
      for (const id of ["H06", "H07", "H08", "H09", "H10", "H11", "S07"]) expect(verdict(l, id), `${id} (threads present: ${withThreads})`).toBe("pass");
      expect(log.length).toBeGreaterThan(10);
      expect(state.posted).toBe(1);
      expect(state.drafted).toBe(3);
    } finally {
      await stub.close();
    }
  }
});

// @covers FR-01.06
test("API checks: each flaw fails the check it breaks", async () => {
  const used = await startStub({}, true);
  try {
    const l = list();
    await runApiChecks(httpCall(used.origin), l);
    expect(verdict(l, "H06")).toBe("fail"); // used data proves nothing about fetch
  } finally {
    await used.close();
  }
  const cases: [Flaws, string][] = [
    [{ repeatFetchAdds: true }, "H06"],
    [{ postedWithoutDraft: true }, "H09"],
    [{ htmlNotFound: true }, "S07"],
    [{ noPersist: true }, "H08"],
  ];
  for (const [flaws, id] of cases) {
    const stub = await startStub(flaws);
    try {
      const l = list();
      await runApiChecks(httpCall(stub.origin), l);
      expect(verdict(l, id), id).toBe("fail");
    } finally {
      await stub.close();
    }
  }
  const down = list();
  const { log } = await runApiChecks(async () => { throw new Error("connection refused"); }, down);
  expect(log.every((e) => e.error)).toBe(true);
  expect(verdict(down, "H11")).toBe("fail");
});

// @covers FR-01.06
test("board page in a real browser: shape and tokens pass for the faithful board, fail for each flaw", async ({ page }) => {
  const names = ["--color-bg", "--color-primary", "--font-size-base"];
  const declared = Object.fromEntries(Object.entries(parseTokens(fs.readFileSync(path.join(fixtures, FIXTURE_NAME, "visual-guidelines.md"), "utf8"))).filter(([k]) => names.includes(k)));
  const stub = await startStub();
  const fouled = await startStub({ chatBox: true, wrongAccent: true });
  try {
    await runApiChecks(httpCall(stub.origin), list());
    await page.goto(stub.origin);
    const snap = await snapshotBoard(page, names);
    expect(snap.tabs).toEqual([...PLATFORMS]);
    const l = list();
    checkBoardShape(snap, l);
    checkBoardTokens(snap, declared, l);
    expect(["S01", "S02", "S04"].map((id) => verdict(l, id))).toEqual(["pass", "pass", "pass"]);

    await page.goto(fouled.origin);
    const bad = await snapshotBoard(page, ["--color-primary"]);
    const l2 = list();
    checkBoardShape(bad, l2);
    checkBoardTokens(bad, { "--color-primary": "#2563eb" }, l2);
    expect(verdict(l2, "S01")).toBe("fail");
    expect(verdict(l2, "S04")).toBe("fail");

    const unbadged = await startStub({ plainBadge: true });
    try {
      await page.goto(unbadged.origin);
      const l3 = list();
      checkBoardShape(await snapshotBoard(page, names), l3);
      expect(verdict(l3, "S02")).toBe("fail"); // no element carries a badge
      expect(verdict(l3, "S01")).toBe("pass"); // the other checks are unaffected
    } finally {
      await unbadged.close();
    }
  } finally {
    await stub.close();
    await fouled.close();
  }
});

// @covers FR-01.06
test("board shape verdicts: missing tab, empty tab, unknown badge value, statuses never seen", () => {
  const ok: BoardSnapshot = {
    tabs: [...PLATFORMS], chatInputs: [], chatPanels: [], tokens: {},
    badgesByTab: { Reddit: ["new", "posted"], "Hacker News": ["new"], LinkedIn: ["drafted"] },
  };
  const run = (snap: BoardSnapshot) => { const l = list(); checkBoardShape(snap, l); return verdict(l, "S02"); };
  expect(run(ok)).toBe("pass");
  expect(run({ ...ok, tabs: ["Reddit", "LinkedIn"] })).toBe("fail");
  expect(run({ ...ok, badgesByTab: { ...ok.badgesByTab, LinkedIn: [] } })).toBe("fail");
  expect(run({ ...ok, badgesByTab: { ...ok.badgesByTab, LinkedIn: ["urgent"] } })).toBe("fail"); // only status badges count
  expect(run({ ...ok, badgesByTab: { ...ok.badgesByTab, LinkedIn: ["drafted", "12"] } })).toBe("pass"); // a counter is ignored
  expect(run({ ...ok, tabs: ["Reddit (3)", "Hacker News", "LinkedIn"] })).toBe("pass");
  expect(run({ ...ok, badgesByTab: { Reddit: ["new"], "Hacker News": ["new"], LinkedIn: ["new"] } })).toBe("fail");
});

// @covers FR-01.06
test("tokens: only the --name: value form is read, colours compare case- and shorthand-insensitively", () => {
  const t = parseTokens(fs.readFileSync(path.join(fixtures, FIXTURE_NAME, "visual-guidelines.md"), "utf8"));
  expect(Object.keys(t).filter((k) => k.startsWith("--color-")).length).toBeGreaterThanOrEqual(23);
  expect(t["--font-size-base"]).toBe("16px");
  expect(parseTokens("Background #f6f7f9, accent #2563eb")).toEqual({});
  expect(normalise("#ABC")).toBe("#aabbcc");
  expect(normalise("rgb(37, 99, 235)")).toBe("#2563eb");
  expect(compareTokens({ "--color-bg": "#F6F7F9" }, { "--color-bg": "rgb(246, 247, 249)" }).mismatches).toEqual([]);
  expect(compareTokens({ "--color-bg": "#f6f7f9" }, {}).mismatches[0]).toContain("not declared");
});

// @covers FR-01.06
test("project checks: plugin shape (H12) and the screen left as the mockup copy (H13)", () => {
  const dir = tmp();
  try {
    const l = list();
    checkPluginShape(dir, l);
    expect(verdict(l, "H12")).toBe("fail");
    write(dir, ".claude-plugin/plugin.json", "{}");
    write(dir, "skills/social-engagement/SKILL.md", "# skill");
    write(dir, "backend/server.py", "print('hi')");
    write(dir, "board/index.html", "<html></html>");
    write(dir, "tests/test_api.py", "def test_x(): pass");
    const l2 = list();
    checkPluginShape(dir, l2);
    expect(verdict(l2, "H12")).toBe("pass");

    // A real fixture mockup already carries a :root token block: an edited copy must still read as the mockup copy.
    const mock = fs.readFileSync(path.join(fixtures, FIXTURE_NAME, "mockups", "01-board.html"), "utf8");
    write(dir, ".shipwright/designs/uploads/01-board.html", mock);
    write(dir, ".shipwright/designs/screens/01-board.html", mock.replace("<html lang=\"en\">", "<html lang=\"en\"><!-- Requirements: FR-1 -->").replace(/\n/g, "\r\n"));
    expect(compareScreens(dir, ["01-board.html"])[0].state).toBe("mockup-copy");
    write(dir, ".shipwright/designs/screens/01-board.html", mock.replace("<main>", "<!-- tidied --><main data-x=\"1\">"));
    expect(compareScreens(dir, ["01-board.html"])[0].state).toBe("mockup-copy"); // differs, carries no kit
    write(dir, ".shipwright/designs/screens/01-board.html", mock.replace("</style>", "/* Untitled UI kit */</style>"));
    expect(compareScreens(dir, ["01-board.html"])[0].state).toBe("composed");
    write(dir, ".shipwright/designs/screens/01-board.html", mock.replace('class="btn"', 'class="btn btn-primary"').replace('class="badge"', 'class="badge badge-success"'));
    expect(compareScreens(dir, ["01-board.html"])[0].state).toBe("composed");
    expect(compareScreens(dir, ["02-none.html"])[0].state).toBe("missing");
    const l3 = list();
    checkScreensComposed(dir, ["01-board.html", "02-none.html"], l3);
    expect(verdict(l3, "H13")).toBe("fail");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("project checks: S05 needs a nine-match seed and no external use, S06 needs pytest and Playwright runs", () => {
  const dir = tmp();
  try {
    const seed = ["reddit", "hackernews", "linkedin"].flatMap((p) => [1, 2, 3].map((n) => ({ platform: p, title: `t${n}`, url: "https://news.ycombinator.com/item?id=1" })));
    write(dir, "seed/matches.json", JSON.stringify(seed));
    write(dir, "backend/server.py", "# see https://example.org docs\nimport json\nHOST = 'http://127.0.0.1:3911'\n");
    write(dir, "board/app.js", "fetch('/api/threads')\n");
    expect(findSeed(dir)?.total).toBe(9);
    const l = list();
    checkSelfContained(dir, l);
    expect(verdict(l, "S05")).toBe("pass");

    write(dir, "backend/server.py", "import urllib.request\nurllib.request.urlopen('https://api.reddit.com/x')\nkey = os.environ['REDDIT_API_KEY']\n");
    expect(findExternalUse(dir, ["backend/server.py"]).length).toBe(2);
    const l2 = list();
    checkSelfContained(dir, l2);
    expect(verdict(l2, "S05")).toBe("fail");

    const l3 = list();
    checkTestsRan(dir, l3);
    expect(verdict(l3, "S06")).toBe("fail");
    write(dir, "shipwright_test_results.json", JSON.stringify({ unit: { passed: 4, total: 4 }, e2e: { passed: 0, total: 0 } }));
    const l4 = list();
    checkTestsRan(dir, l4);
    expect(verdict(l4, "S06")).toBe("fail");
    write(dir, "shipwright_test_results.json", JSON.stringify({ unit: { passed: 4, total: 4, failed: 1 }, e2e: { passed: 2, total: 2 } }));
    const l4b = list();
    checkTestsRan(dir, l4b);
    expect(verdict(l4b, "S06")).toBe("fail");
    write(dir, "shipwright_test_results.json", JSON.stringify({ unit: { passed: 4, total: 4 }, e2e: { passed: 2, total: 2 } }));
    const l5 = list();
    checkTestsRan(dir, l5);
    expect(verdict(l5, "S06")).toBe("pass");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("run-12: templated loopback and placeholder URLs are not external use", () => {
  const dir = tmp();
  try {
    write(dir, "backend/a.py", "A = f'http://127.0.0.1:{port}/x'\nB = f'http://{DEFAULT_HOST}:{port}'\n");
    expect(findExternalUse(dir, ["backend/a.py"])).toEqual([]);
    write(dir, "backend/b.py", "C = f'https://api.reddit.com:{port}/x'\n");
    expect(findExternalUse(dir, ["backend/b.py"]).length).toBe(1);
    write(dir, "backend/c.py", "D = f'https://{region}.api.openai.com/v1'\n");
    expect(findExternalUse(dir, ["backend/c.py"]).length).toBe(1);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("run-12: S06 accepts total = passed+failed as well as passed+failed+skipped", () => {
  const dir = tmp();
  try {
    write(dir, "shipwright_test_results.json", JSON.stringify({ unit: { passed: 399, total: 399, failed: 0, skipped: 1 }, e2e: { passed: 5, total: 6, failed: 0, skipped: 1 } }));
    const l = list();
    checkTestsRan(dir, l);
    expect(verdict(l, "S06")).toBe("pass");
    write(dir, "shipwright_test_results.json", JSON.stringify({ unit: { passed: 3, total: 9, failed: 0, skipped: 1 }, e2e: { passed: 5, total: 5, failed: 0 } }));
    const l2 = list();
    checkTestsRan(dir, l2);
    expect(verdict(l2, "S06")).toBe("fail");
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("run-12: an agent auth failure in the terminal is detected", () => {
  expect(isAuthFailure("Login expired. Please run /login")).toBe(true);
  expect(isAuthFailure("API Error: authentication_failed")).toBe(true);
  expect(isAuthFailure("all good")).toBe(false);
  expect(isAuthFailure("● API Error: 401 authentication_failed")).toBe(true);
  expect(isAuthFailure("+ // authentication_failed handler\n+ const msg = 'Login expired';")).toBe(false);
  expect(isAuthFailure("+ throw new Error('Invalid API key')\n+ // authentication_failed handler\n" + "x\n".repeat(8))).toBe(false);
});
