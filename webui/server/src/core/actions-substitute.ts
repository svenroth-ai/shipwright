/*
 * Command-template placeholder substitution with per-shell escaping.
 *
 * Iterate 3 section 03 / plan.md § 2.2 — the SECURITY BOUNDARY for
 * command-template substitution. The placeholder allowlist is NOT the
 * security boundary on its own: it only guards template-shape
 * corruption. Actual protection against shell injection comes from the
 * per-shell escape discipline in this module (qPs / qCmd / qPosix,
 * re-exported from launcher.ts).
 *
 * Contract:
 *   substitutePlaceholders(template, ctx, shellForm) → string
 *     - Replaces every `{placeholder}` / `{placeholder?}` token with its
 *       shell-escaped substitution.
 *     - Unknown placeholder → throws InvalidPlaceholderError.
 *     - `{task.description?}` containing a newline → throws
 *       InvalidDescriptionError BEFORE substitution (the continuation
 *       prefix would break the single-line copy-paste flow).
 *     - `{task.phase}` that does NOT match ctx.allowedPhaseIds → throws
 *       UnknownPhaseError.
 *     - Unsupported shell form → throws UnsupportedShellError.
 *
 * Optional-suffix semantics:
 *   `{task.description?}` / `{task.autonomy_flag?}` wrap in a ` \\\n    `
 *   leading continuation prefix when the value is non-empty, and emit
 *   the empty string when the value is absent. The prefix is part of
 *   the replacement, NOT of the template — this is how the three-form
 *   output stays byte-identical to the mockup.
 *
 * Security:
 *   User-derived placeholders (`{task.title}`, `{task.description?}`,
 *   `{task.phase_label}`, `{project.path}`) are always shell-escaped.
 *   Server-generated literals (`{task.uuid}`, `{project.id}`,
 *   `{task.phase}`) pass through unquoted — they are UUIDs or allowlist
 *   ids and safe as raw tokens.
 *
 *   `{plugin.dirs}` expands into a space-joined sequence of
 *   `--plugin-dir <escaped>` pairs.
 */

import { qPs, qCmd, qPosix, toPosixPath } from "./launcher.js";

export type ShellForm = "powershell" | "cmd" | "posix";

export interface SubstitutionContext {
  project: {
    id: string;
    path: string;
  };
  task: {
    uuid: string;
    title: string;
    description?: string;
    phase: string;
    phase_label: string;
    autonomy?: "guided" | "autonomous";
  };
  pluginDirs: string[];
  /**
   * Allowlist of valid `{task.phase}` ids. Validated against the
   * resolved `actions.phases[].id` set by the caller (route handler).
   * When provided, substitutePlaceholders throws UnknownPhaseError on
   * a mismatch.
   */
  allowedPhaseIds: Set<string>;
  /**
   * The action id being substituted — used only for error reporting
   * (so InvalidPlaceholderError can surface actionId alongside the
   * offending placeholder).
   */
  actionId: string;
}

export class InvalidPlaceholderError extends Error {
  readonly placeholder: string;
  readonly actionId: string;
  readonly template: string;
  constructor(placeholder: string, actionId: string, template: string) {
    super(
      `Unknown placeholder {${placeholder}} in action "${actionId}" template`,
    );
    this.name = "InvalidPlaceholderError";
    this.placeholder = placeholder;
    this.actionId = actionId;
    this.template = template;
  }
}

export class InvalidDescriptionError extends Error {
  constructor() {
    super(
      "task.description cannot contain newlines (breaks single-line copy-paste)",
    );
    this.name = "InvalidDescriptionError";
  }
}

export class UnknownPhaseError extends Error {
  readonly phase: string;
  constructor(phase: string) {
    super(`Unknown phase id "${phase}" — not in actions.phases[].id allowlist`);
    this.name = "UnknownPhaseError";
    this.phase = phase;
  }
}

export class UnsupportedShellError extends Error {
  readonly shellForm: string;
  constructor(shellForm: string) {
    super(`Unsupported shell form: ${shellForm}`);
    this.name = "UnsupportedShellError";
    this.shellForm = shellForm;
  }
}

/**
 * Canonical placeholder names. Anything not on this list is rejected.
 * The allowlist is NOT a security boundary — it prevents typos and
 * template-shape corruption. The real security guard is the escaping
 * discipline below.
 */
const ALLOWED_PLACEHOLDERS = new Set([
  "project.id",
  "project.path",
  "task.uuid",
  "task.title",
  "task.description?",
  "task.phase",
  "task.phase_label",
  "task.autonomy_flag?",
  "plugin.dirs",
]);

function pickEscaper(shellForm: ShellForm): (v: string) => string {
  if (shellForm === "powershell") return qPs;
  if (shellForm === "cmd") return qCmd;
  if (shellForm === "posix") return qPosix;
  throw new UnsupportedShellError(shellForm);
}

function transformPath(shellForm: ShellForm, p: string): string {
  // POSIX form converts Windows separators to forward slashes (matches
  // launcher.ts behaviour). The other two forms pass paths through as-is.
  return shellForm === "posix" ? toPosixPath(p) : p;
}

/**
 * Build the substitution for a single placeholder key. Returns the
 * replacement string (may be empty when the `?` suffix is absent).
 * Callers are responsible for validating the placeholder exists in
 * ALLOWED_PLACEHOLDERS first.
 */
