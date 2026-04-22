/*
 * Flow I — Folder-tree + file byte routes (FR-03.32, FR-03.34..35, O33).
 *
 *   1. GET /tree returns entries; .shipwright-webui is flagged ignored.
 *   2. GET /file returns bytes WITH X-Content-Type-Options: nosniff +
 *      explicit Content-Type matching the extension.
 *   3. Path traversal attempts (relative `..`, absolute paths, drive
 *      changes) return 400.
 *   4. Unknown-project id → 404.
 *
 * Runs entirely via the request context — no browser needed for these
 * pure-HTTP assertions.
 */

import { test, expect, type APIRequestContext } from "@playwright/test";

const UAT_PROJECT_ID = "fa10a30a-21b1-48e0-a588-e7f721ca5bfc";
const BASE = "http://localhost:3847";

async function getTree(request: APIRequestContext, relPath?: string) {
  const url = new URL(`${BASE}/api/external/projects/${UAT_PROJECT_ID}/tree`);
  if (relPath !== undefined) url.searchParams.set("path", relPath);
  return await request.get(url.toString());
}

async function getFile(request: APIRequestContext, relPath: string) {
  const url = new URL(`${BASE}/api/external/projects/${UAT_PROJECT_ID}/file`);
  url.searchParams.set("path", relPath);
  return await request.get(url.toString());
}

test.describe("Flow I — Tree + file routes", () => {
  test("GET /tree returns the UAT 1 root with .shipwright-webui flagged ignored", async ({
    request,
  }) => {
    const resp = await getTree(request);
    expect(resp.ok()).toBeTruthy();
    const body = (await resp.json()) as {
      entries: Array<{ name: string; kind: "file" | "dir"; ignored: boolean }>;
    };
    expect(Array.isArray(body.entries)).toBe(true);
    const sw = body.entries.find((e) => e.name === ".shipwright-webui");
    expect(sw, "tree must include .shipwright-webui entry").toBeDefined();
    expect(sw?.ignored).toBe(true);
    expect(sw?.kind).toBe("dir");
  });

  test("GET /file returns bytes with X-Content-Type-Options: nosniff and explicit Content-Type", async ({
    request,
  }) => {
    const resp = await getFile(request, "README.md");
    expect(resp.ok(), `GET file must succeed — got ${resp.status()}`).toBeTruthy();

    // Hardened headers (FR-03.35 + O33).
    const nosniff = resp.headers()["x-content-type-options"];
    expect(nosniff, "X-Content-Type-Options: nosniff is required").toBe("nosniff");

    const ct = resp.headers()["content-type"] ?? "";
    expect.soft(ct.toLowerCase()).toMatch(/^text\/(markdown|plain)/);

    const text = await resp.text();
    expect(text).toContain("UAT 1 Test Project");
  });

  test("path traversal attempts return 400", async ({ request }) => {
    const attempts = [
      "../../../etc/passwd",
      "..\\..\\..\\windows\\system.ini",
      "/etc/passwd",
      "C:\\Windows\\System32\\drivers\\etc\\hosts",
    ];
    for (const attempt of attempts) {
      const resp = await getFile(request, attempt);
      expect.soft(
        resp.status(),
        `traversal payload "${attempt}" must be rejected (expected 400 — got ${resp.status()})`,
      ).toBe(400);
    }
  });

  test("tree path traversal (absolute + ..) returns 400", async ({ request }) => {
    const attempts = ["../", "../..", "/etc", "C:\\Windows"];
    for (const attempt of attempts) {
      const resp = await getTree(request, attempt);
      expect.soft(
        resp.status(),
        `tree traversal payload "${attempt}" must be rejected`,
      ).toBe(400);
    }
  });

  test("unknown project id → 404 on both endpoints", async ({ request }) => {
    const bogus = "00000000-0000-0000-0000-000000000000";
    const tree = await request.get(`${BASE}/api/external/projects/${bogus}/tree`);
    expect.soft(tree.status()).toBe(404);

    const file = await request.get(
      `${BASE}/api/external/projects/${bogus}/file?path=README.md`,
    );
    expect.soft(file.status()).toBe(404);
  });
});
