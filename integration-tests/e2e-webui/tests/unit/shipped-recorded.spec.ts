// No model: S05 of the source-adapter variant also proves the build kept the recorded answers the package ships:
// seed/recorded/ of the built project equals the package's files byte for byte, with no file or item added or removed.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { Checklist, parseChecklist } from "../../src/checklist.js";
import { REAL_FIXTURE_NAME } from "../../src/fixture.js";
import { checkSelfContainedWithAdapter, compareShippedRecorded, findRecorded, SHIPPED_RECORDED_DIR } from "../../src/project-checks-adapter.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const real = path.join(repo, "integration-tests", "fixtures", REAL_FIXTURE_NAME);
const list = () => new Checklist(parseChecklist(fs.readFileSync(path.join(repo, "integration-tests", "fixtures", `${REAL_FIXTURE_NAME}-expected-result.md`), "utf8")));
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-shipped-"));
const write = (root: string, rel: string, text: string) => {
  fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
  fs.writeFileSync(path.join(root, rel), text);
};

const shippedProject = () => {
  const root = tmp();
  for (const f of ["syften.json", "apify_linkedin.json"]) write(root, `seed/recorded/${f}`, fs.readFileSync(path.join(SHIPPED_RECORDED_DIR, f), "utf8"));
  write(root, "backend/sources/__init__.py", "def fetch_items(s):\n    return []\n");
  write(root, "backend/server.py", "from sources import fetch_items\n");
  return root;
};
const s05 = (root: string) => {
  const l = list();
  checkSelfContainedWithAdapter(root, l);
  const item = l.items.find((i) => i.id === "S05")!;
  return { verdict: item.verdict, evidence: item.evidence };
};

// @covers FR-01.06
test("S05 variant: the reference is the package in the repo, and byte-identical shipped files with nothing added pass", () => {
  expect(path.resolve(SHIPPED_RECORDED_DIR)).toBe(path.join(real, "seed", "recorded"));
  const root = shippedProject();
  try {
    expect(compareShippedRecorded(root)).toEqual([]);
    const r = s05(root);
    expect(r.verdict, r.evidence).toBe("pass");
    expect(r.evidence).toMatch(/byte-identical to the shipped recorded answers, nothing added/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// @covers FR-01.06
test("S05 variant: a changed byte, a missing file, an extra file and an extra item each fail, and the evidence names the file", () => {
  const root = shippedProject();
  const dir = path.join(root, "seed", "recorded");
  const file = path.join(dir, "syften.json");
  try {
    const original = fs.readFileSync(file);
    const shippedItems = (JSON.parse(original.toString("utf8")) as unknown[]).length;

    // One changed byte that keeps the data valid (first letter of a title), so only the byte comparison can see it.
    const changed = Buffer.from(original);
    const marker = changed.indexOf('"title": "') >= 0 ? '"title": "' : '"title":"';
    expect(changed.indexOf(marker), "the title marker exists in the shipped file").toBeGreaterThan(-1);
    const at = changed.indexOf(marker) + marker.length;
    changed[at] = changed[at] === 0x58 ? 0x59 : 0x58;
    fs.writeFileSync(file, changed);
    expect(findRecorded(root).total, "still valid data").toBe(12);
    let r = s05(root);
    expect(r.verdict).toBe("fail");
    expect(r.evidence).toMatch(/seed\/recorded\/syften\.json changed/);
    fs.writeFileSync(file, original);

    // Same content with the other line ending is still not the shipped file; the evidence says why.
    const eol = original.includes("\r\n") ? original.toString("latin1").replace(/\r\n/g, "\n") : original.toString("latin1").replace(/\n/g, "\r\n");
    fs.writeFileSync(file, Buffer.from(eol, "latin1"));
    r = s05(root);
    expect(r.verdict).toBe("fail");
    expect(r.evidence).toMatch(/seed\/recorded\/syften\.json changed \(line endings only/);
    fs.writeFileSync(file, original);

    // A missing file.
    fs.rmSync(path.join(dir, "apify_linkedin.json"));
    r = s05(root);
    expect(r.verdict).toBe("fail");
    expect(r.evidence).toMatch(/seed\/recorded\/apify_linkedin\.json missing/);
    fs.copyFileSync(path.join(SHIPPED_RECORDED_DIR, "apify_linkedin.json"), path.join(dir, "apify_linkedin.json"));
    expect(s05(root).verdict).toBe("pass");

    // An extra file next to the shipped ones, and one in a subfolder.
    write(root, "seed/recorded/extra.json", "[]");
    r = s05(root);
    expect(r.verdict).toBe("fail");
    expect(r.evidence).toMatch(/seed\/recorded\/extra\.json extra file/);
    fs.rmSync(path.join(dir, "extra.json"));
    write(root, "seed/recorded/more/own.json", "[]");
    expect(s05(root).evidence).toMatch(/seed\/recorded\/more\/own\.json extra file/);
    fs.rmSync(path.join(dir, "more"), { recursive: true });
    expect(s05(root).verdict).toBe("pass");

    // An extra, valid item inside a shipped file: the minimums still hold, but the file is no longer the shipped one.
    const items = JSON.parse(original.toString("utf8")) as unknown[];
    fs.writeFileSync(file, JSON.stringify([...items, items[0]], null, 2));
    expect(findRecorded(root).total).toBe(13);
    r = s05(root);
    expect(r.verdict).toBe("fail");
    expect(r.evidence).toContain(`seed/recorded/syften.json changed (${shippedItems + 1} items, the package ships ${shippedItems})`);

    // A reference folder with no files is a harness fault, never a pass.
    fs.writeFileSync(file, original);
    expect(compareShippedRecorded(root, path.join(root, "no-such-dir"))[0]).toMatch(/ships no recorded answers/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

