import { describe, it, expect } from "vitest";

import {
  parseClaudeVersion,
  isSupported,
  MIN_SUPPORTED_CLI,
} from "./cli-compat.js";

describe("parseClaudeVersion", () => {
  it("extracts semver from '2.1.114 (Claude Code)'", () => {
    expect(parseClaudeVersion("2.1.114 (Claude Code)")).toEqual({
      major: 2,
      minor: 1,
      patch: 114,
    });
  });

  it("tolerates pre-release suffixes and extracts the x.y.z", () => {
    expect(parseClaudeVersion("2.2.0-beta.3")).toEqual({ major: 2, minor: 2, patch: 0 });
  });

  it("returns null on garbage", () => {
    expect(parseClaudeVersion("")).toBeNull();
    expect(parseClaudeVersion("not a version")).toBeNull();
  });
});

describe("isSupported", () => {
  it("accepts the pinned minimum", () => {
    expect(isSupported(parseClaudeVersion(MIN_SUPPORTED_CLI))).toBe(true);
  });

  it("accepts a higher patch", () => {
    expect(isSupported(parseClaudeVersion("2.1.200"))).toBe(true);
  });

  it("accepts a higher minor", () => {
    expect(isSupported(parseClaudeVersion("2.2.0"))).toBe(true);
  });

  it("rejects an older patch", () => {
    expect(isSupported(parseClaudeVersion("2.1.50"))).toBe(false);
  });

  it("rejects an older major", () => {
    expect(isSupported(parseClaudeVersion("1.9.9"))).toBe(false);
  });

  it("rejects a future major that outruns MAX_SUPPORTED_CLI_MAJOR", () => {
    expect(isSupported(parseClaudeVersion("3.0.0"))).toBe(false);
  });

  it("rejects null", () => {
    expect(isSupported(null)).toBe(false);
  });
});
