import { test, expect } from '@playwright/test';

const RUNNING_TASK_ID = '7f1815f3-e319-4667-ad67-6a4d7a6c9bf8';

test.describe('PoC assistant-ui route', () => {
  test('renders without fatal error and shows messages', async ({ page }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => {
      pageErrors.push(err.message);
    });

    await page.goto(`/poc-chat/${RUNNING_TASK_ID}`);
    // SSE keeps network active — wait for DOM + a beat so React renders,
    // don't wait for networkidle (it never happens with live streams).
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2500);

    // Screenshot for visual inspection
    await page.screenshot({
      path: 'e2e/.poc-screenshots/poc-route.png',
      fullPage: true,
    });

    // The PoC route should mount without page errors
    expect(pageErrors).toEqual([]);

    // The outer panel must be present
    await expect(page.getByTestId('poc-chat-panel')).toBeVisible();

    // Check console errors (allow React Query retry warnings but fail on TypeError / ReferenceError / etc)
    const fatalErrors = consoleErrors.filter((e) =>
      /TypeError|ReferenceError|Cannot read|Invalid hook|is not a function/i.test(e),
    );
    expect(fatalErrors, `fatal console errors: ${fatalErrors.join('\n')}`).toEqual([]);
  });

  test('production ChatPanel still works for side-by-side comparison', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await page.goto(`/tasks/${RUNNING_TASK_ID}`);
    // SSE keeps network active — wait for DOM + a beat so React renders,
    // don't wait for networkidle (it never happens with live streams).
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2500);

    await page.screenshot({
      path: 'e2e/.poc-screenshots/production-route.png',
      fullPage: true,
    });

    expect(pageErrors).toEqual([]);
    await expect(page.getByTestId('chat-panel')).toBeVisible();
  });
});
