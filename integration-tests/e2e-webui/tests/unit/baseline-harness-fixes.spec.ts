// No model: regressions of the first real run of the baseline fixture (run 20). The checks were wrong, not the built app.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { listRow, visibleText } from "../../src/baseline/board-ui.js";
import { checkAdapterOnly, checkStoreOnly } from "../../src/baseline/checks-static.js";
import { Probe } from "../../src/baseline/probe.js";

const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};
const verdict = (fn: (p: Probe) => void) => { const p = new Probe(); fn(p); return p.verdict(); };

// @covers FR-01.06
test("a thread's list row is found among hidden picker options, and hidden banner text does not count", async ({ page }) => {
  await page.setContent(`<select hidden><option>Plan the rollout</option></select>
    <a data-k="reddit:1" href="#x" onclick="document.title='clicked'">Plan the rollout</a>
    <div id="reload" hidden><span>Claude updated the board</span></div>`);
  await listRow(page, { key: "reddit:1", post: { title: "Plan the rollout" } }).click({ timeout: 2000 });
  expect(await page.title()).toBe("clicked");
  await listRow(page, { post: { title: "Plan the rollout" } }).click({ timeout: 2000 }); // no key: found by its text among the rows
  expect(await visibleText(page, /Claude updated the board/i).count()).toBe(0);
  await page.evaluate(() => { (document.getElementById("reload") as HTMLElement).hidden = false; });
  expect(await visibleText(page, /Claude updated the board/i).count()).toBe(1);
});

// @covers FR-01.06
test("B30: the brief's own 409 text 'already in lessons.md' is not a file access; a real file access still fails", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-baseline-unit-"));
  write(root, "backend/store/base.py", "class Store:\n    pass\n");
  write(root, "tests/test_store.py", "class MemStore: pass\nclass JsonStore: pass\n");
  write(root, "backend/rules/lessons.py", 'DUPLICATE = "this lesson is already in lessons.md"\n');
  expect(verdict((p) => checkStoreOnly(root, p))).toMatchObject({ pass: true });
  write(root, "backend/rules/lessons.py", 'DUPLICATE = "this lesson is already in lessons.md"\nPATH = "lessons.md"\n');
  expect(verdict((p) => checkStoreOnly(root, p)).evidence).toContain("backend/rules/lessons.py");
  // a differently worded message is not the brief's sentence and stays red
  write(root, "backend/rules/lessons.py", 'DUPLICATE = "lessons.md already holds this"\n');
  expect(verdict((p) => checkStoreOnly(root, p)).evidence).toContain("backend/rules/lessons.py");
  // the sentence next to a real access in another file also stays red
  write(root, "backend/rules/lessons.py", 'DUPLICATE = "this lesson is already in lessons.md"\n');
  write(root, "backend/api/x.py", "open('events.jsonl')\n");
  expect(verdict((p) => checkStoreOnly(root, p)).evidence).toContain("backend/api/x.py");
});

// @covers FR-01.06
test("B31: the default hosts may sit in a shared settings file of the adapter package, but must exist there", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-baseline-unit-"));
  for (const n of ["syften", "apify", "hn_algolia"]) write(root, `backend/services/${n}.py`, "from backend.services.http import request_json\n");
  write(root, "backend/services/settings.py", 'D = {"a": "https://syften.com/api/0.1/", "b": "https://api.apify.com/v2", "c": "https://hn.algolia.com/api/v1"}\n');
  write(root, "board/board.js", "fetch('/api/board');\n");
  expect(verdict((p) => checkAdapterOnly(root, p))).toMatchObject({ pass: true });
  write(root, "backend/services/settings.py", 'D = {"a": "https://syften.com/api/0.1/"}\n');
  expect(verdict((p) => checkAdapterOnly(root, p)).evidence).toContain("default host of Apify");
  // a service host outside the adapter package stays red
  write(root, "backend/services/settings.py", 'D = {"a": "https://syften.com/api/0.1/", "b": "https://api.apify.com/v2", "c": "https://hn.algolia.com/api/v1"}\n');
  write(root, "backend/rules/fetch.py", 'U = "https://api.apify.com/v2/x"\n');
  expect(verdict((p) => checkAdapterOnly(root, p)).pass).toBe(false);
});
