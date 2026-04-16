/**
 * Iterate 14.6 — format a Claude CLI model id into a human label.
 *
 * Inputs look like `claude-opus-4-5-20251101` (real CLI system/init output),
 * `claude-sonnet-4-6` (shorthand), or `claude-opus-4-7`. We extract family +
 * major.minor and title-case the family. Missing / malformed inputs fall
 * back to "Claude".
 *
 * Iterate 14.10 — strict major-minor regex restored. 14.9 loosened it to
 * tolerate a missing minor version for the (wrong) `claude-opus-7` guess,
 * but the real CLI id is `claude-opus-4-7` which matches the strict
 * pattern just fine.
 *
 * Examples:
 *   claude-opus-4-5-20251101   → "Opus 4.5"
 *   claude-sonnet-4-6          → "Sonnet 4.6"
 *   claude-haiku-4-5           → "Haiku 4.5"
 *   claude-opus-4-7            → "Opus 4.7"
 *   undefined                  → "Claude"
 *   "gpt-5"                    → "Claude"
 */
export function formatModelLabel(modelId?: string | null): string {
  if (!modelId) return 'Claude';
  const m = modelId.match(/claude-(opus|sonnet|haiku)-(\d+)-(\d+)/i);
  if (!m) return 'Claude';
  const family = m[1].charAt(0).toUpperCase() + m[1].slice(1).toLowerCase();
  return `${family} ${m[2]}.${m[3]}`;
}
