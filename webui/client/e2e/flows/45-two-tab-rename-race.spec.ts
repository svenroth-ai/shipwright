/*
 * Spec 45 — Two-tab rapid rename race.
 *
 * Open the same task in two browser contexts. Issue 5 rapid renames in
 * each tab in parallel. Assert proper-lockfile prevented JSON corruption
 * (the file remains valid + parseable) and that the final title is one
 * of the values written (last-write-wins is deterministic at the lock
 * boundary, even if which-write-wins is timing-dependent).
 */

import { test, expect } from "@playwright/test";

test.describe("Concurrent rename — proper-lockfile contract", () => {
  test("5 + 5 parallel renames across two tabs leave the store consistent", async ({
    browser,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "race-init", cwd: "C:/tmp/race" },
    });
    const { task } = (await create.json()) as { task: { taskId: string } };

    const titlesA = ["a1", "a2", "a3", "a4", "a5"];
    const titlesB = ["b1", "b2", "b3", "b4", "b5"];

    const ctxA = await browser.newContext();
    const ctxB = await browser.newContext();
    try {
      // Issue parallel PATCHes from each context — using context.request
      // means cookies + same origin as a real tab.
      const [resultsA, resultsB] = await Promise.all([
        Promise.all(
          titlesA.map((title) =>
            ctxA.request.patch(`/api/external/tasks/${task.taskId}`, {
              headers: { "Content-Type": "application/json" },
              data: { title },
            }),
          ),
        ),
        Promise.all(
          titlesB.map((title) =>
            ctxB.request.patch(`/api/external/tasks/${task.taskId}`, {
              headers: { "Content-Type": "application/json" },
              data: { title },
            }),
          ),
        ),
      ]);

      // Every PATCH should succeed (200) or be the documented contention
      // surface (409). No silent corruption / 500s.
      for (const r of [...resultsA, ...resultsB]) {
        expect([200, 409]).toContain(r.status());
      }

      // Final state read: the title is one of the 10 values we wrote.
      const final = await request.get(`/api/external/tasks/${task.taskId}`);
      expect(final.status()).toBe(200);
      const { task: refreshed } = (await final.json()) as { task: { title: string } };
      expect([...titlesA, ...titlesB]).toContain(refreshed.title);
    } finally {
      await ctxA.close();
      await ctxB.close();
    }
  });
});
