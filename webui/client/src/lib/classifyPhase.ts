/*
 * Tiny pure helper that maps a free-text title to a phase id from the
 * project's `actions.phases[]` allowlist (iterate 3 section 02 / ADR-039).
 *
 * The classifier is deliberately naive — one-shot keyword matching, no
 * embeddings, no fuzzy scoring. Its job is to seed the phase dropdown
 * sensibly from the title so the user doesn't have to click for the
 * 80%-happy-path ("Fix login bug" → build, "Design dashboard" → design).
 * When in doubt, return `null` and let NewIssueModal fall back to the
 * first phase in the schema (O23).
 *
 * Keyword rules shadow the mockup's `updatePhaseDetection()` regex set
 * (new-task-dialog.html:764-771). They are intentionally keyed against
 * verb-family stems rather than exact phase ids because a project with
 * custom phases (`["implement", "verify"]` per spec 51a) still wants
 * title-to-phase auto-detect — we only resolve phase-name → phase-id
 * at the tail of the function.
 */

// Keyword → generic phase family. Intersected with the project's actual
// phase ids in classifyPhase() so custom phase names still match.
const RULES: Array<{ re: RegExp; family: string[] }> = [
  { re: /\b(implement|add|build|code|wire|fix|refactor)\b/i, family: ["build", "implement"] },
  { re: /\b(design|mock|mockup|wireframe|layout|ux|ui)\b/i, family: ["design"] },
  { re: /\b(plan|spec|decompose|refine|requirements)/i, family: ["plan", "requirements", "project"] },
  { re: /\b(test|coverage|playwright|vitest|verify|qa)/i, family: ["test", "verify"] },
  { re: /\b(deploy|release|ship|rollout)/i, family: ["deploy", "release"] },
  { re: /\b(security|vuln|audit|cve|xss|sql.injection)/i, family: ["security", "audit"] },
  { re: /\b(changelog|release.notes)/i, family: ["changelog"] },
  { re: /\b(compliance|governance|sbom|traceability)/i, family: ["compliance"] },
];

/**
 * Classify a title against the given phase id allowlist. Returns the
 * first matching phase id, or null when nothing resonates (NewIssueModal
 * then falls back to phases[0]).
 */
export function classifyPhase(
  text: string,
  phases: readonly string[],
): string | null {
  if (!text || phases.length === 0) return null;
  const haystack = text.trim();
  if (!haystack) return null;

  for (const rule of RULES) {
    if (rule.re.test(haystack)) {
      // Prefer a phase whose id matches any family keyword. Case-insensitive
      // comparison so "Build" vs "build" vs "BUILD" all resolve.
      for (const fam of rule.family) {
        const hit = phases.find((p) => p.toLowerCase() === fam.toLowerCase());
        if (hit) return hit;
      }
    }
  }
  return null;
}
