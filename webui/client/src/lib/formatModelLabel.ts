/**
 * Iterate 14.6 — format a Claude CLI model id into a human label.
 *
 * Inputs look like `claude-opus-4-5-20251101` (real CLI system/init output)
 * or `claude-sonnet-4-6` (shorthand). We extract family + major.minor and
 * title-case the family. Missing / malformed inputs fall back to "Claude".
 *
 * Examples:
 *   claude-opus-4-5-20251101   → "Opus 4.5"
 *   claude-sonnet-4-6          → "Sonnet 4.6"
 *   claude-haiku-4-5           → "Haiku 4.5"
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
