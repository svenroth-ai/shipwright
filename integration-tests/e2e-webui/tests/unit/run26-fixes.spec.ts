// Run 26 check defects: a Python f-string slice is code, not a host.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { findExternalUse } from "../../src/project-checks.js";

// @covers FR-01.06
test("B31: an f-string cut at its slice colon names no host, a real host next to it still does", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "run26-"));
  try {
    fs.mkdirSync(path.join(root, "backend"), { recursive: true });
    fs.writeFileSync(path.join(root, "backend", "links.py"), 'def f(value, scheme):\n    return f"https://{value[scheme.end():]}"\n');
    expect(findExternalUse(root, ["backend/links.py"])).toEqual([]);
    fs.writeFileSync(path.join(root, "backend", "leak.py"), 'u = "https://api.apify.com/v2"\n');
    expect(findExternalUse(root, ["backend/leak.py"]).length).toBe(1);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
