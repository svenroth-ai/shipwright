/*
 * PATCH /api/external/tasks/:id — projectId extension (section 02).
 *
 * Iterate 2 shipped title-only PATCH. Section 02 adds {projectId} as an
 * independently-optional field and loosens the "title required" rule to
 * "at least one of title|projectId must be present".
 *
 * Unknown projectId → 400 with {error:"unknown_project_id", projectId}.
 * Reserved literal "unassigned" is always valid.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Hono } from "hono";
import { mkdtempSync, rmSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import { SdkSessionsStore, type SdkSessionsStoreDeps } from "../core/sdk-sessions-store.js";
import { SessionWatcher } from "../core/session-watcher.js";
import { createExternalRoutes } from "./routes.js";

function inMemoryDeps(): SdkSessionsStoreDeps {
  const files = new Map<string, string>();
  const existing = new Set<string>();
  return {
    readFile: async (p) => {
      if (!files.has(p)) throw Object.assign(new Error("ENOENT"), { code: "ENOENT" });
      return files.get(p)!;
    },
    writeFile: async (p, data) => { files.set(p, data); existing.add(p); },
    existsSync: (p) => existing.has(p),
    mkdirSync: (p) => { existing.add(p); },
    ensureFile: (p) => { if (!files.has(p)) files.set(p, ""); existing.add(p); },
  };
}

describe("PATCH /api/external/tasks/:id — projectId (section 02)", () => {
  let app: Hono;
  let store: SdkSessionsStore;
  let projectsDir: string;
  const knownProjectIds = () => new Set(["p-known-1", "p-known-2"]);

  beforeEach(async () => {
    projectsDir = mkdtempSync(path.join(tmpdir(), "proj-patch-route-"));
    store = new SdkSessionsStore("/store/sdk-sessions.json", inMemoryDeps());
    await store.load();
    const watcher = new SessionWatcher({ projectsDir });
    app = new Hono();
    app.route(
      "/",
      createExternalRoutes({
        store,
        watcher,
        getKnownProjectIds: knownProjectIds,
      }),
    );
  });

  async function createTask(): Promise<string> {
    const res = await app.request("/api/external/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "seed", cwd: "/tmp" }),
    });
    const body = (await res.json()) as { task: { taskId: string } };
    return body.task.taskId;
  }

  it("patch-accepts-valid-projectId: known id succeeds with 200 + mutation visible on reread", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "p-known-1" }),
    });
    expect(res.status).toBe(200);

    const reread = await app.request(`/api/external/tasks/${taskId}`);
    const body = (await reread.json()) as { task: { projectId: string } };
    expect(body.task.projectId).toBe("p-known-1");
  });

  it("patch-accepts-reserved-unassigned: literal 'unassigned' always valid", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "unassigned" }),
    });
    expect(res.status).toBe(200);
    const reread = await app.request(`/api/external/tasks/${taskId}`);
    const body = (await reread.json()) as { task: { projectId: string } };
    expect(body.task.projectId).toBe("unassigned");
  });

  it("patch-rejects-unknown-projectId: unknown id returns 400 + structured error", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "does-not-exist" }),
    });
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string; projectId: string };
    expect(body.error).toBe("unknown_project_id");
    expect(body.projectId).toBe("does-not-exist");
  });

  it("patch-accepts-title-alone-legacy: iterate-2 title-only shape still works", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "renamed" }),
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { task: { title: string } };
    expect(body.task.title).toBe("renamed");
  });

  it("patch-accepts-projectId-alone: no title needed", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId: "p-known-2" }),
    });
    expect(res.status).toBe(200);
  });

  it("patch-title-and-projectId-together: both applied atomically", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "both", projectId: "p-known-1" }),
    });
    expect(res.status).toBe(200);
    const body = (await res.json()) as { task: { title: string; projectId: string } };
    expect(body.task.title).toBe("both");
    expect(body.task.projectId).toBe("p-known-1");
  });

  it("patch-with-no-fields: empty body returns 400 with at_least_one_field_required", async () => {
    const taskId = await createTask();
    const res = await app.request(`/api/external/tasks/${taskId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
    const body = (await res.json()) as { error: string };
    expect(body.error).toBe("at_least_one_field_required");
  });

  afterEach(() => {
    try { rmSync(projectsDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });
});
