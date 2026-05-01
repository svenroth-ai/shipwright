#!/usr/bin/env node
// Lighthouse runner for /shipwright-test performance budget check.
//
// Invoked by performance_check.py as:
//   node lighthouse-runner.mjs <url>
// with cwd = project_root, so `playwright` resolves from the project's
// node_modules (the project already has it for E2E). Lighthouse itself is
// pinned in this directory's package.json; the Python wrapper lazy-installs
// node_modules in the plugin's perf/ subdir on first invocation.
//
// Output: a Lighthouse JSON LHR document on stdout. On failure: a JSON
// object {"error": "..."} on stdout AND a non-zero exit code.

import { createRequire } from 'node:module';
import { createServer } from 'node:net';

const url = process.argv[2];
if (!url) {
  process.stdout.write(JSON.stringify({ error: 'no URL argument' }));
  process.exit(2);
}

// Pre-allocate a free TCP port to use as --remote-debugging-port. Doing this
// in a throwaway TCP server (then closing it before Chromium binds) avoids:
//  - port collisions on a fixed 9222
//  - reaching into Playwright internals to discover the bound port
//  - API churn between Playwright versions (browser.wsEndpoint() shape changed)
async function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = createServer();
    srv.unref();
    srv.on('error', reject);
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
  });
}

let chromium;
let lighthouse;

try {
  // playwright resolved from cwd (the user's project). chromium is the
  // Playwright-bundled Chromium — same one that runs E2E.
  const projectRequire = createRequire(`${process.cwd()}/`);
  ({ chromium } = projectRequire('playwright'));
} catch (err) {
  process.stdout.write(JSON.stringify({
    error: `playwright not found in project (${process.cwd()}): ${err.message}`,
  }));
  process.exit(3);
}

try {
  // lighthouse resolved from THIS script's package.json (shipwright-test plugin),
  // not the user project — that's the version pin guarantee.
  lighthouse = (await import('lighthouse')).default;
} catch (err) {
  process.stdout.write(JSON.stringify({
    error: `lighthouse not installed in plugin perf/node_modules: ${err.message}`,
  }));
  process.exit(4);
}

let browser;
try {
  const port = await getFreePort();
  // Sandbox stays ON by default — auditing arbitrary http(s) URLs without
  // sandbox isolation would weaken Chromium's security model. CI/Docker
  // environments that need --no-sandbox can set
  // SHIPWRIGHT_PERF_NO_SANDBOX=1 explicitly.
  const launchArgs = [`--remote-debugging-port=${port}`];
  if (process.env.SHIPWRIGHT_PERF_NO_SANDBOX === '1') {
    launchArgs.push('--no-sandbox');
  }
  browser = await chromium.launch({ args: launchArgs });

  const result = await lighthouse(url, {
    port,
    output: 'json',
    logLevel: 'error',
    onlyCategories: ['performance'],
  });

  if (!result || !result.lhr) {
    throw new Error('lighthouse returned no LHR');
  }

  process.stdout.write(JSON.stringify(result.lhr));
} catch (err) {
  process.stdout.write(JSON.stringify({
    error: `lighthouse run failed: ${err.message}`,
  }));
  process.exitCode = 5;
} finally {
  if (browser) {
    try { await browser.close(); } catch { /* swallow — best-effort cleanup */ }
  }
}
