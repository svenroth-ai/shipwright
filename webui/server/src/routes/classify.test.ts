import { describe, it, expect, vi } from "vitest";
import { Hono } from "hono";
import { createClassifyRoutes } from "./classify.js";
import { errorHandler } from "../middleware/error-handler.js";

const mockProject = { id: "p1", name: "Test", path: "/tmp", profile: "default", status: "active", createdAt: "2026-01-01", lastActive: "2026-01-01" };

// Mock the intent-classifier module
vi.mock("../bridge/intent-classifier.js", () => ({
  classifyIntent: vi.fn(async () => ({ intent: "feature", affected_frs: ["FR-01"] })),
  classifyComplexity: vi.fn(async () => ({ complexity: "medium" })),
}));

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
});
