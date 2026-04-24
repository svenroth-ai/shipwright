import { describe, it, expect } from "vitest";
import { formatBindError } from "./bind-errors.js";

describe("formatBindError", () => {
  it("produces actionable message for EADDRINUSE", () => {
    const err = Object.assign(new Error("listen EADDRINUSE"), {
      code: "EADDRINUSE",
    });
    const result = formatBindError(err, 3847);
    expect(result.message).toContain("3847");
    expect(result.message).toContain("in use");
    expect(result.message.toLowerCase()).toMatch(/override|stop|port=/i);
    expect(result.exitCode).not.toBe(0);
  });

  it("produces distinct message for EACCES", () => {
    const err = Object.assign(new Error("listen EACCES"), { code: "EACCES" });
    const result = formatBindError(err, 80);
    expect(result.message).toContain("80");
    expect(result.message.toLowerCase()).toContain("permission");
    expect(result.exitCode).not.toBe(0);
  });

  it("handles EADDRNOTAVAIL distinctly", () => {
    const err = Object.assign(new Error("listen EADDRNOTAVAIL"), {
      code: "EADDRNOTAVAIL",
    });
    const result = formatBindError(err, 3847);
    expect(result.message).toContain("3847");
    expect(result.message.toLowerCase()).toContain("not available");
    expect(result.exitCode).not.toBe(0);
  });

  it("falls back loud on unknown bind errors", () => {
    const err = Object.assign(new Error("boom"), { code: "EWEIRD" });
    const result = formatBindError(err, 3847);
    expect(result.message).toContain("3847");
    expect(result.message.toLowerCase()).toMatch(/boom|failed/);
    expect(result.exitCode).not.toBe(0);
  });

  it("handles errors without a code", () => {
    const err = new Error("unexpected");
    const result = formatBindError(err, 3847);
    expect(result.exitCode).not.toBe(0);
    expect(result.message).toContain("3847");
  });

  it("never returns an empty message", () => {
    const err = new Error("");
    const result = formatBindError(err, 3847);
    expect(result.message.trim().length).toBeGreaterThan(0);
  });

  it("EADDRINUSE message matches a documented, stable pattern", () => {
    // This pattern is asserted by webui/CLAUDE.md + docs/guide.md §8.5.
    // Changing the format here requires updating those docs.
    const err = Object.assign(new Error("listen EADDRINUSE"), {
      code: "EADDRINUSE",
    });
    const result = formatBindError(err, 3848);
    expect(result.message).toMatch(/^Port 3848 is in use\. /);
    expect(result.message).toMatch(/PORT=<other>/);
  });
});
