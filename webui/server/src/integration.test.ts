import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import { ProjectManager } from "./core/project-manager.js";
import { EventStore } from "./core/event-store.js";
import { TaskManager } from "./core/task-manager.js";
import { appendEvent, emitTaskCreatedEvent } from "./bridge/event-writer.js";
import { readEventsFromFile } from "./bridge/event-reader.js";

let tmpDir: string;

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "shipwright-int-"));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

describe("ProjectManager — real file I/O", () => {
  function createManager() {
    const registryPath = path.join(tmpDir, "registry.json").replace(/\\/g, "/");
    return new ProjectManager(registryPath, {
      readFile: (p, enc) => fs.promises.readFile(p, enc as BufferEncoding),
      // Use sync write wrapped in resolved promise to avoid race conditions
      // (ProjectManager.persist() is fire-and-forget)
      writeFile: (p, data) => { fs.writeFileSync(p, data, "utf-8"); return Promise.resolve(); },
      existsSync: (p) => fs.existsSync(p),
      mkdirSync: (p, opts) => fs.mkdirSync(p, opts),
      readdirSync: (p, opts) =>
        fs.readdirSync(p, opts as { withFileTypes: true }) as unknown as Array<{
          name: string;
          isDirectory: () => boolean;
        }>,
    });
  }

  it("creates registry file on first load", async () => {
    const pm = createManager();
    await pm.load();
    const registryFile = path.join(tmpDir, "registry.json");
    expect(fs.existsSync(registryFile)).toBe(true);
    const content = JSON.parse(fs.readFileSync(registryFile, "utf-8"));
    expect(content).toEqual([]);
  });

  it("persists and reloads projects", async () => {
    const projectDir = path.join(tmpDir, "my-project").replace(/\\/g, "/");
    fs.mkdirSync(projectDir);

    const pm1 = createManager();
    await pm1.load();
    const created = pm1.create({
      name: "Test Project",
      path: projectDir,
      profile: "custom",
      status: "active",
    });
    expect(created.id).toBeTruthy();
    expect(created.name).toBe("Test Project");

    // Reload from disk
    const pm2 = createManager();
    await pm2.load();
    const all = pm2.getAll();
    expect(all).toHaveLength(1);
    expect(all[0].name).toBe("Test Project");
    expect(all[0].id).toBe(created.id);
  });

  it("updates project settings and persists", async () => {
    const projectDir = path.join(tmpDir, "proj-settings").replace(/\\/g, "/");
    fs.mkdirSync(projectDir);

    const pm = createManager();
    await pm.load();
    const project = pm.create({ name: "Settings Test", path: projectDir, profile: "custom", status: "active" });

    pm.update(project.id, {
      settings: { autonomy: "autonomous", envVars: { API_KEY: "test123" } },
    });

    // Reload
    const pm2 = createManager();
    await pm2.load();
    const reloaded = pm2.getById(project.id);
    expect(reloaded?.settings?.autonomy).toBe("autonomous");
    expect(reloaded?.settings?.envVars?.API_KEY).toBe("test123");
  });

  it("deletes project and persists", async () => {
    const projectDir = path.join(tmpDir, "proj-del").replace(/\\/g, "/");
    fs.mkdirSync(projectDir);

    const pm = createManager();
    await pm.load();
    const project = pm.create({ name: "To Delete", path: projectDir, profile: "custom", status: "active" });
    pm.delete(project.id);

    const pm2 = createManager();
    await pm2.load();
    expect(pm2.getAll()).toHaveLength(0);
  });

  it("discovers projects by shipwright_run_config.json", async () => {
    const scanDir = path.join(tmpDir, "scan").replace(/\\/g, "/");
    fs.mkdirSync(scanDir);
    const proj1 = path.join(scanDir, "proj1");
    const proj2 = path.join(scanDir, "proj2");
    const notProj = path.join(scanDir, "not-a-project");
    fs.mkdirSync(proj1);
    fs.mkdirSync(proj2);
    fs.mkdirSync(notProj);
    fs.writeFileSync(path.join(proj1, "shipwright_run_config.json"), "{}");
    fs.writeFileSync(path.join(proj2, "shipwright_project_config.json"), "{}");

    const pm = createManager();
    await pm.load();
    const discovered = pm.discover(scanDir);
    expect(discovered).toHaveLength(2);
    expect(discovered.map((d) => d.name).sort()).toEqual(["proj1", "proj2"]);
  });
});

