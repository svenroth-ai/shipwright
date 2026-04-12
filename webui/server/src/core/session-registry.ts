/**
 * Maps a Shipwright task ID to the real Claude CLI session ID.
 *
 * Context: Claude CLI's --session-id flag does not deterministically create
 * a session with the supplied UUID. On initial spawn, Claude generates its
 * OWN session_id internally and emits it in the first system/init NDJSON
 * event. To resume that session later with --resume <id>, we must use
 * Claude's ID, not ours.
 *
 * This registry captures the real session_id from system/init events and
 * persists it to disk so it survives server restarts.
 */

export interface SessionRegistryDeps {
  readFile: (path: string, encoding: string) => Promise<string>;
  writeFile: (path: string, data: string) => Promise<void>;
  existsSync: (path: string) => boolean;
  mkdirSync: (path: string, opts?: { recursive: boolean }) => void;
}

export class SessionRegistry {
  private taskToSession = new Map<string, string>();
  private loaded = false;

  constructor(
    private deps: SessionRegistryDeps,
    private filePath: string
  ) {}

  async load(): Promise<void> {
    if (this.loaded) return;
    this.loaded = true;
    if (!this.deps.existsSync(this.filePath)) return;
    try {
      const content = await this.deps.readFile(this.filePath, "utf-8");
      const parsed = JSON.parse(content) as Record<string, string>;
      for (const [taskId, sessionId] of Object.entries(parsed)) {
        this.taskToSession.set(taskId, sessionId);
      }
    } catch {
      // Ignore corrupt file
    }
  }

  /** Record the real Claude session_id for a task (from system/init). */
  async set(taskId: string, sessionId: string): Promise<void> {
    if (!taskId || !sessionId) return;
    // Only update if changed (avoid disk writes on every message)
    if (this.taskToSession.get(taskId) === sessionId) return;
    this.taskToSession.set(taskId, sessionId);
    await this.persist();
  }

  get(taskId: string): string | undefined {
    return this.taskToSession.get(taskId);
  }

  private async persist(): Promise<void> {
    const dir = this.filePath.substring(
      0,
      Math.max(this.filePath.lastIndexOf("/"), this.filePath.lastIndexOf("\\"))
    );
    if (dir && !this.deps.existsSync(dir)) {
      this.deps.mkdirSync(dir, { recursive: true });
    }
    const obj: Record<string, string> = {};
    for (const [k, v] of this.taskToSession.entries()) obj[k] = v;
    await this.deps.writeFile(this.filePath, JSON.stringify(obj, null, 2));
  }
}
