import { describe, it, expect, vi } from "vitest";
import { SSEManager } from "./sse-manager.js";
import type { SSEEvent } from "../../../client/src/types/sse.js";

function mockController(): ReadableStreamDefaultController & { enqueued: Uint8Array[] } {
  const enqueued: Uint8Array[] = [];
  return {
    enqueued,
    enqueue: vi.fn((data: Uint8Array) => enqueued.push(data)),
    close: vi.fn(),
    desiredSize: null,
    error: vi.fn(),
  };
}

describe("SSEManager", () => {
  it("addClient increases count", () => {
    const mgr = new SSEManager();
    mgr.addClient("c1", mockController());
    expect(mgr.getClientCount()).toBe(1);
  });

  it("two clients -> count 2", () => {
    const mgr = new SSEManager();
    mgr.addClient("c1", mockController());
    mgr.addClient("c2", mockController());
    expect(mgr.getClientCount()).toBe(2);
  });

  it("removeClient decreases count", () => {
    const mgr = new SSEManager();
    mgr.addClient("c1", mockController());
    mgr.removeClient("c1");
    expect(mgr.getClientCount()).toBe(0);
  });

  it("removeClient for non-existent does not throw", () => {
    const mgr = new SSEManager();
    expect(() => mgr.removeClient("nonexistent")).not.toThrow();
  });

  it("broadcast writes SSE-formatted data to all clients", () => {
    const mgr = new SSEManager();
    const ctrl1 = mockController();
    const ctrl2 = mockController();
    mgr.addClient("c1", ctrl1);
    mgr.addClient("c2", ctrl2);

    const event: SSEEvent = {
      type: "task:created",
      payload: { id: "t1" },
      timestamp: "2026-01-01T00:00:00Z",
    };
    mgr.broadcast(event);
    expect(ctrl1.enqueue).toHaveBeenCalled();
    expect(ctrl2.enqueue).toHaveBeenCalled();
  });

  it("broadcast format contains event: and data:", () => {
    const mgr = new SSEManager();
    const ctrl = mockController();
    mgr.addClient("c1", ctrl);

    mgr.broadcast({
      type: "task:updated",
      payload: { status: "done" },
      timestamp: "2026-01-01T00:00:00Z",
    });

    const text = new TextDecoder().decode(ctrl.enqueued[0]);
    expect(text).toContain("event: task:updated\n");
    expect(text).toContain("data: ");
    expect(text).toMatch(/\n\n$/);
  });

  it("broadcast removes client if enqueue throws", () => {
    const mgr = new SSEManager();
    const ctrl = mockController();
    (ctrl.enqueue as any).mockImplementation(() => {
      throw new Error("closed");
    });
    mgr.addClient("c1", ctrl);
    mgr.broadcast({
      type: "task:created",
      payload: {},
      timestamp: "2026-01-01T00:00:00Z",
    });
    expect(mgr.getClientCount()).toBe(0);
  });

  it("broadcastToProject sends to all", () => {
    const mgr = new SSEManager();
    const ctrl = mockController();
    mgr.addClient("c1", ctrl);
    mgr.broadcastToProject("p1", {
      type: "project:updated",
      payload: {},
      timestamp: "2026-01-01T00:00:00Z",
    });
    expect(ctrl.enqueue).toHaveBeenCalled();
  });

  it("closeAll empties client map", () => {
    const mgr = new SSEManager();
    mgr.addClient("c1", mockController());
    mgr.addClient("c2", mockController());
    mgr.closeAll();
    expect(mgr.getClientCount()).toBe(0);
  });
});