describe("EventStore + TaskManager — real file I/O", () => {
  it("writes events to JSONL and replays them", async () => {
    const eventsFile = path.join(tmpDir, "events.jsonl").replace(/\\/g, "/");

    // Write events using event-writer
    const writerDeps = {
      appendFile: (p: string, data: string) => fs.promises.appendFile(p, data, "utf-8"),
      lock: async (_p: string) => async () => {},
      ensureDir: (p: string) => { if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true }); },
      ensureFile: (p: string) => { if (!fs.existsSync(p)) fs.writeFileSync(p, ""); },
    };

    await emitTaskCreatedEvent(eventsFile, "task-1", "proj-1", "Build login page", "feat", "P1", writerDeps);
    await appendEvent(eventsFile, {
      type: "phase_started",
      timestamp: new Date().toISOString(),
      task_id: "task-1",
      phase: "build",
    }, writerDeps);
    await appendEvent(eventsFile, {
      type: "task_updated",
      timestamp: new Date().toISOString(),
      task_id: "task-1",
      description: "Build login page with OAuth",
    }, writerDeps);

    // Read events from file
    const readerDeps = {
      readFile: (p: string) => fs.promises.readFile(p, "utf-8"),
      existsSync: (p: string) => fs.existsSync(p),
    };
    const events = await readEventsFromFile(eventsFile, readerDeps);
    expect(events).toHaveLength(3);

    // Replay in EventStore
    const store = new EventStore();
    store.replayProject("proj-1", events);

    const tasks = store.getTasksForProject("proj-1");
    expect(tasks).toHaveLength(1);
    expect(tasks[0].description).toBe("Build login page with OAuth"); // Updated description
    expect(tasks[0].status).toBe("running");
    expect(tasks[0].currentPhase).toBe("build");
    expect(tasks[0].intent).toBe("feat");
    expect(tasks[0].priority).toBe("P1");
  });

  it("TaskManager derives kanban status correctly", async () => {
    const store = new EventStore();
    store.replayProject("proj-1", [
      {
        type: "task_created",
        timestamp: "2026-04-01T00:00:00Z",
        task_id: "t1",
        project_id: "proj-1",
        description: "Task A",
      },
      {
        type: "task_created",
        timestamp: "2026-04-01T00:01:00Z",
        task_id: "t2",
        project_id: "proj-1",
        description: "Task B",
      },
      {
        type: "phase_started",
        timestamp: "2026-04-01T00:02:00Z",
        task_id: "t1",
        phase: "build",
      },
      {
        type: "work_completed",
        timestamp: "2026-04-01T00:03:00Z",
        task_id: "t2",
      },
    ]);

    const tm = new TaskManager(store);
    const tasks = tm.getTasksWithKanban("proj-1");
    expect(tasks).toHaveLength(2);

    const t1 = tasks.find((t) => t.id === "t1")!;
    const t2 = tasks.find((t) => t.id === "t2")!;

    expect(t1.kanbanStatus).toBe("in_progress"); // build phase maps to in_progress
    expect(t2.kanbanStatus).toBe("done"); // work_completed → done
  });

  it("task_cancelled event sets correct state", () => {
    const store = new EventStore();
    store.replayProject("proj-1", [
      {
        type: "task_created",
        timestamp: "2026-04-01T00:00:00Z",
        task_id: "t1",
        project_id: "proj-1",
        description: "Cancelled task",
      },
      {
        type: "task_cancelled",
        timestamp: "2026-04-01T00:01:00Z",
        task_id: "t1",
      },
    ]);

    const tm = new TaskManager(store);
    const tasks = tm.getTasksWithKanban("proj-1");
    expect(tasks[0].status).toBe("cancelled");
    expect(tasks[0].kanbanStatus).toBe("cancelled");
  });
});
