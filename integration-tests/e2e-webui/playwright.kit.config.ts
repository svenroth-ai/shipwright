import { defineConfig } from "@playwright/test";

// Runs only the design-kit render spec. testDir is the repository root so the report names the spec by its repo-relative
// path, which is how the F0.5 gate ties a staged result to the runner command.
export default defineConfig({
  testDir: "../..",
  testMatch: "**/e2e-webui/tests/unit/design-kit-reply-board.spec.ts",
  testIgnore: ["**/node_modules/**"],
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
});
