import { describe, it, expect } from "vitest";
import { wrapWithEffort, coerceEffort } from "./effort-prompt.js";

describe("wrapWithEffort (iterate 13.1 — Claude CLI 2.1.1 removed /think slash commands)", () => {
  it("returns input unchanged for low", () => {
    expect(wrapWithEffort("hello", "low")).toBe("hello");
  });

  it("returns input unchanged for medium (was /think, removed in CLI 2.1.1)", () => {
    expect(wrapWithEffort("fix the bug", "medium")).toBe("fix the bug");
  });

  it("returns input unchanged for high (was /think hard, removed in CLI 2.1.1)", () => {
    expect(wrapWithEffort("design the auth layer", "high")).toBe("design the auth layer");
  });

  it("returns input unchanged for max (was /ultrathink, removed in CLI 2.1.1)", () => {
    expect(wrapWithEffort("plan migration strategy", "max")).toBe("plan migration strategy");
  });

  it("returns input unchanged for unknown effort value", () => {
    expect(wrapWithEffort("hello", "banana")).toBe("hello");
  });

  it("returns input unchanged when effort is undefined", () => {
    expect(wrapWithEffort("hello", undefined)).toBe("hello");
  });

  it("preserves empty input", () => {
    expect(wrapWithEffort("", "max")).toBe("");
  });
});

describe("coerceEffort", () => {
  it("accepts the four valid levels", () => {
    expect(coerceEffort("low")).toBe("low");
    expect(coerceEffort("medium")).toBe("medium");
    expect(coerceEffort("high")).toBe("high");
    expect(coerceEffort("max")).toBe("max");
  });

  it("returns undefined for invalid values", () => {
    expect(coerceEffort("ultra")).toBeUndefined();
    expect(coerceEffort(42)).toBeUndefined();
    expect(coerceEffort(undefined)).toBeUndefined();
    expect(coerceEffort(null)).toBeUndefined();
  });
});
