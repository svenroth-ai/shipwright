/*
 * file-route.test.ts — GET /api/external/projects/:projectId/file
 * (section 04a, spec § 5.3).
 *
 * Security contract:
 *   - Path traversal → 400
 *   - > 5 MB → 413 file_too_large
 *   - Binary MIME not in the image allowlist → 415
 *   - X-Content-Type-Options: nosniff on every 200
 *   - Explicit Content-Type per extension
 *   - Content-Disposition: inline; filename="<sanitized>" with RFC-6266
 *     escaping + hard-limited character class (no CR/LF/quote/backslash)
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Hono } from "hono";
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  mkdirSync,
  writeFile as writeFileCb,
} from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";
import { promisify } from "node:util";

import {
  SdkSessionsStore,
  type SdkSessionsStoreDeps,
} from "../core/sdk-sessions-store.js";
import { SessionWatcher } from "../core/session-watcher.js";
import { createExternalRoutes, type ExternalRouteProjectView } from "./routes.js";
import { __clearGitignoreCacheForTests } from "../core/gitignore-cache.js";

const writeFileAsync = promisify(writeFileCb);

function inMemoryDeps(): SdkSessionsStoreDeps {
  const files = new Map<string, string>();
  const existing = new Set<string>();
  return {
    readFile: async (p) => {
      if (!files.has(p)) throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
      return files.get(p)!;
    },
    writeFile: async (p, data) => {
      files.set(p, data);
      existing.add(p);
    },
    existsSync: (p) => existing.has(p),
    mkdirSync: (p) => {
      existing.add(p);
    },
    ensureFile: (p) => {
      if (!files.has(p)) files.set(p, "");
      existing.add(p);
    },
  };
}

describe("GET /api/external/projects/:projectId/file (section 04a)", () => {
  let app: Hono;
  let projectDir: string;
  const projectId = "p-file-test";

  beforeEach(async () => {
    projectDir = mkdtempSync(path.join(tmpdir(), "file-route-test-"));
    mkdirSync(path.join(projectDir, "src"), { recursive: true });
    writeFileSync(path.join(projectDir, "src", "index.ts"), "export const x = 1;\n");
    writeFileSync(path.join(projectDir, "README.md"), "# hi\n");
    writeFileSync(path.join(projectDir, "notes.txt"), "plain\n");
    // Minimal 1x1 valid PNG header — byte content ≠ 0 so length > 0.
    writeFileSync(
      path.join(projectDir, "logo.png"),
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    );
    writeFileSync(
      path.join(projectDir, "logo.jpg"),
      Buffer.from([0xff, 0xd8, 0xff, 0xe0]),
    );
    writeFileSync(
      path.join(projectDir, "logo.jpeg"),
      Buffer.from([0xff, 0xd8, 0xff, 0xe0]),
    );
    writeFileSync(
      path.join(projectDir, "logo.gif"),
      Buffer.from([0x47, 0x49, 0x46, 0x38]),
    );
    writeFileSync(
      path.join(projectDir, "logo.svg"),
      "<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>",
    );
    writeFileSync(
      path.join(projectDir, "logo.webp"),
      Buffer.from([0x52, 0x49, 0x46, 0x46, 0, 0, 0, 0, 0x57, 0x45, 0x42, 0x50]),
    );
    writeFileSync(path.join(projectDir, "archive.zip"), Buffer.from([0x50, 0x4b, 0x03, 0x04]));
    writeFileSync(
      path.join(projectDir, "weird name; rm -rf ~.txt"),
      "evil filename\n",
    );

    __clearGitignoreCacheForTests();

    const store = new SdkSessionsStore(
      "/store/sdk-sessions.json",
      inMemoryDeps(),
    );
    await store.load();
    const watcher = new SessionWatcher({ projectsDir: projectDir });
    const project: ExternalRouteProjectView = {
      id: projectId,
      name: "test",
      path: projectDir,
    };
    app = new Hono();
    app.route(
      "/",
      createExternalRoutes({
        store,
        watcher,
        getProjectById: (id) => (id === projectId ? project : undefined),
      }),
    );
  });

  afterEach(() => {
    try {
      rmSync(projectDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  });

  it("404 unknown project id", async () => {
    const res = await app.request(
      "/api/external/projects/not-a-project/file?path=README.md",
    );
    expect(res.status).toBe(404);
  });

  it("400 missing ?path parameter", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file`,
    );
    expect(res.status).toBe(400);
  });

  it("200 text file: Content-Type text/plain + nosniff + Content-Disposition inline", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=notes.txt`,
    );
    expect(res.status).toBe(200);
    const ct = res.headers.get("content-type") ?? "";
    expect(ct).toMatch(/^text\/plain/);
    expect(ct).toMatch(/charset=utf-8/);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    const cd = res.headers.get("content-disposition") ?? "";
    expect(cd).toMatch(/^inline;\s*filename="[^"]+"/);
    expect(cd).toContain('filename="notes.txt"');
    expect(await res.text()).toBe("plain\n");
  });

  it("200 markdown file: text/markdown; charset=utf-8", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=README.md`,
    );
    expect(res.status).toBe(200);
    const ct = res.headers.get("content-type") ?? "";
    expect(ct).toMatch(/^text\/markdown/);
    expect(ct).toMatch(/charset=utf-8/);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it("200 typescript file: text/plain with utf-8 (not JS mime)", async () => {
    // .ts is NOT image-allowlist, but IS text. We return text/plain to
    // prevent the browser from ever executing it — the explicit Content-Type
    // plus nosniff guarantees no script execution even if rendered <iframe>.
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=src/index.ts`,
    );
    expect(res.status).toBe(200);
    const ct = res.headers.get("content-type") ?? "";
    expect(ct).toMatch(/^text\/plain/);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
  });

  it.each([
    ["png", "image/png"],
    ["jpg", "image/jpeg"],
    ["jpeg", "image/jpeg"],
    ["gif", "image/gif"],
    ["svg", "image/svg+xml"],
    ["webp", "image/webp"],
  ])("200 image.%s: Content-Type %s + nosniff", async (ext, mime) => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=logo.${ext}`,
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe(mime);
    expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    expect(res.headers.get("content-disposition")).toMatch(
      new RegExp(`^inline;\\s*filename="logo\\.${ext}"`),
    );
  });

  it("415 binary non-image: .zip rejected", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=archive.zip`,
    );
    expect(res.status).toBe(415);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("binary_not_previewable");
  });

  it("413 file_too_large: >5 MB rejected", async () => {
    // 5 MB + 1 byte.
    const bigPath = path.join(projectDir, "big.txt");
    const size = 5 * 1024 * 1024 + 1;
    // Write as a buffer of zeros. fs.writeFileSync is synchronous and
    // sufficient for this one-off write.
    writeFileSync(bigPath, Buffer.alloc(size, 0x41));
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=big.txt`,
    );
    expect(res.status).toBe(413);
    const body = (await res.json()) as { error: string; maxBytes: number };
    expect(body.error).toBe("file_too_large");
    expect(body.maxBytes).toBe(5 * 1024 * 1024);
  });

  it("400 traversal: ?path=../etc/passwd", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=${encodeURIComponent("../etc/passwd")}`,
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("path_traversal");
  });

  it("400 absolute: ?path=/etc/passwd", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=${encodeURIComponent("/etc/passwd")}`,
    );
    expect(res.status).toBe(400);
  });

  it("404 not_found on missing path", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=does-not-exist.txt`,
    );
    expect(res.status).toBe(404);
  });

  it("400 on directory: ?path=src (dir) returns 400 not_a_file", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=src`,
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("not_a_file");
  });

  it("filename sanitization: quotes/CR/LF stripped + bounded to 120 chars", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=${encodeURIComponent("weird name; rm -rf ~.txt")}`,
    );
    expect(res.status).toBe(200);
    const cd = res.headers.get("content-disposition") ?? "";
    // Must not contain raw CR or LF (header injection defense).
    expect(cd).not.toMatch(/[\r\n]/);
    // Matches the inline; filename="..." shape with only [A-Za-z0-9._-] + spaces.
    expect(cd).toMatch(/^inline;\s*filename="[A-Za-z0-9._ -]+"$/);
    // Backslash and embedded quote forbidden.
    expect(cd).not.toContain("\\");
  });

  it("filename sanitization: 200-char filename clamped to 120", async () => {
    const longName = "a".repeat(200) + ".txt";
    writeFileSync(path.join(projectDir, longName), "x");
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=${encodeURIComponent(longName)}`,
    );
    expect(res.status).toBe(200);
    const cd = res.headers.get("content-disposition") ?? "";
    const m = cd.match(/filename="([^"]+)"/);
    expect(m).not.toBeNull();
    if (m) expect(m[1].length).toBeLessThanOrEqual(120);
  });

  it("CSP header blocks inline scripts on SVG (defense in depth)", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/file?path=logo.svg`,
    );
    expect(res.status).toBe(200);
    const csp = res.headers.get("content-security-policy") ?? "";
    expect(csp).toContain("default-src 'none'");
    expect(csp).toContain("sandbox");
  });

  it("nosniff present on every 200 response", async () => {
    const paths = ["notes.txt", "README.md", "logo.png", "src/index.ts"];
    for (const p of paths) {
      const res = await app.request(
        `/api/external/projects/${projectId}/file?path=${encodeURIComponent(p)}`,
      );
      expect(res.status).toBe(200);
      expect(res.headers.get("x-content-type-options")).toBe("nosniff");
    }
  });
});
