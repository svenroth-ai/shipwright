import { describe, it, expect } from "vitest";
import { getPhaseStyle } from "./phaseStyle";

describe("getPhaseStyle", () => {
  it("returns the right palette for each canonical phase id", () => {
    expect(getPhaseStyle("compliance").dot).toContain("#0EA5E9");
    expect(getPhaseStyle("build").dot).toContain("#F59E0B");
    expect(getPhaseStyle("security").dot).toContain("#DC2626");
    expect(getPhaseStyle("adopt").dot).toContain("#64748B");
  });

  it("is case-insensitive on phase id", () => {
    expect(getPhaseStyle("Compliance")).toEqual(getPhaseStyle("compliance"));
    expect(getPhaseStyle("BUILD")).toEqual(getPhaseStyle("build"));
  });

  it("falls back to the build palette for unknown phase ids", () => {
    expect(getPhaseStyle("future-unknown")).toEqual(getPhaseStyle("build"));
    expect(getPhaseStyle("")).toEqual(getPhaseStyle("build"));
  });

  it("falls back to build when phase id is undefined", () => {
    expect(getPhaseStyle(undefined)).toEqual(getPhaseStyle("build"));
  });
});
