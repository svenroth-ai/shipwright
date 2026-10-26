import { defineConfig } from "@playwright/test";

// No timeout here on purpose: the overall budget is SHIPWRIGHT_E2E_MAX_MINUTES, enforced (and required,
// with no default) by the spec itself.
export default defineConfig({
  testDir: "tests",
  timeout: 0,
  workers: 1,
  fullyParallel: false,
  reporter: [["list"]],
  projects: [
    { name: "e2e", testMatch: "e2e.spec.ts" },
    { name: "unit", testMatch: "unit/*.spec.ts" },
  ],
});
