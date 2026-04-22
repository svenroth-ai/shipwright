/*
 * Regression guard for the schema validator against O24's 5 failure modes.
 * These are the documented negative cases the GET /actions route must
 * reject with a typed SchemaError.
 */

import { describe, it, expect } from "vitest";

import { validateActionsSchema } from "../core/actions-schema-validator.js";
import {
  loadBundledDefault,
  clearActionsCache,
} from "../core/project-actions-loader.js";

describe("validateActionsSchema — bundled default passes clean", () => {
  it("produces zero errors for the shipped default-actions.json", () => {
    clearActionsCache();
    const bundled = loadBundledDefault();
    expect(validateActionsSchema(bundled)).toEqual([]);
  });
});

describe("validateActionsSchema — 5 negative cases (O24)", () => {
  it("1. duplicate action ids → {code:'duplicate_action_id', id}", () => {
    const errs = validateActionsSchema({
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "new-task",
          label: "a",
          kind: "external_launch",
          command_template: "x",
        },
        {
          id: "new-task",
          label: "b",
          kind: "external_launch",
          command_template: "y",
        },
      ],
      phases: [{ id: "build", label: "Build" }],
      preview: { enabled: false },
    });
    const dup = errs.find((e) => e.code === "duplicate_action_id");
    expect(dup).toBeDefined();
    expect(dup?.id).toBe("new-task");
  });

  it("2. invalid defaults.autonomy enum → {code:'invalid_autonomy_enum'}", () => {
    const errs = validateActionsSchema({
      schemaVersion: 1,
      defaults: { autonomy: "wild" as unknown as "guided" },
      actions: [
        {
          id: "a",
          label: "a",
          kind: "external_launch",
          command_template: "x",
        },
      ],
      phases: [{ id: "build", label: "Build" }],
      preview: { enabled: false },
    });
    const bad = errs.find((e) => e.code === "invalid_autonomy_enum");
    expect(bad).toBeDefined();
    expect(bad?.value).toBe("wild");
  });

  it("3. empty phases[] → {code:'empty_phases'}", () => {
    const errs = validateActionsSchema({
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "a",
          label: "a",
          kind: "external_launch",
          command_template: "x",
        },
      ],
      phases: [],
      preview: { enabled: false },
    });
    expect(errs.some((e) => e.code === "empty_phases")).toBe(true);
  });

  it("4. missing command_template on external_launch → {code:'missing_command_template', actionId}", () => {
    const errs = validateActionsSchema({
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "a",
          label: "a",
          kind: "external_launch",
          command_template: "" as string,
        },
      ],
      phases: [{ id: "build", label: "Build" }],
      preview: { enabled: false },
    });
    const err = errs.find((e) => e.code === "missing_command_template");
    expect(err).toBeDefined();
    expect(err?.actionId).toBe("a");
  });

  it("5. stale complexity modal field → {code:'unsupported_modal_field'}", () => {
    const errs = validateActionsSchema({
      schemaVersion: 1,
      defaults: { autonomy: "guided" },
      actions: [
        {
          id: "a",
          label: "a",
          kind: "external_launch",
          command_template: "x",
          modal_fields: ["title", "complexity:radio:small,medium,large"],
        },
      ],
      phases: [{ id: "build", label: "Build" }],
      preview: { enabled: false },
    });
    const err = errs.find((e) => e.code === "unsupported_modal_field");
    expect(err).toBeDefined();
    expect(err?.field).toBe("complexity:radio:small,medium,large");
  });
});
