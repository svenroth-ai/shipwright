import { test, expect } from '@playwright/test';

const RUNNING_TASK_ID = '7f1815f3-e319-4667-ad67-6a4d7a6c9bf8';

/**
 * Iterate 2026-04-18 modelswitch-spawn-ux — E2E DOM contract for the
 * mid-task model switch flow.
 *
 * Runs against the live webui + a known running task (task 7f1815f3 on
 * the ToDo Demo project) that already has a `system/init` with model
 * label present.
 *
 * Gate checks:
 *   1. ModelSelector trigger renders with a known label and responds to
 *      clicks without throwing.
 *   2. The pending-target visual (target model label + spinner) appears
 *      during a simulated switch AND the trigger becomes disabled. We
 *      mock the /mode POST to never resolve so the pending state is
 *      observable.
 *   3. When the mock responds with 409, an inline error banner
 *      (`model-switch-error`) appears. This proves the error-surfacing
 *      path wired in Sub-iterate B of this fix.
 */

test.describe('Model switch UX (iterate modelswitch-spawn-ux)', () => {
  test('pending-target visual appears on click and persists while respawn is in flight', async ({
    page,
  }) => {
    // Hold the /mode request open so the pending-target visual is
    // observable in the DOM. Matches the live 1-2s respawn window.
    let releaseHold!: () => void;
    const held = new Promise<void>((resolve) => {
      releaseHold = resolve;
    });
    await page.route('**/api/projects/*/tasks/*/mode', async (route) => {
      await held;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { taskId: RUNNING_TASK_ID, model: 'claude-opus-4-6', status: 'running' },
        }),
      });
    });

    await page.goto(`/tasks/${RUNNING_TASK_ID}`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByTestId('chat-panel')).toBeVisible();

    const trigger = page.getByTestId('model-selector-trigger');
    await expect(trigger).toBeVisible();

    await trigger.click();
    // Pick a model different from the current label. The live task is
    // on Opus 4.7 per capture, so switching to 4.6 is a real change.
    const opus46 = page.getByRole('button', { name: /Opus 4\.6/ }).first();
    await opus46.click();

    // Pending-target attribute exposes the chosen id.
    await expect(trigger).toHaveAttribute('data-pending-target', 'claude-opus-4-6');
    await expect(page.getByTestId('model-switching-spinner')).toBeVisible();
    await expect(trigger).toBeDisabled();

    releaseHold();
  });

  test('server 409 surfaces as model-switch-error banner and clears pending state', async ({
    page,
  }) => {
    await page.route('**/api/projects/*/tasks/*/mode', async (route) => {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Answer the pending question before switching mode' }),
      });
    });

    await page.goto(`/tasks/${RUNNING_TASK_ID}`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByTestId('chat-panel')).toBeVisible();

    const trigger = page.getByTestId('model-selector-trigger');
    await trigger.click();
    const opus46 = page.getByRole('button', { name: /Opus 4\.6/ }).first();
    await opus46.click();

    await expect(page.getByTestId('model-switch-error')).toBeVisible();
    await expect(page.getByTestId('model-switch-error')).toContainText(/pending question/i);
    // Pending target cleared on error so the user can retry.
    await expect(trigger).not.toHaveAttribute('data-pending-target', 'claude-opus-4-6');
  });

  test('ChatPanel renders the chat-spawn-indicator when loading into a task mid-flight', async ({
    page,
  }) => {
    // Hold the task query so the client treats this as the "fresh mount"
    // case where task is undefined + systemInit unknown = awaitingInit.
    await page.route(`**/api/projects/*/tasks/${RUNNING_TASK_ID}`, async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      // Fulfill with 404 to simulate the fresh-task race (task exists on
      // CLI side but not yet persisted to server cache).
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Task not found' }),
      });
    });
    // Empty chat history so no system/init hydrates.
    await page.route(`**/api/projects/*/chat/${RUNNING_TASK_ID}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ data: [] }),
      });
    });

    await page.goto(`/tasks/${RUNNING_TASK_ID}`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.getByTestId('chat-spawn-indicator')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('Starting Claude…')).toBeVisible();
  });
});
