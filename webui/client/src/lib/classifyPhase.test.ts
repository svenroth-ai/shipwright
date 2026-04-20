import { describe, it, expect } from "vitest";

import { classifyPhase } from "./classifyPhase";

const SHIPWRIGHT_PHASES = [
  "project",
  "design",
  "plan",
  "build",
  "test",
  "deploy",
  "changelog",
  "compliance",
  "security",
];

const CUSTOM_PHASES = ["implement", "verify"];

describe("classifyPhase", () => {
  it("returns null for empty input", () => {
    expect(classifyPhase("", SHIPWRIGHT_PHASES)).toBeNull();
    expect(classifyPhase("   ", SHIPWRIGHT_PHASES)).toBeNull();
  });

  it("returns null when the phases allowlist is empty", () => {
    expect(classifyPhase("fix login bug", [])).toBeNull();
  });

  it("maps 'fix', 'build', 'implement' keywords to Shipwright `build` phase", () => {
    expect(classifyPhase("Fix login redirect bug", SHIPWRIGHT_PHASES)).toBe("build");
    expect(classifyPhase("Build the dashboard", SHIPWRIGHT_PHASES)).toBe("build");
    expect(classifyPhase("Implement RBAC", SHIPWRIGHT_PHASES)).toBe("build");
  });

  it("maps 'design' / 'mockup' keywords to Shipwright `design` phase", () => {
    expect(classifyPhase("Design the auth flow", SHIPWRIGHT_PHASES)).toBe("design");
    expect(classifyPhase("Mock a new wireframe", SHIPWRIGHT_PHASES)).toBe("design");
  });

  it("maps 'test' / 'playwright' / 'qa' keywords to Shipwright `test` phase", () => {
    expect(classifyPhase("Write playwright coverage for checkout", SHIPWRIGHT_PHASES)).toBe("test");
    expect(classifyPhase("QA run on staging", SHIPWRIGHT_PHASES)).toBe("test");
  });

  it("supports custom phase ids (project-level overrides)", () => {
    // Shipwright's 'build' maps to the custom 'implement' phase and 'test' maps to 'verify'.
    expect(classifyPhase("Implement the migration script", CUSTOM_PHASES)).toBe("implement");
    expect(classifyPhase("Verify test coverage", CUSTOM_PHASES)).toBe("verify");
  });

  it("returns null when nothing matches any rule", () => {
    expect(classifyPhase("asdfghjkl qwerty", SHIPWRIGHT_PHASES)).toBeNull();
  });

  it("is case-insensitive on both the input text and the phase id", () => {
    expect(classifyPhase("DEPLOY to prod", SHIPWRIGHT_PHASES)).toBe("deploy");
    expect(classifyPhase("deploy to prod", ["Deploy"])).toBe("Deploy");
  });
});
