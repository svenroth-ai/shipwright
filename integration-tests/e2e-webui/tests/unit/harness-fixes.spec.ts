// No model: the harness fixes of the trg-cbf58cba iterate. S05 (the app's own e2e/ suite and reserved test domains are no
// external use), S02 (the row click must hit a VISIBLE match, not the hidden thread-picker option) and the launch retry.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { checkMasterDetailShape, snapshotMasterDetail, type MasterDetailSnapshot } from "../../src/board-dom-real.js";
import type { RealThreadState } from "../../src/board-api-real.js";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { launchedByModal, startTaskSession, taskStateText } from "../../src/driver.js";
import { captureLaunchCommands, ensureLaunched, launchVerdict } from "../../src/launch-recovery.js";
import { REAL_FIXTURE_NAME } from "../../src/fixture.js";
import { findExternalUse } from "../../src/project-checks.js";
import { checkSelfContainedWithAdapter } from "../../src/project-checks-adapter.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const list = () => new Checklist(parseChecklist(fs.readFileSync(path.join(repo, "integration-tests", "fixtures", `${REAL_FIXTURE_NAME}-expected-result.md`), "utf8")));
const verdict = (l: Checklist, id: string) => l.items.find((i) => i.id === id)!.verdict;
const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};
const day = (n: number) => new Date(Date.UTC(2026, 9, 29) - n * 86_400_000).toISOString();

