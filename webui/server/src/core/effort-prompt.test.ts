import { describe, it, expect } from "vitest";
import { wrapWithEffort, coerceEffort } from "./effort-prompt.js";

describe("wrapWithEffort", () => {
  it("returns input unchanged for low", () => {
    expect(wrapWithEffort("hello", "low")).toBe("hello");
  });

  it("prepends /think for medium", () => {
    expect(wrapWithEffort("fix the bug", "medium")).toBe("/think\n\nfix the bug");
  });

  it("prepends /think hard for high", () => {
    expect(wrapWithEffort("design the auth layer", "high")).toBe(
      "/think hard\n\ndesign the auth layer",
    );
  });

  it("prepends /ultrathink for max", () => {
    expect(wrapWithEffort("plan migration strategy", "max")).toBe(
      "/ultrathink\n\nplan migration strategy",
    );
  });

  it("returns input unchanged for unknown effort value", () => {
    expect(wrapWithEffort("hello", "banana")).toBe("hello");
  });

  it("returns input unchanged when effort is undefined", () => {
    expect(wrapWithEffort("hello", undefined)).toBe("hello");
  });

  it("preserves empty input", () => {
    expect(wrapWithEffort("", "max")).toBe("/ultrathink\n\n");
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
