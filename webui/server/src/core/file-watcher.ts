export interface FileWatcherDeps {
  watch: (paths: string | string[], options?: object) => FSWatcherLike;
}

export interface FSWatcherLike {
  on: (event: string, callback: (...args: unknown[]) => void) => FSWatcherLike;
  close: () => Promise<void> | void;
}

export class FileWatcher {
  private watchers = new Map<string, FSWatcherLike>();
  private debounceTimers = new Map<string, ReturnType<typeof setTimeout>>();

  constructor(private deps: FileWatcherDeps) {}

  watchProject(
    projectId: string,
    projectDir: string,
    onChange: (type: string, path: string) => void
  ): void {
    const patterns = [
      `${projectDir}/shipwright_events.jsonl`,
      `${projectDir}/shipwright_*_config.json`,
    ];

    const watcher = this.deps.watch(patterns, { ignoreInitial: true });
    watcher.on("change", (changedPath: unknown) => {
      const pathStr = String(changedPath);
      const type = pathStr.includes("events.jsonl") ? "event" : "config";
      this.debounce(projectId, () => onChange(type, pathStr));
    });
    watcher.on("add", (changedPath: unknown) => {
      const pathStr = String(changedPath);
      const type = pathStr.includes("events.jsonl") ? "event" : "config";
      this.debounce(projectId, () => onChange(type, pathStr));
    });

    this.watchers.set(projectId, watcher);
  }

  unwatchProject(projectId: string): void {
    const watcher = this.watchers.get(projectId);
    if (watcher) {
      watcher.close();
      this.watchers.delete(projectId);
    }
    const timer = this.debounceTimers.get(projectId);
    if (timer) {
      clearTimeout(timer);
      this.debounceTimers.delete(projectId);
    }
  }

  unwatchAll(): void {
    for (const [id] of this.watchers) {
      this.unwatchProject(id);
    }
  }

  private debounce(projectId: string, callback: () => void): void {
    const existing = this.debounceTimers.get(projectId);
    if (existing) clearTimeout(existing);
    this.debounceTimers.set(
      projectId,
      setTimeout(() => {
        this.debounceTimers.delete(projectId);
        callback();
      }, 300)
    );
  }
}
