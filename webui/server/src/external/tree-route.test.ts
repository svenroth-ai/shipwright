/*
 * tree-route.test.ts — GET /api/external/projects/:projectId/tree
 * (section 04a, spec § 5.2).
 *
 * Tests use a throwaway project dir under tmpdir with a synthesized set
 * of files + directories + .gitignore to drive the assertions.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Hono } from "hono";
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  mkdirSync,
  utimesSync,
} from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import {
  SdkSessionsStore,
  type SdkSessionsStoreDeps,
} from "../core/sdk-sessions-store.js";
import { SessionWatcher } from "../core/session-watcher.js";
import { createExternalRoutes, type ExternalRouteProjectView } from "./routes.js";
import {
  __clearGitignoreCacheForTests,
  __getGitignoreCacheStatsForTests,
} from "../core/gitignore-cache.js";

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

describe("GET /api/external/projects/:projectId/tree (section 04a)", () => {
  let app: Hono;
  let projectDir: string;
  const projectId = "p-tree-test";

  beforeEach(async () => {
    projectDir = mkdtempSync(path.join(tmpdir(), "tree-route-test-"));
    // Layout under projectDir:
    //   src/index.ts
    //   src/components/Foo.tsx
    //   README.md
    //   .git/HEAD                (ignored via defaults)
    //   node_modules/.pkg        (ignored via defaults)
    //   secrets/credentials.txt  (ignored via .gitignore)
    //   .gitignore
    mkdirSync(path.join(projectDir, "src", "components"), { recursive: true });
    writeFileSync(path.join(projectDir, "src", "index.ts"), "export {};");
    writeFileSync(
      path.join(projectDir, "src", "components", "Foo.tsx"),
      "export const Foo = () => null;",
    );
    writeFileSync(path.join(projectDir, "README.md"), "# project");
    mkdirSync(path.join(projectDir, ".git"), { recursive: true });
    writeFileSync(path.join(projectDir, ".git", "HEAD"), "ref: refs/heads/main\n");
    mkdirSync(path.join(projectDir, "node_modules"), { recursive: true });
    writeFileSync(path.join(projectDir, "node_modules", ".pkg"), "");
    mkdirSync(path.join(projectDir, "secrets"), { recursive: true });
    writeFileSync(path.join(projectDir, "secrets", "credentials.txt"), "s3cret");
    writeFileSync(path.join(projectDir, ".gitignore"), "secrets\n");

    __clearGitignoreCacheForTests();

    const store = new SdkSessionsStore("/store/sdk-sessions.json", inMemoryDeps());
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
    const res = await app.request("/api/external/projects/not-a-project/tree");
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("project_not_found");
  });

  it("root listing without ?path returns top-level entries", async () => {
    const res = await app.request(`/api/external/projects/${projectId}/tree`);
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      entries: Array<{ name: string; kind: "file" | "dir"; ignored: boolean }>;
    };
    const names = body.entries.map((e) => e.name).sort();
    expect(names).toContain("src");
    expect(names).toContain("README.md");
    expect(names).toContain(".git");
    expect(names).toContain("node_modules");
    expect(names).toContain("secrets");
    expect(names).toContain(".gitignore");

    const src = body.entries.find((e) => e.name === "src");
    expect(src?.kind).toBe("dir");
    expect(src?.ignored).toBe(false);

    const readme = body.entries.find((e) => e.name === "README.md");
    expect(readme?.kind).toBe("file");
    expect(readme?.ignored).toBe(false);
  });

  it("default ignored markers flagged ignored:true", async () => {
    const res = await app.request(`/api/external/projects/${projectId}/tree`);
    const body = (await res.json()) as {
      entries: Array<{ name: string; ignored: boolean }>;
    };
    const git = body.entries.find((e) => e.name === ".git");
    const nodeModules = body.entries.find((e) => e.name === "node_modules");
    expect(git?.ignored).toBe(true);
    expect(nodeModules?.ignored).toBe(true);
  });

  it(".gitignore pattern 'secrets' flags secrets dir ignored:true", async () => {
    const res = await app.request(`/api/external/projects/${projectId}/tree`);
    const body = (await res.json()) as {
      entries: Array<{ name: string; ignored: boolean }>;
    };
    const secrets = body.entries.find((e) => e.name === "secrets");
    expect(secrets?.ignored).toBe(true);
  });

  it("?path=src returns only src's direct children (lazy expand)", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/tree?path=src`,
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      entries: Array<{ name: string; kind: string }>;
    };
    const names = body.entries.map((e) => e.name).sort();
    expect(names).toEqual(["components", "index.ts"]);
    // Ensure we didn't recurse — components/Foo.tsx should NOT appear here.
    expect(names.includes("Foo.tsx")).toBe(false);
  });

  it("?path=../other (traversal) returns 400 path_traversal", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/tree?path=${encodeURIComponent("../other")}`,
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("path_traversal");
  });

  it("?path=/etc/passwd (absolute) returns 400", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/tree?path=${encodeURIComponent("/etc/passwd")}`,
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    // "absolute_input" maps to same error code as traversal from client
    // perspective — both are "you cannot escape the project root".
    expect(["path_traversal", "absolute_input"]).toContain(body.error);
  });

  it("?path=does-not-exist returns 404 not_found", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/tree?path=does-not-exist`,
    );
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("not_found");
  });

  it("?path=README.md (file, not dir) returns 400 not_a_directory", async () => {
    const res = await app.request(
      `/api/external/projects/${projectId}/tree?path=README.md`,
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("not_a_directory");
  });

  it("ignore cache: two calls with no mtime change → parser invoked once", async () => {
    __clearGitignoreCacheForTests();
    await app.request(`/api/external/projects/${projectId}/tree`);
    await app.request(`/api/external/projects/${projectId}/tree`);
    const stats = __getGitignoreCacheStatsForTests();
    expect(stats.parses).toBe(1);
  });

  it("ignore cache: mtime change forces re-parse", async () => {
    __clearGitignoreCacheForTests();
    await app.request(`/api/external/projects/${projectId}/tree`);

    // Bump mtime on .gitignore
    const future = new Date(Date.now() + 2000);
    writeFileSync(path.join(projectDir, ".gitignore"), "cache\n");
    utimesSync(path.join(projectDir, ".gitignore"), future, future);

    await app.request(`/api/external/projects/${projectId}/tree`);
    const stats = __getGitignoreCacheStatsForTests();
    expect(stats.parses).toBe(2);
  });
});
