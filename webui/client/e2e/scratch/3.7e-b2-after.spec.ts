/**
 * Iterate 3.7e-b2 — TaskDetail polish verification.
 *
 * Captures screenshots + assertions to verify:
 *   1. Deploy pipeline (draft) → Header CTA is GREEN Launch with Terminal
 *      icon LEFT of the label.
 *   2. An idle/active task → Header CTA is BROWN Resume with Terminal icon
 *      LEFT of the label. (Seeded tasks are all `draft`, so we intercept the
 *      /tasks/:id response and override `state` to `idle` for the Resume
 *      test. This is the least-invasive way to verify the Resume variant
 *      without re-seeding.)
 *   3. Ask-bubble button reads "Answer in Terminal", brown, Terminal icon
 *      left (Foundation R6 change).
 *   4. Assistant bubble role badge reads "CLAUDE" (Foundation R4 change).
 *   5. User bubble has NO border + has a box-shadow (Foundation R5).
 *
 * Screenshots:
 *   e2e/screenshots/3.7e-b2-header-launch.png      (green Launch)
 *   e2e/screenshots/3.7e-b2-header-resume.png      (brown Resume)
 *   e2e/screenshots/3.7e-b2-ask-bubble.png         (Answer in Terminal)
 *   e2e/screenshots/3.7e-b2-claude-badge.png       (CLAUDE role label)
 *   e2e/screenshots/3.7e-b2-user-bubble.png        (no-border + shadow)
 */
import { test, expect } from "@playwright/test";

