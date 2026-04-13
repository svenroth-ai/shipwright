/**
 * Effort wire-through — iterate 9.
 *
 * Claude Code CLI does not expose a `--thinking` or `--effort` flag. In the
 * VS Code Claude extension, "Max" maps to the `/ultrathink` slash command
 * and lesser levels map to `/think` / `/think hard`. These prefixes are just
 * text that Claude recognizes as a thinking-depth instruction — they work
 * equally well when prepended to any prompt, initial or follow-up.
 *
 * This module is the single source of truth for (a) the valid effort level
 * set and (b) the text prefix each level maps to. Used by both the `/tasks`
 * and `/chat` routes.
 */

export type EffortLevel = "low" | "medium" | "high" | "max";

const VALID: readonly EffortLevel[] = ["low", "medium", "high", "max"] as const;

const PREFIXES: Record<EffortLevel, string> = {
  low: "",
  medium: "/think",
  high: "/think hard",
  max: "/ultrathink",
};

/**
 * Wrap `text` with the thinking-depth prefix for the given effort level.
 * Unknown / undefined effort returns `text` unchanged. Low returns `text`
 * unchanged too (default CLI behavior is already fine for low-effort work).
 */
export function wrapWithEffort(text: string, effort: string | undefined): string {
  if (!effort) return text;
  if (!(VALID as readonly string[]).includes(effort)) return text;
  const prefix = PREFIXES[effort as EffortLevel];
  if (!prefix) return text;
  return `${prefix}\n\n${text}`;
}

/**
 * Validate an incoming effort value from an API request body.
 * Returns the strongly-typed level or undefined when the input is not a
 * recognized effort string. Callers treat `undefined` as "no wrapping".
 */
export function coerceEffort(raw: unknown): EffortLevel | undefined {
  if (typeof raw !== "string") return undefined;
  if ((VALID as readonly string[]).includes(raw)) return raw as EffortLevel;
  return undefined;
}
