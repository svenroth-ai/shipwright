import type { ClaudeProcess, ClaudeSpawnOptions, ClaudeAdapter } from "./claude-adapter.js";

export interface GovernorDeps {
  isProcessRunning: (pid: number) => boolean;
  kill: (pid: number, signal?: string) => void;
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}

export const defaultGovernorDeps: GovernorDeps = {
  isProcessRunning: (pid: number) => {
    try {
      process.kill(pid, 0);
      return true;
    } catch {
      return false;
    }
  },
  kill: (pid: number, signal?: string) => {
    process.kill(pid, signal as NodeJS.Signals);
  },
  readFile: async (path, encoding) => {
    const fs = await import("fs/promises");
    return fs.readFile(path, encoding as BufferEncoding);
  },
  writeFile: async (path, data) => {
    const fs = await import("fs/promises");
    await fs.writeFile(path, data);
  },
  existsSync: (path) => {
    const fs = require("fs");
    return fs.existsSync(path);
  },
  mkdirSync: (path, opts) => {
    const fs = require("fs");
    fs.mkdirSync(path, opts);
  },
};

export class ProcessGovernor {
  private activeProcesses = new Map<string, ClaudeProcess>();
  private queue: ClaudeSpawnOptions[] = [];

  constructor(
    private maxConcurrent: number,
    private adapter: ClaudeAdapter,
    private deps: GovernorDeps,
    private pidFilePath: string
  ) {}

  async acquire(options: ClaudeSpawnOptions): Promise<ClaudeProcess | "queued"> {
    if (this.activeProcesses.size < this.maxConcurrent) {
      const proc = this.adapter.spawn(options);
      this.activeProcesses.set(options.taskId, proc);
      await this.persistPids();
      return proc;
    }
    this.queue.push(options);
    return "queued";
  }

  async release(taskId: string): Promise<void> {
    this.activeProcesses.delete(taskId);
    await this.persistPids();

    if (this.queue.length > 0) {
      const next = this.queue.shift()!;
      await this.acquire(next);
    }
  }

  async persistPids(): Promise<void> {
    const dir = this.pidFilePath.substring(0, this.pidFilePath.lastIndexOf("/"));
    if (dir && !this.deps.existsSync(dir)) {
      this.deps.mkdirSync(dir, { recursive: true });
    }
    const pids = Array.from(this.activeProcesses.values())
      .filter((p) => p.pid > 0)
      .map((p) => ({
        pid: p.pid,
        taskId: p.taskId,
      }));
    await this.deps.writeFile(this.pidFilePath, JSON.stringify(pids));
  }

  async loadPids(): Promise<Array<{ pid: number; taskId: string }>> {
    if (!this.deps.existsSync(this.pidFilePath)) return [];
    try {
      const content = await this.deps.readFile(this.pidFilePath, "utf-8");
      return JSON.parse(content);
    } catch {
      return [];
    }
  }

  async cleanupOrphans(): Promise<{ killed: number; stale: number }> {
    const pids = await this.loadPids();
    let killed = 0;
    let stale = 0;

    for (const entry of pids) {
      if (this.activeProcesses.has(entry.taskId)) continue;
      // Skip invalid PIDs (0 = own process group, negative = process group)
      if (!entry.pid || entry.pid <= 0) {
        stale++;
        continue;
      }
      if (this.deps.isProcessRunning(entry.pid)) {
        try {
          this.deps.kill(entry.pid);
          killed++;
        } catch {
          stale++;
        }
      } else {
        stale++;
      }
    }

    await this.deps.writeFile(this.pidFilePath, "[]");
    console.log(JSON.stringify({ level: "info", message: "Orphan cleanup", killed, stale }));
    return { killed, stale };
  }

  getProcess(taskId: string): ClaudeProcess | undefined {
    return this.activeProcesses.get(taskId);
  }

  getAllActive(): ClaudeProcess[] {
    return Array.from(this.activeProcesses.values());
  }

  getQueueLength(): number {
    return this.queue.length;
  }
}
