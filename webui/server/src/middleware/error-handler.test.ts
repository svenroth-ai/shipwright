import { describe, it, expect } from "vitest";
import { Hono } from "hono";
import { AppError, errorHandler } from "./error-handler.js";

describe("AppError", () => {
  it("creates error with status code", () => {
    const err = new AppError("Not found", 404);
    expect(err.message).toBe("Not found");
    expect(err.statusCode).toBe(404);
    expect(err).toBeInstanceOf(Error);
  });

  it("supports optional detail field", () => {
    const err = new AppError("Bad request", 400, "Email is required");
    expect(err.detail).toBe("Email is required");
  });
});

describe("errorHandler", () => {
  function createTestApp() {
    const app = new Hono();
    app.onError(errorHandler);
    return app;
  }

  it("returns correct JSON for AppError with 404", async () => {
    const app = createTestApp();
    app.get("/test", () => {
      throw new AppError("Resource not found", 404);
    });

    const res = await app.request("/test");
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body).toEqual({ error: "Resource not found" });
  });

  it("returns correct JSON for AppError with 400 and detail", async () => {
    const app = createTestApp();
    app.get("/test", () => {
      throw new AppError("Validation failed", 400, "Email is required");
    });

    const res = await app.request("/test");
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body).toEqual({
      error: "Validation failed",
      detail: "Email is required",
    });
  });

  it("returns 500 with generic message for unknown errors", async () => {
    const app = createTestApp();
    app.get("/test", () => {
      throw new Error("something broke");
    });

    const res = await app.request("/test");
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body).toEqual({ error: "Internal server error" });
  });
});
