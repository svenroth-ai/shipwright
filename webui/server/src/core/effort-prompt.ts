/**
 * Effort wire-through — iterate 9, revised iterate 13.1.
 *
 * History: iterate 9 mapped effort levels to Claude Code's `/think`,
 * `/think hard`, and `/ultrathink` slash commands, which previously
 * controlled thinking depth. Claude Code CLI 2.1.1 REMOVED those slash
 * commands (verified via `claude --help` — no `--thinking` flag, and
 * the system/init slash_commands list no longer contains them). Sending
 * `/think\n\n<prompt>` now produces a server error:
 *     "Unknown slash command: think"
 *
 * Until Claude Code exposes thinking depth again (either as a CLI flag
 * or as new slash commands), all effort levels route through unchanged.
 * The toolbar effort selector still works cosmetically but has no
 * runtime effect. Revisit when the CLI adds a `--thinking-budget` flag
 * or re-introduces `/think` style commands.
 */

export type EffortLevel = "low" | "medium" | "high" | "max";

const VALID: readonly EffortLevel[] = ["low", "medium", "high", "max"] as const;

const PREFIXES: Record<EffortLevel, string> = {
  low: "",
  medium: "",
  high: "",
  max: "",
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
