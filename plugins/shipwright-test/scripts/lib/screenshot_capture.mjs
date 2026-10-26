// Capture screenshots for the Test-phase screenshot check (screenshot_check.py).
//
// node screenshot_capture.mjs --project <dir> --jobs <jobs.json> [--width 1280 --height 800]
//
// jobs.json: [{"url": "http://localhost:3000/login", "out": "<abs png path>"}, ...]
// url may be http(s):// (the built app) or file:// (an approved mockup). Every shot is the
// FIXED viewport (no full-page), animations off, so both sides have the same pixel size.
// `playwright` is resolved from the PROJECT (where playwright_setup installed it), not from here.
// stdout: one JSON object {"ok": bool, "captured": [...], "errors": [{"out","error"}]}.
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const project = resolve(arg("project", "."));
const jobs = JSON.parse(readFileSync(arg("jobs"), "utf-8"));
const viewport = { width: Number(arg("width", "1280")), height: Number(arg("height", "800")) };
const result = { ok: true, captured: [], errors: [] };

let chromium;
// Playwright lives where playwright_setup.py installed it: the project root, or a service dir in a multi-service repo.
const searchDirs = [project, ...process.argv.flatMap((a, i, all) => (a === "--search" && all[i + 1] ? [resolve(all[i + 1])] : []))];
const failures = [];
for (const dir of searchDirs) {
  try {
    const req = createRequire(join(dir, "package.json"));
    let pw;
    try { pw = req("playwright"); } catch { pw = req("@playwright/test"); }
    chromium = pw.chromium;
    break;
  } catch (e) {
    failures.push(`${dir}: ${String(e.message).split(String.fromCharCode(10))[0]}`);
  }
}
if (!chromium) {
  console.log(JSON.stringify({ ok: false, captured: [], errors: [{ out: "", error: `playwright not resolvable from ${failures.join("; ")}` }] }));
  process.exit(0);
}

let browser;
try {
  browser = await chromium.launch();
} catch (e) {
  console.log(JSON.stringify({ ok: false, captured: [], errors: [{ out: "", error: `browser did not launch (run playwright_setup.py): ${String(e.message || e).split(/\r?\n/)[0].slice(0, 200)}` }] }));
  process.exit(0);
}
try {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: "reduce" });
  for (const job of jobs) {
    const page = await context.newPage();
    try {
      const response = await page.goto(job.url, { waitUntil: "load", timeout: 30000 });
      if (response && !response.ok()) throw new Error(`HTTP ${response.status()} for ${job.url}`);
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      await page.evaluate(() => document.fonts.ready).catch(() => {});
      await page.addStyleTag({ content: "*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}" });
      await page.screenshot({ path: job.out, fullPage: false });
      result.captured.push(job.out);
    } catch (e) {
      result.ok = false;
      result.errors.push({ out: job.out, error: String(e.message || e).slice(0, 300) });
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify(result));
