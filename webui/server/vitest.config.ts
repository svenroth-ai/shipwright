import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  test: {
    include: ["**/*.test.ts"],
    threads: true,
  },
  resolve: {
    alias: {
      "@shared": path.resolve(__dirname, "../client/src/types"),
    },
  },
});
