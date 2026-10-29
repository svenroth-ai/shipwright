// Capture screenshots for the Test-phase screenshot check (screenshot_check.py).
//
// node screenshot_capture.mjs --project <dir> --jobs <jobs.json> [--width 1280 --height 800]
//
// jobs.json: [{"url": "http://localhost:3000/login", "out": "<abs png path>", "steps": [{"click": "#tab-queue"}]}, ...]
// optional "steps" bring a served page into a state before the shot: {"click": sel} | {"fill": [sel, text]} | {"wait_for": sel}.
// Nothing is injected into the page (no style/script tag): the app's own Content-Security-Policy cannot block the capture.
// url may be http(s):// (the built app) or file:// (the approved design screens). Every shot is the
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
  for (const job of jobs) {
    // One context per job: a step that saves state (localStorage, cookies, a submitted form) never reaches the next screen.
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1, reducedMotion: "reduce" });
    const page = await context.newPage();
    try {
      const response = await page.goto(job.url, { waitUntil: "load", timeout: 30000 });
      if (response && !response.ok()) throw new Error(`HTTP ${response.status()} for ${job.url}`);
      await page.waitForLoadState("networkidle", { timeout: 10000 }).catch(() => {});
      // Steps run in order, 10 s each; one that cannot run fails THIS job (never a silent shot of the initial state).
      for (const [i, step] of (job.steps || []).entries()) {
        try {
          if (step.click) await page.click(step.click, { timeout: 10000 });
          else if (step.fill) await page.fill(step.fill[0], String(step.fill[1]), { timeout: 10000 });
          else if (step.wait_for) await page.waitForSelector(step.wait_for, { timeout: 10000 });
        } catch (e) {
          throw new Error(`step ${i + 1} ${JSON.stringify(step)} failed: ${String(e.message || e).split(String.fromCharCode(10))[0].slice(0, 160)}`);
        }
        await page.waitForLoadState("networkidle", { timeout: 5000 }).catch(() => {});
      }
      await page.evaluate(() => document.fonts.ready).catch(() => {});
      if (job.steps && job.steps.length) {  // no hover or focus ring left by the steps (the design screen has none)
        await page.mouse.move(0, 0);
        await page.evaluate(() => document.activeElement && document.activeElement.blur && document.activeElement.blur()).catch(() => {});
      }
      // Playwright's own switches, not an injected <style>: an inline style is blocked by a page CSP (style-src without 'unsafe-inline').
      await page.screenshot({ path: job.out, fullPage: false, animations: "disabled", caret: "hide" });
      result.captured.push(job.out);
    } catch (e) {
      result.ok = false;
      result.errors.push({ out: job.out, error: String(e.message || e).slice(0, 300) });
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
console.log(JSON.stringify(result));
