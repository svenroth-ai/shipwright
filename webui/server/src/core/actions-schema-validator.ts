/*
 * Actions.json structural validator.
 *
 * Iterate 3 section 03 — plan.md § 7 O24. The loader is pure I/O; this
 * validator catches the five schema failure modes that the external
 * review flagged:
 *   1. Duplicate action ids
 *   2. Invalid defaults.autonomy enum
 *   3. Empty phases[]
 *   4. Missing required action fields (command_template on external_launch)
 *   5. Unsupported modal_fields entry (stale `complexity:radio:...` per AD-03.13)
 *
 * Placeholder-level validation (unknown placeholder tokens inside
 * command_template) is the responsibility of
 * `actions-substitute.validateTemplate`. This module deliberately stays
 * structure-only so the two concerns compose.
 *
 * Returns a list of errors rather than throwing — the route layer
 * decides how to surface them (HTTP 400 with structured code on the
 * first error, or aggregated diagnostics for the GET /actions route).
 */

import type { ResolvedActions } from "./project-actions-loader.js";

export type SchemaErrorCode =
  | "duplicate_action_id"
  | "invalid_autonomy_enum"
  | "empty_phases"
  | "missing_command_template"
  | "unsupported_modal_field"
  | "invalid_preview_enabled";

export interface SchemaError {
  code: SchemaErrorCode;
  [key: string]: unknown;
}

/**
 * Modal field allowlist (per AD-03.13). `complexity:radio:small,medium,large`
 * is explicitly removed; the new iterate modal uses complexity auto-detect
 * at skill-invocation time, not a pre-launch field.
 */
const SUPPORTED_MODAL_FIELDS = new Set([
  "title",
  "phase",
  "description",
  "autonomy",
  "project", // read-only strip or dropdown — not user-input but may appear in modal_fields for the `all projects` branch
]);

const VALID_AUTONOMY = new Set(["guided", "autonomous"]);

export function validateActionsSchema(
  actions: ResolvedActions,
): SchemaError[] {
  const errors: SchemaError[] = [];

  // 1. Duplicate action ids.
  const ids = new Set<string>();
  for (const a of actions.actions) {
    if (ids.has(a.id)) {
      errors.push({ code: "duplicate_action_id", id: a.id });
    }
    ids.add(a.id);
  }

  // 2. Invalid defaults.autonomy enum.
  if (!VALID_AUTONOMY.has(actions.defaults.autonomy)) {
    errors.push({
      code: "invalid_autonomy_enum",
      value: actions.defaults.autonomy,
    });
  }

  // 3. Empty phases[].
  if (!Array.isArray(actions.phases) || actions.phases.length === 0) {
    errors.push({ code: "empty_phases" });
  }

  // 4. Missing command_template on external_launch kind.
  for (const a of actions.actions) {
    if (a.kind === "external_launch") {
      if (typeof a.command_template !== "string" || a.command_template.trim() === "") {
        errors.push({ code: "missing_command_template", actionId: a.id });
      }
    }
  }

  // 5. Unsupported modal_fields entries.
  for (const a of actions.actions) {
    if (!a.modal_fields) continue;
    for (const field of a.modal_fields) {
      // Field may include a type suffix like `complexity:radio:...`; treat
      // anything with a colon as type-tagged and lookup by the bare name.
      const bare = field.split(":")[0];
      if (!SUPPORTED_MODAL_FIELDS.has(bare) || field !== bare) {
        // `field !== bare` catches `complexity:radio:...` even if `complexity`
        // alone were somehow in the allowlist (it isn't, but defense-in-depth).
        errors.push({
          code: "unsupported_modal_field",
          actionId: a.id,
          field,
        });
      }
    }
  }

  // preview.enabled type guard (not in the review list, but a JSON-
  // coerced junk value here would silently break the route's
  // precedence chain).
  const previewEnabled = actions.preview?.enabled;
  if (
    previewEnabled !== true &&
    previewEnabled !== false &&
    previewEnabled !== "auto"
  ) {
    errors.push({
      code: "invalid_preview_enabled",
      value: previewEnabled as unknown,
    });
  }

  return errors;
}
