/*
 * Reserved project-id constants.
 *
 * Iterate 3 section 02 — the synthesized pseudo-project bucket for tasks
 * without an explicit projectId (or whose projectId points at a deleted
 * project). Server-side ADR-037 keeps this row out of projects.json; the
 * client imports the literal from here so no component hardcodes the
 * string. Server has its own copy in core/project-manager.ts
 * (intentional duplication per conventions.md:14).
 */

export const UNASSIGNED_PROJECT_ID = "unassigned";
