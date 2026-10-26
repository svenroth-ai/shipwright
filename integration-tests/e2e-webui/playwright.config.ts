import { defineConfig } from "@playwright/test";

// The overall budget is SHIPWRIGHT_E2E_MAX_MINUTES (required, no default): the e2e spec sets its own test
// timeout from it once the config is loaded. The unit project keeps Playwright's default test timeout.
export default defineConfig({
  testDir: "tests",
  use: { actionTimeout: 60_000, navigationTimeout: 120_000 },
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  projects: [
    { name: "e2e", testMatch: "e2e.spec.ts" },
    { name: "unit", testMatch: "unit/*.spec.ts" },
  ],
});