function substituteOne(
  key: string,
  ctx: SubstitutionContext,
  shellForm: ShellForm,
): string {
  const q = pickEscaper(shellForm);

  switch (key) {
    case "project.id":
      return ctx.project.id;
    case "project.path":
      return q(transformPath(shellForm, ctx.project.path));
    case "task.uuid":
      return ctx.task.uuid;
    case "task.title":
      return q(ctx.task.title);
    case "task.phase":
      if (!ctx.allowedPhaseIds.has(ctx.task.phase)) {
        throw new UnknownPhaseError(ctx.task.phase);
      }
      return ctx.task.phase;
    case "task.phase_label":
      return q(ctx.task.phase_label);
    case "task.description?": {
      const d = ctx.task.description?.trim();
      if (!d) return "";
      if (/[\r\n]/.test(d)) throw new InvalidDescriptionError();
      // ` \\\n    ` leading continuation prefix — the optional-suffix
      // semantics covered in the header comment.
      return ` \\\n    ${q(d)}`;
    }
    case "task.autonomy_flag?": {
      if (ctx.task.autonomy === "autonomous") {
        return ` \\\n    --autonomous`;
      }
      return "";
    }
    case "plugin.dirs": {
      const dirs = ctx.pluginDirs;
      if (!dirs || dirs.length === 0) return "";
      return dirs
        .map((d) => `--plugin-dir ${q(transformPath(shellForm, d))}`)
        .join(" ");
    }
    default:
      // This branch is unreachable when callers pre-validate via
      // ALLOWED_PLACEHOLDERS; guarded here so a misuse fails loudly.
      throw new InvalidPlaceholderError(key, ctx.actionId, "");
  }
}

/**
 * Substitute placeholders in `template` for a given shell form. Throws
 * on unknown placeholders, description newlines, unknown phase ids,
 * and unsupported shell forms.
 */
export function substitutePlaceholders(
  template: string,
  ctx: SubstitutionContext,
  shellForm: ShellForm,
): string {
  // Validate shell form up front so a template with no placeholders
  // still rejects "fish".
  pickEscaper(shellForm);

  // Pre-flight reject of description newlines so every shell form
  // fails identically on bad input.
  if (ctx.task.description && /[\r\n]/.test(ctx.task.description)) {
    throw new InvalidDescriptionError();
  }

  // Regex matches `{anything-up-to-closing-brace}` with no nesting. The
  // `?` is part of the placeholder key for optional tokens.
  const substituted = template.replace(/\{([^}]+)\}/g, (_match, rawKey: string) => {
    const key = rawKey.trim();
    if (!ALLOWED_PLACEHOLDERS.has(key)) {
      throw new InvalidPlaceholderError(key, ctx.actionId, template);
    }
    return substituteOne(key, ctx, shellForm);
  });

  // 2026-04-23 — iterate-20260423-shell-line-continuations.
  //
  // The bundled command_template AND the optional-suffix renderers emit
  // POSIX `\<newline>    ` continuations for readability. Those are ONLY
  // valid in POSIX shells — PowerShell and cmd.exe treat the backslash as
  // a literal token, drop everything after the newline, and the user ends
  // up pasting just `claude /shipwright-<phase>` with a stray `\`. The
  // safest cross-shell form is a single line (every shell parses a long
  // one-line command identically). We therefore collapse every
  // `<ws>\<newline><ws>` sequence to a single space AFTER substitution.
  // Trailing whitespace is trimmed so an empty optional suffix at the
  // end of the template doesn't leave a dangling blank.
  return substituted.replace(/[ \t]*\\\r?\n[ \t]*/g, " ").replace(/[ \t]+$/, "");
}

/**
 * Parallel evaluation across all three shell forms. Useful for the
 * launch route which returns `{powershell, cmd, posix}` to the client.
 * Each form is evaluated independently so an escape-drift bug in one
 * can't corrupt the others.
 */
export function substituteAllForms(
  template: string,
  ctx: SubstitutionContext,
): { powershell: string; cmd: string; posix: string } {
  return {
    powershell: substitutePlaceholders(template, ctx, "powershell"),
    cmd: substitutePlaceholders(template, ctx, "cmd"),
    posix: substitutePlaceholders(template, ctx, "posix"),
  };
}

/**
 * Convenience wrapper: the route layer's single entry point for producing
 * the 3 shell forms from a command template + context. Delegates directly
 * to substituteAllForms but reads better at the call site.
 */
export function buildExternalLaunchCommand(args: {
  template: string;
  ctx: SubstitutionContext;
}): { powershell: string; cmd: string; posix: string } {
  return substituteAllForms(args.template, args.ctx);
}

/**
 * Dry-run validator used by the actions route to verify every
 * `command_template` is substitution-safe at load time. Constructs a
 * synthetic context with representative values and re-runs all three
 * shell forms. Returns the first error encountered, or null on success.
 *
 * Does NOT raise UnknownPhaseError — the validator's job is to catch
 * placeholder typos and shape corruption, not to fail-close when a
 * phase allowlist is empty (e.g. during initial setup). The actual
 * phase check runs at launch time with the real task state.
 */
export function validateTemplate(
  template: string,
  actionId: string,
  phaseIds: string[],
): InvalidPlaceholderError | null {
  const ctx: SubstitutionContext = {
    project: { id: "dry-run-project", path: "/tmp/dry-run" },
    task: {
      uuid: "00000000-0000-0000-0000-000000000000",
      title: "dry run",
      phase: phaseIds[0] ?? "dry-run-phase",
      phase_label: "Dry Run",
    },
    pluginDirs: [],
    allowedPhaseIds: new Set([...phaseIds, "dry-run-phase"]),
    actionId,
  };
  try {
    substituteAllForms(template, ctx);
    return null;
  } catch (err) {
    if (err instanceof InvalidPlaceholderError) return err;
    // Other error classes (UnsupportedShellError, InvalidDescriptionError,
    // UnknownPhaseError) do not apply to the dry-run context because we
    // supply clean values.
    throw err;
  }
}
