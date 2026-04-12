import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createClassifyRoutes } from "./classify.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };

// Mock the intent-classifier module
vi.mock("../bridge/intent-classifier.js", async () => {
  const actual = await vi.importActual<typeof import("../bridge/intent-classifier.js")>(
    "../bridge/intent-classifier.js"
  );
  return {
    ...actual,
    classifyIntent: vi.fn(async () => ({ intent: "feature", affected_frs: ["FR-01"] })),
    classifyComplexity: vi.fn(async () => ({ complexity: "medium" })),
    classifyPhase: vi.fn(async () => ({ phase: "design", confidence: 0.8 })),
  };
});

function setup() {
  const projectManager = { getById: vi.fn((id: string) => id === "p1" ? mockProject : undefined) } as any;
  const app = new Hono();
  app.onError(errorHandler);
  app.route("/", createClassifyRoutes(projectManager));
  return { app };
}

describe("Classify Routes", () => {
  it("POST /api/projects/:id/classify returns intent and complexity", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "Add dark mode" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.intent).toBe("feature");
    expect(body.data.complexity).toBe("medium");
  });

  it("POST /api/projects/:id/classify returns phase + phase_confidence", async () => {
    const { app } = setup();
    const res = await app.request("/api/projects/p1/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: "design a landing page" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.data.phase).toBe("design");
    expect(body.data.phase_confidence).toBe(0.8);
  });
});
