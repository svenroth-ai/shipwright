import { describe, it, expect } from "vitest";
import { app } from "./index.js";

describe("GET /api/health", () => {
  it("returns 200 with status ok, version, and uptime", async () => {
    const res = await app.request("/api/health");
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(typeof body.version).toBe("string");
    expect(typeof body.uptime).toBe("number");
  });
});

describe("Unknown routes", () => {
  it("returns 404 with JSON error body", async () => {
    const res = await app.request("/api/nonexistent");
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body).toHaveProperty("error");
  });
});

describe("CORS", () => {
  it("includes CORS headers for localhost origins", async () => {
    const res = await app.request("/api/health", {
      headers: { Origin: "http://localhost:5173" },
    });
    expect(res.headers.get("Access-Control-Allow-Origin")).toBe(
      "http://localhost:5173"
    );
  });
});

describe("Error handling", () => {
  it("produces correct JSON for thrown AppError instances", async () => {
    // The /api/nonexistent route triggers a 404 AppError via the notFound handler
    const res = await app.request("/api/nonexistent");
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });
});
