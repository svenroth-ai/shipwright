/*
 * Spec 37a — Markdown rendering, code highlighting, ANSI stripping,
 * long-line wrapping, malformed-middle-line tolerance.
 *
 * Seeds a JSONL containing assistant markdown text, a fenced code block,
 * a tool_result with ANSI escapes, a 5 KB long line, and a malformed
 * middle line. Verifies the transcript renders all of them without
 * crashing the page and surfaces the malformed line as an unknown stub
 * (not a silent drop).
 */

import { test, expect } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { homedir } from "node:os";

const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

test.describe("Markdown + code + ANSI + long-line rendering", () => {
  test("assistant markdown, fenced code, ANSI tool_result, long line all render without errors", async ({
    page,
    request,
  }) => {
    const create = await request.post("/api/external/tasks", {
      data: { title: "render-spec", cwd: "C:/tmp/render-spec" },
    });
    const { task } = (await create.json()) as { task: { taskId: string; sessionUuid: string } };

    const encodedDir = path.join(PROJECTS_DIR, `e2e-render-${Date.now()}`);
    mkdirSync(encodedDir, { recursive: true });
    const jsonlPath = path.join(encodedDir, `${task.sessionUuid}.jsonl`);

    const markdownAssistant =
      "## Heading\n\n" +
      "Some **bold** and *italic* text with a `code span`.\n\n" +
      "```ts\nconst pi = 3.14;\n```\n";

    const ansiToolResult = "\u001b[31mRED ERROR\u001b[0m\nplain second line";

    const longLine = "y".repeat(5000);

    const lines = [
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "text", text: markdownAssistant }] },
      }),
      // Malformed middle line — should surface as unknown stub.
      "this-is-not-json-and-should-become-an-unknown-event",
      JSON.stringify({
        type: "user",
        sessionId: task.sessionUuid,
        message: {
          content: [
            { type: "tool_result", tool_use_id: "tu_x", content: ansiToolResult },
          ],
        },
      }),
      JSON.stringify({
        type: "assistant",
        sessionId: task.sessionUuid,
        message: { content: [{ type: "text", text: longLine }] },
      }),
    ];
    writeFileSync(jsonlPath, lines.join("\n") + "\n", "utf-8");

    // Capture page errors so a thrown render exception fails the test.
    const pageErrors: Error[] = [];
    page.on("pageerror", (err) => pageErrors.push(err));

    await page.goto(`/tasks/${task.taskId}`);
    await expect(page.getByTestId("task-detail-page")).toBeVisible();

    // Markdown body present, raw markdown chars not leaking.
    await expect(page.getByTestId("markdown-body").first()).toBeVisible({ timeout: 5000 });
    await expect(page.locator("strong").filter({ hasText: "bold" })).toBeVisible();
    await expect(page.locator("em").filter({ hasText: "italic" })).toBeVisible();
    await expect(page.locator("h2").filter({ hasText: "Heading" })).toBeVisible();
    await expect(page.getByTestId("fenced-code").first()).toContainText("const pi = 3.14;");

    // Malformed middle line surfaces as an unknown event (not silently dropped).
    await expect(page.getByTestId("bubble-unknown").first()).toBeVisible();

    // Tool output renders ANSI-stripped (the literal text, not escape codes).
    const toolBlock = page.getByTestId("tool-output-block").first();
    await expect(toolBlock).toBeVisible();
    const toolText = await toolBlock.textContent();
    expect(toolText).toContain("RED ERROR");
    expect(toolText).not.toMatch(/\u001b\[/); // no ANSI escapes in DOM text

    // Long line: ZWS injection means the text is still present + the layout
    // doesn't blow out (we don't measure pixels here, just the DOM survival).
    const bodyText = await page.locator("body").textContent();
    expect(bodyText).toContain("yyyyy");

    expect(pageErrors).toEqual([]);
  });
});
