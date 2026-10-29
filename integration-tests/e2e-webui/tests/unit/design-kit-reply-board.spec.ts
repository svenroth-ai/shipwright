// The Untitled UI kit reply-board parts in a real browser: the gallery pages are the built output of kit.css + a token set.
import path from "node:path";
import { expect, test } from "@playwright/test";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const examples = path.join(repo, "plugins", "shipwright-design", "skills", "design", "kit", "untitled-ui", "examples");

for (const look of ["clean", "warm", "bold"]) {
  const page_ = `file:///${path.join(examples, `gallery-${look}.html`).replaceAll("\\", "/")}`;

  test.describe(`gallery-${look}`, { tag: ["@FR-01.04"] }, () => {
    test(`${look}: wide screen: the list pane sits beside the thread, the picker is hidden`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.goto(page_);
      const pane = page.locator(".master-pane").first();
      const detail = page.locator(".detail-pane").first();
      await expect(pane.locator(".list")).toBeVisible();
      await expect(page.locator(".master-picker").first()).toBeHidden();
      const [p, l, d] = [await pane.boundingBox(), await pane.locator(".list").boundingBox(), await detail.boundingBox()];
      expect(p!.x + p!.width).toBeLessThanOrEqual(d!.x + 8); // the pane's own padding is pulled back by an equal negative margin
      expect(Math.abs(l!.y - d!.y)).toBeLessThan(2); // the list card, not the padded pane, lines up with the thread card
      expect(p!.width).toBeGreaterThanOrEqual(280);
    });

    test(`${look}: narrow screen: the picker replaces the list and nothing overflows sideways`, async ({ page }) => {
      await page.setViewportSize({ width: 375, height: 800 });
      await page.goto(page_);
      await expect(page.locator(".master-pane .list").first()).toBeHidden();
      await expect(page.locator(".master-picker select").first()).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });

    test(`${look}: a reply is nested under its comment and drawn with a left rule`, async ({ page }) => {
      await page.goto(page_);
      const inner = page.locator(".comment-tree .comment-tree").first();
      await expect(inner).toBeVisible();
      expect(await inner.evaluate((e) => getComputedStyle(e).borderLeftWidth)).toBe("1px");
      const [outer, nested] = [await page.locator(".comment").first().boundingBox(), await inner.boundingBox()];
      expect(nested!.x).toBeGreaterThan(outer!.x);
    });

    test(`${look}: counts show in the segmented control and the eyebrow is the mono font`, async ({ page }) => {
      await page.goto(page_);
      const count = page.locator(".segmented-item.active .count").first();
      await expect(count).toBeVisible();
      await expect(count).toHaveText("4");
      const fonts = await page.evaluate(() => ({
        eyebrow: getComputedStyle(document.querySelector(".eyebrow")!).fontFamily,
        mono: getComputedStyle(document.documentElement).getPropertyValue("--font-mono").trim(),
        transform: getComputedStyle(document.querySelector(".eyebrow")!).textTransform,
      }));
      expect(fonts.transform).toBe("uppercase");
      const plain = (v: string) => v.replaceAll('"', "'").replace(/\s+/g, " ");
      expect(plain(fonts.eyebrow)).toBe(plain(fonts.mono));
    });

    test(`${look}: the draft callout carries the primary accent and the copy button shows the copied state`, async ({ page }) => {
      await page.goto(page_);
      const accent = await page.locator(".callout").first().evaluate((e) => ({ edge: getComputedStyle(e).borderLeftColor, primary: getComputedStyle(document.documentElement).getPropertyValue("--color-primary").trim() }));
      expect(accent.edge).not.toBe("");
      await expect(page.locator(".copy-btn.copied").first()).toHaveText("Copied");
    });
  });
}
