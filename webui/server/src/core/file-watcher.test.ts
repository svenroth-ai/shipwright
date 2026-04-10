import { describe, it, expect, vi } from "vitest";
import { FileWatcher } from "./file-watcher.js";
import type { FileWatcherDeps, FSWatcherLike } from "./file-watcher.js";

function createMockWatcher(): FSWatcherLike & { handlers: Record<string, Function[]> } {
  const handlers: Record<string, Function[]> = {};
  return {
    handlers,
    on: vi.fn(function (this: any, event: string, cb: Function) {
      if (!handlers[event]) handlers[event] = [];
      handlers[event].push(cb);
      return this;
    }),
    close: vi.fn(async () => {}),
  };
}

describe("FileWatcher", () => {
  it("emits event type for events file change", async () => {
    const mockW = createMockWatcher();
    const deps: FileWatcherDeps = { watch: vi.fn(() => mockW) };
    const fw = new FileWatcher(deps);
    const onChange = vi.fn();
    fw.watchProject("p1", "/proj", onChange);

    // Simulate change event
    mockW.handlers["change"]?.[0]("/proj/shipwright_events.jsonl");
    await new Promise((r) => setTimeout(r, 350));
    expect(onChange).toHaveBeenCalledWith("event", "/proj/shipwright_events.jsonl");
  });

  it("emits config type for config file change", async () => {
    const mockW = createMockWatcher();
    const deps: FileWatcherDeps = { watch: vi.fn(() => mockW) };
    const fw = new FileWatcher(deps);
    const onChange = vi.fn();
    fw.watchProject("p1", "/proj", onChange);

    mockW.handlers["change"]?.[0]("/proj/shipwright_build_config.json");
    await new Promise((r) => setTimeout(r, 350));
    expect(onChange).toHaveBeenCalledWith("config", "/proj/shipwright_build_config.json");
  });

  it("debounces rapid changes within 300ms", async () => {
    const mockW = createMockWatcher();
    const deps: FileWatcherDeps = { watch: vi.fn(() => mockW) };
    const fw = new FileWatcher(deps);
    const onChange = vi.fn();
    fw.watchProject("p1", "/proj", onChange);

    mockW.handlers["change"]?.[0]("/proj/shipwright_events.jsonl");
    mockW.handlers["change"]?.[0]("/proj/shipwright_events.jsonl");
    mockW.handlers["change"]?.[0]("/proj/shipwright_events.jsonl");
    await new Promise((r) => setTimeout(r, 350));
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("unwatchProject closes watcher and clears timer", () => {
    const mockW = createMockWatcher();
    const deps: FileWatcherDeps = { watch: vi.fn(() => mockW) };
    const fw = new FileWatcher(deps);
    fw.watchProject("p1", "/proj", vi.fn());
    fw.unwatchProject("p1");
    expect(mockW.close).toHaveBeenCalled();
  });

  it("unwatchAll closes all watchers", () => {
    const mockW1 = createMockWatcher();
    const mockW2 = createMockWatcher();
    let callCount = 0;
    const deps: FileWatcherDeps = {
      watch: vi.fn(() => (callCount++ === 0 ? mockW1 : mockW2)),
    };
    const fw = new FileWatcher(deps);
    fw.watchProject("p1", "/proj1", vi.fn());
    fw.watchProject("p2", "/proj2", vi.fn());
    fw.unwatchAll();
    expect(mockW1.close).toHaveBeenCalled();
    expect(mockW2.close).toHaveBeenCalled();
  });
});