// @covers FR-01.06
test("S05 variant: the app's own e2e/ suite and reserved test domains (.example, .test, .invalid, .localhost) are not external use", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-s05-"));
  try {
    write(root, "backend/server.py", "from sources import fetch_items\nHOST = 'http://127.0.0.1:3911'\n");
    write(root, "backend/sources/__init__.py", "def fetch_items(sources):\n    return []\n");
    write(root, "board/app.js", "const LINK = 'https://www.reddit.example/r/x/comments/1';\nconst H = 'https://news.hn.test/item?id=1';\n");
    write(root, "e2e/reply.spec.ts", "await page.goto('https://api.reddit.com/live');\n");
    write(root, "e2e/screenshot-fixture.mjs", "const u = 'https://www.linkedin.com/posts/x';\n");
    const mk = (backend: string) => [0, 1, 2].map((i) => ({ item: { item_url: `u${i}`, backend, title: `t${i}`, timestamp: day(i === 0 ? 40 : i) } }));
    write(root, "seed/recorded/syften.json", JSON.stringify([...mk("reddit"), ...mk("hackernews")]));
    write(root, "seed/recorded/apify_linkedin.json", JSON.stringify([0, 1, 2].map((i) => ({ linkedinUrl: `l${i}`, content: `c${i}`, postedAt: { date: day(i === 0 ? 40 : i) } }))));
    const ref = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-s05-ref-"));
    fs.cpSync(path.join(root, "seed", "recorded"), ref, { recursive: true }); // stands in for the package's files
    const l = list();
    checkSelfContainedWithAdapter(root, l, ref);
    expect(verdict(l, "S05"), l.items.find((i) => i.id === "S05")!.evidence).toBe("pass");
    expect(findExternalUse(root, ["board/app.js"], { reservedTestDomains: true })).toEqual([]);
    expect(findExternalUse(root, ["board/app.js"]).length, "the tabs variant stays strict").toBe(2);
    write(root, "hooks/a.py", "u = 'https://x.invalid/a'\nv = 'http://svc.localhost:8/b'\nw = 'https://reddit.example.com/real'\n");
    // only the reserved TLD is exempt, not a lookalike host that merely starts with it
    expect(findExternalUse(root, ["hooks/a.py"], { reservedTestDomains: true }).map((h) => h.split(" reaches ")[1])).toEqual(["reddit.example.com"]);
    write(root, "board/leak.js", "fetch('https://api.apify.com/v2/acts')\n"); // a real service outside the adapter still fails
    const l2 = list();
    checkSelfContainedWithAdapter(root, l2, ref);
    expect(verdict(l2, "S05")).toBe("fail");
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("S02: a hidden thread-picker option before the list must not swallow the row click; the evidence says what was clicked", async ({ page }) => {
  test.setTimeout(90_000); // each open that finds no visible row waits 8 s before giving up
  const state: RealThreadState = { posted: 1, drafted: 2, fresh: 1, perPlatform: {}, titles: { 1: "A fresh thread title", 2: "A drafted thread title" }, platformOf: { 1: "reddit", 2: "reddit" } };
  // The built app's shape (run 14): the picker (display:none on a wide screen) precedes the list and carries every title as an option.
  const board = (copyReply: boolean) => `<style>.master-picker{display:none}</style>
    <div role="tablist"><button role="tab">Reddit 2</button></div>
    <nav><div class="master-picker"><select id="thread-picker"><option value="1">A fresh thread title</option><option value="2">A drafted thread title</option></select></div>
    <div id="thread-list"><a href="#" data-id="1" onclick="show(1);return false">A fresh thread title</a><a href="#" data-id="2" onclick="show(2);return false">A drafted thread title</a></div></nav>
    <main id="pane"></main>
    <script>function show(id){document.getElementById('pane').innerHTML='<h2>'+(id===1?'A fresh thread title':'A drafted thread title')+'</h2>'+(id===2&&${copyReply}?'<button>Copy reply</button>':'');}</script>`;
  await page.setContent(board(true));
  const ok = await snapshotMasterDetail(page, [], state);
  expect(ok.listBesideThread).toBe(true);
  expect(ok.copyReply).toBe(true);
  expect(ok.diagnostics).toMatch(/open fresh: thread 1 .*clicked a, 2 visible afterwards/);
  expect(ok.diagnostics).not.toMatch(/clicked option|failed:/);
  expect(ok.diagnostics).toMatch(/Copy reply buttons: 1 visible of 1/);

  // An app that really has no Copy reply for the drafted thread still fails, and the evidence names the cause.
  await page.setContent(board(false));
  const bad = await snapshotMasterDetail(page, [], state);
  expect(bad.copyReply).toBe(false);
  expect(bad.diagnostics).toMatch(/Copy reply buttons: 0 visible of 0/);
  const l = list();
  checkMasterDetailShape({ ...(bad as MasterDetailSnapshot) }, l);
  expect(l.items.find((i) => i.id === "S02")!.evidence).toMatch(/diagnostics: open fresh: thread 1/);

  // A Copy reply button that exists but is hidden fails S02 and the evidence says it is hidden, not absent.
  await page.setContent(board(true).replace("<button>Copy reply</button>", "<button hidden>Copy reply</button>"));
  const hidden = await snapshotMasterDetail(page, [], state);
  expect(hidden.copyReply).toBe(false);
  expect(hidden.diagnostics).toMatch(/Copy reply buttons: 0 visible of 1 in the page \(some exist but are hidden\)/);

  // A visible dropdown of titles with no list is not "list beside thread": options never count as the row.
  await page.setContent(`<div role="tablist"><button role="tab">Reddit 2</button></div><select><option>A fresh thread title</option><option>A drafted thread title</option></select><main id="pane"></main>`);
  const dropdownOnly = await snapshotMasterDetail(page, [], state);
  expect(dropdownOnly.listBesideThread).toBe(false);
  expect(dropdownOnly.diagnostics).toMatch(/0 visible\), clicked failed:/);

  // No drafted thread in the setup: reported as such, not as a timeout.
  const none = await snapshotMasterDetail(page, [], { ...state, drafted: null });
  expect(none.diagnostics).toMatch(/nothing to open.*state\.drafted null/);
});

// @covers FR-01.04
test("launch retry: a missing button is retried after a reload, each miss is reported", async ({ page }) => {
  let loads = 0;
  await page.route("http://launch.test/**", (route) => {
    loads += 1;
    const button = loads >= 2 ? `<button data-testid="cta-launch-in-terminal" onclick="this.remove()">Launch</button>` : "";
    return route.fulfill({ status: 200, contentType: "text/html", body: `<body>${button}</body>` });
  });
  await page.goto("http://launch.test/task");
  const misses: number[] = [];
  await startTaskSession(page, async (attempt) => { misses.push(attempt); }, { first: 800, retry: 800 });
  expect(misses).toEqual([1]);
  expect(loads).toBe(2);
  expect(await page.getByTestId("cta-launch-in-terminal").count()).toBe(0);

  // A button that never comes is reported on every miss and still ends in the usual timeout error.
  await page.route("http://launch.test/**", (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<body></body>" }));
  const all: number[] = [];
  await expect(startTaskSession(page, async (attempt) => { all.push(attempt); }, { first: 300, retry: 300 })).rejects.toThrow(/Timeout/);
  expect(all).toEqual([1, 2, 3]);
});

// @covers FR-01.04
test("task state text never throws", async ({ request }) => {
  expect(await taskStateText(request, "http://127.0.0.1:1", "t1")).toMatch(/state unreadable/);
  expect(await taskStateText(request, "http://127.0.0.1:1", null)).toBe("task id unknown");
});

// @covers FR-01.06
test("no launch button is fine only when the modal already launched the task", () => {
  expect(launchedByModal(false, "state awaiting_external_start")).toBe(true);
  expect(launchedByModal(false, "state active")).toBe(true);
  expect(launchedByModal(true, "state awaiting_external_start")).toBe(false); // button present: click it
  expect(launchedByModal(false, "state failed")).toBe(false);
  expect(launchedByModal(false, "state inactive")).toBe(false); // only the exact words count
  expect(launchedByModal(false, "task not in the list")).toBe(false);
});

// @covers FR-01.06
test("launch watch: started at once, handed over again when stalled, failing fast with state and terminal text", async () => {
  const mk = (states: string[], terminals: string[], canSend = true) => {
    const log: string[] = [];
    let i = 0;
    return {
      log,
      w: {
        readState: async () => states[Math.min(i, states.length - 1)]!,
        readTerminal: async () => terminals[Math.min(i++, terminals.length - 1)]!,
        handOver: async () => { log.push("handover"); return canSend; },
        step: async (t: string) => { log.push(t); },
        sleep: async () => undefined,
        windowMs: 6_000,
      },
    };
  };
  const PS = "PS C:\\app>";
  for (const idle of [`PowerShell 7.4.1\n${PS}`, `Windows PowerShell\nCopyright (C) Microsoft Corporation.\n${PS}`, "Microsoft Windows [Version 10.0.26200]\nC:\\app>", "user@host:~/app$ ", PS, ""]) {
    expect(launchVerdict("state awaiting_external_start", idle)).toBe("stalled"); // banners and prompts are no start
  }
  expect(launchVerdict("state unreadable (boom)", PS)).toBe("stalled");
  expect(launchVerdict("state not reported", "")).toBe("stalled");
  expect(launchVerdict("state awaiting_external_start", `${PS} claude --x\nWelcome`)).toBe("started");
  expect(launchVerdict("state active", PS)).toBe("started");
  expect(launchVerdict("state failed", PS)).toBe("failed");
  expect(launchVerdict("state inactive", "")).toBe("failed");
  expect(launchVerdict("state awaiting_external_start", "claude: command not found")).toBe("stalled");
  await expect(ensureLaunched(mk(["state launch_failed"], [PS]).w)).rejects.toThrow(/failed to launch: state launch_failed/);

  const ok = mk(["state active"], [""]);
  await ensureLaunched(ok.w);
  expect(ok.log).toEqual(["Launch confirmed"]);

  // stalled for the whole first window, then the second hand-over works
  const retry = mk(["state awaiting_external_start", "state awaiting_external_start", "state awaiting_external_start", "state awaiting_external_start", "state active"], [PS]);
  await ensureLaunched(retry.w);
  expect(retry.log.filter((l) => l === "handover")).toHaveLength(1);
  expect(retry.log.at(-1)).toMatch(/after hand-over 1/);

  const never = mk(["state awaiting_external_start"], [PS]);
  await expect(ensureLaunched(never.w)).rejects.toThrow(/did not start after 3 tries: state awaiting_external_start; terminal: PS C:\\app>/);
  expect(never.log.filter((l) => l === "handover")).toHaveLength(2);

  const nothing = mk(["state awaiting_external_start"], [""], false);
  await expect(ensureLaunched(nothing.w)).rejects.toThrow(/no command was captured.*\(empty\)/);
});

// @covers FR-01.06
test("launch capture reads the body inside the route and passes the untouched response on", async () => {
  type Fetch = () => Promise<{ json: () => Promise<unknown> }>;
  const make = async () => {
    let pattern!: RegExp;
    let handler!: (route: never) => Promise<void>;
    const cap = await captureLaunchCommands({ route: async (p: RegExp, h: typeof handler) => { pattern = p; handler = h; } } as never);
    const run = async (method: string, fetch: Fetch) => {
      const seen: string[] = [];
      let passed: unknown;
      const route = { request: () => ({ method: () => method }), fetch, fulfill: async (o: { response: unknown }) => { seen.push("fulfill"); passed = o.response; }, continue: async () => { seen.push("continue"); } };
      await handler(route as never);
      return { seen, passed };
    };
    return { cap, run, pattern };
  };
  const { cap, run, pattern } = await make();
  expect(cap.get()).toBeNull();
  expect(pattern.exec("http://127.0.0.1:3000/api/external/tasks/t-1/launch")).not.toBeNull();
  expect(pattern.exec("http://127.0.0.1:3000/api/external/tasks/t-1")).toBeNull();

  const commands = { powershell: "p", cmd: "c", posix: "x" };
  const res = { json: async () => ({ task: {}, commands }) };
  expect(await run("GET", async () => res)).toEqual({ seen: ["continue"], passed: undefined }); // other verbs untouched
  expect(cap.get()).toBeNull();
  const ok = await run("POST", async () => res);
  expect(ok.seen).toEqual(["fulfill"]);
  expect(ok.passed).toBe(res); // the page sees the very response it asked for
  expect(cap.get()).toEqual(commands);

  const bad = await make();
  const notJson = await bad.run("POST", async () => ({ json: async () => { throw new Error("not json"); } }));
  expect(notJson.seen).toEqual(["fulfill"]); // still delivered, just not captured
  expect(bad.cap.get()).toBeNull();
  expect((await bad.run("POST", async () => { throw new Error("net"); })).seen).toEqual(["continue"]);
});
