/**
 * Browser Verify — Lightweight visual check for Shipwright.
 *
 * Navigates to a URL, waits for network idle, captures a screenshot,
 * collects console errors, and writes a JSON result file.
 *
 * Usage:
 *   npx tsx e2e/browser-verify.ts [--url http://localhost:3000] [--output browser-verify-result.json]
 *
 * Output JSON:
 *   {
 *     "success": true/false,
 *     "url": "http://localhost:3000",
 *     "screenshot": "e2e/screenshots/browser-verify.png",
 *     "console_errors": ["Error: ..."],
 *     "title": "My App",
 *     "dom_snippet": "<html>...</html>"
 *   }
 */

import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';

const args = process.argv.slice(2);
const urlIndex = args.indexOf('--url');
const outputIndex = args.indexOf('--output');
const url = urlIndex !== -1 ? args[urlIndex + 1] : 'http://localhost:3000';
const outputPath = outputIndex !== -1 ? args[outputIndex + 1] : 'browser-verify-result.json';
const screenshotDir = resolve('e2e', 'screenshots');
const screenshotPath = resolve(screenshotDir, 'browser-verify.png');

interface VerifyResult {
  success: boolean;
  url: string;
  screenshot: string;
  console_errors: string[];
  title: string;
  dom_snippet: string;
  error?: string;
}

async function verify(): Promise<VerifyResult> {
  const consoleErrors: string[] = [];

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  // Collect console errors
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  // Collect uncaught exceptions
  page.on('pageerror', (err) => {
    consoleErrors.push(`Uncaught: ${err.message}`);
  });

  try {
    // Navigate and wait for network idle
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

    // Get page title
    const title = await page.title();

    // Capture screenshot
    mkdirSync(screenshotDir, { recursive: true });
    await page.screenshot({ path: screenshotPath, fullPage: true });

    // Get DOM snippet (truncated to 5000 chars for context window)
    const html = await page.content();
    const domSnippet = html.length > 5000 ? html.substring(0, 5000) + '\n<!-- truncated -->' : html;

    await browser.close();

    return {
      success: consoleErrors.length === 0,
      url,
      screenshot: screenshotPath,
      console_errors: consoleErrors,
      title,
      dom_snippet: domSnippet,
    };
  } catch (err) {
    await browser.close();
    return {
      success: false,
      url,
      screenshot: '',
      console_errors: consoleErrors,
      title: '',
      dom_snippet: '',
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

verify().then((result) => {
  mkdirSync(dirname(resolve(outputPath)), { recursive: true });
  writeFileSync(resolve(outputPath), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.success ? 0 : 1);
});
