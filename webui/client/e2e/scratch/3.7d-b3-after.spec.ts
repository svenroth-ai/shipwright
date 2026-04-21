/**
 * Iterate 3.7d-b3 — Inbox AFTER verification.
 *
 * Asserts the read-only rebuild of the Inbox:
 *   - No `<textarea>` / freetext input on the page.
 *   - Option chips are not buttons (no clickable answers).
 *   - No "Launch" button on Inbox cards.
 *   - Resume button present and does NOT navigate (stops propagation).
 *   - Clicking the card body navigates to /tasks/<taskId>.
 *
 * Requires seed-inbox-fixtures.ts to have been run so at least one Ask item
 * is rendered.
 */
import { test, expect } from "@playwright/test";

test.describe("3.7d-b3 AFTER", () => {
  test("Inbox is read-only with Resume-only CTA + card click-through", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

    await page.goto("/inbox", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(2000);

    // Full-page AFTER screenshot.
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b3-after-inbox.png",
      fullPage: true,
    });

    // 1) No textarea anywhere on the page.
    const textareaCount = await page.locator("textarea").count();
    expect(textareaCount).toBe(0);

    // 2) No freetext input (v2 testid gone).
    await expect(page.getByTestId("inbox-freetext-input")).toHaveCount(0);
    await expect(page.getByTestId("inbox-freetext-send")).toHaveCount(0);

    // 3) Find the first inbox card.
    const cards = page.locator("[data-testid^='inbox-card-']");
    const cardCount = await cards.count();
    expect(cardCount).toBeGreaterThan(0);
    const firstCard = cards.first();

    // Read the toolUseId suffix so we can target its Resume button.
    const firstTestId = await firstCard.getAttribute("data-testid");
    expect(firstTestId).toBeTruthy();
    const tuId = (firstTestId ?? "").replace("inbox-card-", "");
    expect(tuId.length).toBeGreaterThan(0);

    // 4) The card has role=button + tabIndex=0 (a11y contract).
    await expect(firstCard).toHaveAttribute("role", "button");
    await expect(firstCard).toHaveAttribute("tabindex", "0");

    // 5) No "Launch" button on this card — only Resume.
    await expect(
      page.getByTestId(`inbox-launch-${tuId}`),
    ).toHaveCount(0);
    const resumeBtn = page.getByTestId(`inbox-resume-${tuId}`);
    await expect(resumeBtn).toBeVisible();
    await expect(resumeBtn).toContainText(/Resume|Preparing|Copied/);

    // 6) Option chips (if any) are NOT `<button>` tags.
    const chips = firstCard.locator("[data-testid^='inbox-option-chip-']");
    const chipCount = await chips.count();
    for (let i = 0; i < chipCount; i++) {
      const tag = await chips.nth(i).evaluate((el) => el.tagName.toLowerCase());
      expect(tag).not.toBe("button");
      // Also: no onclick attribute on the chip.
      const onclick = await chips.nth(i).getAttribute("onclick");
      expect(onclick).toBeNull();
    }

    // 7) Grant clipboard permissions for the Resume click.
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);

    // 8) Click the Resume button. URL must NOT navigate to /tasks/*.
    await resumeBtn.click();
    await page.waitForTimeout(400);
    expect(page.url()).toContain("/inbox");

    // Screenshot of the Resume-clicked state.
    await page.screenshot({
      path: "e2e/screenshots/3.7d-b3-after-resume-clicked.png",
      fullPage: false,
    });

    // 9) Now click the card body (not the Resume button). The easiest way
    // to hit the body without hitting the button is to click near the
    // top-left of the card.
    const box = await firstCard.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      await page.mouse.click(box.x + 40, box.y + 30);
    }
    await page.waitForTimeout(500);
    expect(page.url()).toMatch(/\/tasks\//);

    // 10) Console-error hygiene.
    if (consoleErrors.length > 0) {
      console.log("AFTER console errors:", consoleErrors);
    }
    // Fail soft on console errors — b1/b2 may have unrelated errors in
    // parallel surfaces; only fail if the errors came from our surface.
    const ourErrors = consoleErrors.filter(
      (e) => /Inbox|InboxPage|InboxCard|InboxResume/.test(e),
    );
    expect(ourErrors).toEqual([]);
  });
});