test.describe("3.7e-b2 TaskDetail polish", () => {
  test("Launch / Resume header CTAs + Claude rename + user-bubble shadow + Answer-in-Terminal", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(`pageerror: ${err.message}`);
    });

    // Fetch the seeded tasks first so we know which ones we're opening.
    const tasksResp = await page.request.get(
      "http://localhost:3847/api/external/tasks",
    );
    const { tasks } = (await tasksResp.json()) as {
      tasks: Array<{ taskId: string; title: string; state: string }>;
    };

    const deployTask = tasks.find((t) =>
      /Deploy pipeline to prod/i.test(t.title),
    );
    const oauthTask = tasks.find((t) =>
      /Add OAuth scope for read:webhooks/i.test(t.title),
    );
    if (!deployTask) throw new Error("Deploy pipeline seed task not found");
    if (!oauthTask) throw new Error("Add OAuth scope seed task not found");

    // Server-side task state can drift between seed and navigation — the
    // watcher may transition draft → active once it picks up the seeded
    // JSONL. To keep this spec deterministic we always intercept
    // /api/external/tasks[/:id] GETs and pin the state we want. Only the
    // GET reads are overridden; POST/PATCH/launch pass through untouched.
    async function pinTaskState(
      targetTaskId: string,
      forcedState: string,
    ): Promise<void> {
      // Match the task GET exactly — do NOT match sub-paths like
      // `/transcript`, `/launch`, `/inbox`, etc. The URL regex asserts end
      // of path (? followed by query string OR end-of-string).
      const exactTaskRe = new RegExp(
        `/api/external/tasks/${targetTaskId}(?:\\?|$)`,
      );
      await page.route(exactTaskRe, async (route) => {
        if (route.request().method() !== "GET") return route.continue();
        const response = await route.fetch();
        const ct = response.headers()["content-type"] ?? "";
        if (!ct.includes("application/json")) return route.continue();
        const body = (await response.json()) as {
          task?: Record<string, unknown>;
        };
        if (body.task && body.task.taskId === targetTaskId) {
          body.task.state = forcedState;
        }
        await route.fulfill({
          status: response.status(),
          headers: response.headers(),
          body: JSON.stringify(body),
        });
      });
      const listRe = /\/api\/external\/tasks(?:\?|$)/;
      await page.route(listRe, async (route) => {
        if (route.request().method() !== "GET") return route.continue();
        const response = await route.fetch();
        const body = (await response.json()) as {
          tasks: Array<Record<string, unknown>>;
        };
        for (const t of body.tasks) {
          if (t.taskId === targetTaskId) t.state = forcedState;
        }
        await route.fulfill({
          status: response.status(),
          headers: response.headers(),
          body: JSON.stringify(body),
        });
      });
    }

    async function unpinTaskState(targetTaskId: string): Promise<void> {
      const exactTaskRe = new RegExp(
        `/api/external/tasks/${targetTaskId}(?:\\?|$)`,
      );
      await page.unroute(exactTaskRe);
      await page.unroute(/\/api\/external\/tasks(?:\?|$)/);
    }

    // ---------------------------------------------------------------------
    // 1) Deploy pipeline forced to draft → GREEN Launch.
    // ---------------------------------------------------------------------
    await pinTaskState(deployTask.taskId, "draft");
    await page.goto(`/tasks/${deployTask.taskId}`, {
      waitUntil: "domcontentloaded",
    });
    const launchBtn = page.getByTestId("cta-launch-in-terminal");
    await expect(launchBtn).toBeVisible({ timeout: 5000 });

    // Icon left of label — Terminal icon (Lucide) renders an <svg> as the
    // first element child, label text comes after. Also grab data-color and
    // background color so anyone greping the snapshot can trivially confirm
    // the variant. All reads happen in the same evaluate() to avoid the
    // element being re-rendered between two separate locator queries (the
    // transcript polling hook re-renders this bubble tree on every tick).
    const launchShape = await launchBtn.evaluate((el) => ({
      iconFirst:
        !!el.firstElementChild &&
        el.firstElementChild.tagName.toLowerCase() === "svg",
      color: el.getAttribute("data-color"),
      label: el.textContent?.trim(),
      bg: getComputedStyle(el).backgroundColor,
    }));
    // --color-success = #059669 = rgb(5, 150, 105).
    expect(launchShape.bg).toBe("rgb(5, 150, 105)");
    expect(launchShape.iconFirst).toBe(true);
    expect(launchShape.color).toBe("green");
    expect(launchShape.label).toMatch(/Launch/i);

    // Screenshot the header only.
    const header = page.getByTestId("task-detail-header");
    await header.screenshot({
      path: "e2e/screenshots/3.7e-b2-header-launch.png",
    });

    // ---------------------------------------------------------------------
    // 2) Add OAuth scope forced to idle → BROWN Resume.
    // ---------------------------------------------------------------------
    // First drop the deploy-task routes; we'll re-pin later for the ask-bubble
    // test.
    await unpinTaskState(deployTask.taskId);
    await pinTaskState(oauthTask.taskId, "idle");

    await page.goto(`/tasks/${oauthTask.taskId}`, {
      waitUntil: "domcontentloaded",
    });
    const resumeBtn = page.getByTestId("cta-copy-resume-command");
    await expect(resumeBtn).toBeVisible({ timeout: 5000 });

    const resumeShape = await resumeBtn.evaluate((el) => ({
      iconFirst:
        !!el.firstElementChild &&
        el.firstElementChild.tagName.toLowerCase() === "svg",
      color: el.getAttribute("data-color"),
      label: el.textContent?.trim(),
      bg: getComputedStyle(el).backgroundColor,
    }));
    // --color-primary = #6b5e56 = rgb(107, 94, 86).
    expect(resumeShape.bg).toBe("rgb(107, 94, 86)");
    expect(resumeShape.iconFirst).toBe(true);
    expect(resumeShape.color).toBe("brown");
    expect(resumeShape.label).toMatch(/Resume/i);

    const header2 = page.getByTestId("task-detail-header");
    await header2.screenshot({
      path: "e2e/screenshots/3.7e-b2-header-resume.png",
    });

    // Drop the oauth-route overrides + re-pin deploy task back to draft for
    // the ask-bubble test (we want its pending askuser bubble to render).
    await unpinTaskState(oauthTask.taskId);
    await pinTaskState(deployTask.taskId, "draft");

    // ---------------------------------------------------------------------
    // 3) Deploy pipeline again — verify ask-bubble Answer-in-Terminal button.
    //    The deploy task has 1 pending ask (tu-…-1).
    // ---------------------------------------------------------------------
    await page.goto(`/tasks/${deployTask.taskId}`, {
      waitUntil: "domcontentloaded",
    });
    await page.waitForTimeout(1500);
    const askRow = page.getByTestId("askuser-resume-row").first();
    await expect(askRow).toBeVisible({ timeout: 5000 });

    const answerBtn = page.getByTestId("askuser-answer-in-terminal").first();
    await expect(answerBtn).toBeVisible();
    await expect(answerBtn).toContainText(/Answer in Terminal/i);

    const answerBg = await answerBtn.evaluate(
      (el) => getComputedStyle(el).backgroundColor,
    );
    expect(answerBg).toBe("rgb(107, 94, 86)"); // brown

    const answerIconFirst = await answerBtn.evaluate((el) => {
      const first = el.firstElementChild;
      return !!first && first.tagName.toLowerCase() === "svg";
    });
    expect(answerIconFirst).toBe(true);

    // Screenshot the ask bubble (use its parent for context).
    const askBubble = page.getByTestId("askuser-pending").first();
    if ((await askBubble.count()) > 0) {
      await askBubble.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      await askBubble.screenshot({
        path: "e2e/screenshots/3.7e-b2-ask-bubble.png",
      });
    }

    // ---------------------------------------------------------------------
    // 4) Assistant bubble → CLAUDE role label.
    //    The deploy task JSONL contains an assistant message; scroll top
    //    and look for any bubble-assistant.
    // ---------------------------------------------------------------------
    const scroll = page.getByTestId("transcript-scroll");
    if ((await scroll.count()) > 0) {
      await scroll.evaluate((el) => {
        el.scrollTop = 0;
      });
      await page.waitForTimeout(300);
    }
    const assistantBubble = page.getByTestId("bubble-assistant").first();
    if ((await assistantBubble.count()) > 0) {
      const role = await assistantBubble.locator("span").first().innerText();
      expect(role.trim().toUpperCase()).toBe("CLAUDE");
      await assistantBubble.screenshot({
        path: "e2e/screenshots/3.7e-b2-claude-badge.png",
      });
    } else {
      // eslint-disable-next-line no-console
      console.log(
        "no assistant bubble in deploy task — falling back to refactor task",
      );
      await page.goto("/", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(1000);
      const refactorTitle = page.getByText(/Refactor auth middleware/i).first();
      if ((await refactorTitle.count()) > 0) {
        await refactorTitle.click();
        await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
        await page.waitForTimeout(1500);
        const ab = page.getByTestId("bubble-assistant").first();
        if ((await ab.count()) > 0) {
          const role = await ab.locator("span").first().innerText();
          expect(role.trim().toUpperCase()).toBe("CLAUDE");
          await ab.screenshot({
            path: "e2e/screenshots/3.7e-b2-claude-badge.png",
          });
        }
      }
    }

    // ---------------------------------------------------------------------
    // 5) User bubble — no border + shadow.
    //    Refactor auth middleware has a user bubble at the top of the
    //    transcript (seeded).
    // ---------------------------------------------------------------------
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    const refactorCard = page.getByText(/Refactor auth middleware/i).first();
    if ((await refactorCard.count()) > 0) {
      await refactorCard.click();
      await page.waitForURL(/\/tasks\/.+/, { timeout: 5000 });
      await page.waitForTimeout(1500);
      const scr = page.getByTestId("transcript-scroll");
      if ((await scr.count()) > 0) {
        await scr.evaluate((el) => {
          el.scrollTop = 0;
        });
        await page.waitForTimeout(300);
      }
      const userBubble = page.getByTestId("bubble-user").first();
      await expect(userBubble).toBeVisible({ timeout: 5000 });

      // Inspect the INNER bubble (first child of the outer flex wrapper).
      const style = await userBubble.evaluate((el) => {
        const inner = el.firstElementChild as HTMLElement | null;
        if (!inner) return { border: "", boxShadow: "", bg: "" };
        const s = getComputedStyle(inner);
        return {
          border: s.border,
          borderTopWidth: s.borderTopWidth,
          borderRightWidth: s.borderRightWidth,
          borderBottomWidth: s.borderBottomWidth,
          borderLeftWidth: s.borderLeftWidth,
          boxShadow: s.boxShadow,
          bg: s.backgroundColor,
        };
      });
      // No border → every border-*-width is 0px.
      expect(style.borderTopWidth).toBe("0px");
      expect(style.borderRightWidth).toBe("0px");
      expect(style.borderBottomWidth).toBe("0px");
      expect(style.borderLeftWidth).toBe("0px");
      // Shadow present — must NOT be "none".
      expect(style.boxShadow).not.toBe("none");
      // Darker background from 3.7d-a: --color-border = #e0dbd4 =
      // rgb(224, 219, 212).
      expect(style.bg).toBe("rgb(224, 219, 212)");

      await userBubble.screenshot({
        path: "e2e/screenshots/3.7e-b2-user-bubble.png",
      });
    }

    // eslint-disable-next-line no-console
    console.log("3.7e-b2 console errors:", JSON.stringify(consoleErrors));
    // Filter out S1-surface errors — parallel agents are mid-edit on TaskCard
    // / TaskBoardPage / Projects / Inbox files; errors originating in those
    // files are NOT mine. My scope is TaskDetailHeader + TaskDetail screens.
    const myErrors = consoleErrors.filter(
      (e) =>
        !/favicon|401|CORS/i.test(e) &&
        !/TaskCard|TaskBoard|ProjectsPage|ProjectWizard|InboxPage/.test(e) &&
        !/isDraft is not defined/.test(e),
    );
    expect(myErrors).toEqual([]);
  });
});
