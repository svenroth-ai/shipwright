import { describe, it, expect } from "vitest";

import {
  substitutePlaceholders,
  substituteAllForms,
  validateTemplate,
  InvalidPlaceholderError,
  InvalidDescriptionError,
  UnknownPhaseError,
  UnsupportedShellError,
  type SubstitutionContext,
  type ShellForm,
} from "./actions-substitute.js";

function baseCtx(overrides: Partial<SubstitutionContext["task"]> = {}): SubstitutionContext {
  return {
    project: { id: "proj-123", path: "/home/sven/app" },
    task: {
      uuid: "00000000-1111-2222-3333-444444444444",
      title: "Write docs",
      phase: "build",
      phase_label: "Build",
      ...overrides,
    },
    pluginDirs: [],
    allowedPhaseIds: new Set(["build", "test", "design"]),
    actionId: "new-task",
  };
}

const SHELL_FORMS: ShellForm[] = ["powershell", "cmd", "posix"];

describe("actions-substitute — positive placeholders across shells", () => {
  it("substitutes project.path with embedded spaces (single quotes / double quotes)", () => {
    const ctx = baseCtx();
    ctx.project.path = "/home/sven/my app";
    expect(substitutePlaceholders("{project.path}", ctx, "powershell")).toBe(
      `'/home/sven/my app'`,
    );
    expect(substitutePlaceholders("{project.path}", ctx, "cmd")).toBe(
      `"/home/sven/my app"`,
    );
    expect(substitutePlaceholders("{project.path}", ctx, "posix")).toBe(
      `'/home/sven/my app'`,
    );
  });

  it("substitutes project.path containing single quotes (shell-escaped correctly)", () => {
    const ctx = baseCtx();
    ctx.project.path = "/home/sven/o'malley/app";
    // PS: ' → ''; POSIX: ' → '\''; CMD: untouched (double-quoted form)
    expect(substitutePlaceholders("{project.path}", ctx, "powershell")).toBe(
      `'/home/sven/o''malley/app'`,
    );
    expect(substitutePlaceholders("{project.path}", ctx, "posix")).toBe(
      `'/home/sven/o'\\''malley/app'`,
    );
    expect(substitutePlaceholders("{project.path}", ctx, "cmd")).toBe(
      `"/home/sven/o'malley/app"`,
    );
  });

  it("substitutes project.path containing double quotes", () => {
    const ctx = baseCtx();
    ctx.project.path = `/home/sven/He said "hi"/app`;
    // CMD: " → \"; PS/POSIX double quotes pass through single-quoted form
    expect(substitutePlaceholders("{project.path}", ctx, "cmd")).toBe(
      `"/home/sven/He said \\"hi\\"/app"`,
    );
    expect(substitutePlaceholders("{project.path}", ctx, "powershell")).toContain(
      `He said "hi"`,
    );
  });

  it("substitutes Windows trailing-backslash path", () => {
    const ctx = baseCtx();
    ctx.project.path = "C:\\dev\\app\\";
    // POSIX converts backslashes to forward slashes.
    expect(substitutePlaceholders("{project.path}", ctx, "posix")).toBe(
      "'C:/dev/app/'",
    );
    expect(substitutePlaceholders("{project.path}", ctx, "powershell")).toBe(
      "'C:\\dev\\app\\'",
    );
  });

  it("substitutes Unicode path", () => {
    const ctx = baseCtx();
    ctx.project.path = "/home/sven/äpp";
    for (const form of SHELL_FORMS) {
      const out = substitutePlaceholders("{project.path}", ctx, form);
      expect(out).toContain("äpp");
    }
  });

  it("project.id passes through UNQUOTED (server-generated UUID, safe literal)", () => {
    const ctx = baseCtx();
    for (const form of SHELL_FORMS) {
      expect(substitutePlaceholders("{project.id}", ctx, form)).toBe("proj-123");
    }
  });

  it("task.uuid passes through UNQUOTED", () => {
    const ctx = baseCtx();
    for (const form of SHELL_FORMS) {
      expect(substitutePlaceholders("{task.uuid}", ctx, form)).toBe(ctx.task.uuid);
    }
  });

  it("task.title with shell-metacharacters is escaped (not executed)", () => {
    const ctx = baseCtx({ title: "oops $(whoami) `ls` ; rm -rf /" });
    const posix = substitutePlaceholders("{task.title}", ctx, "posix");
    // POSIX single-quoted — literal content wrapped so no interpolation
    expect(posix).toBe(`'oops $(whoami) \`ls\` ; rm -rf /'`);
    expect(posix.startsWith("'")).toBe(true);
    expect(posix.endsWith("'")).toBe(true);
  });

  it("task.description? empty produces empty substitution (no leading prefix)", () => {
    const ctx = baseCtx();
    expect(substitutePlaceholders("{task.description?}", ctx, "posix")).toBe("");
    expect(substitutePlaceholders("before{task.description?}after", ctx, "posix"))
      .toBe("beforeafter");
  });

  it("task.description? non-empty produces space-prefixed escaped value", () => {
    // 2026-04-23 — post-processing in substitutePlaceholders now flattens
    // the continuation-prefix `\<newline>    ` to a single space so the
    // output is cross-shell safe (PowerShell + cmd don't honour `\`).
    const ctx = baseCtx();
    ctx.task.description = "Please fix the bug";
    const out = substitutePlaceholders("{task.description?}", ctx, "posix");
    expect(out).toBe(` 'Please fix the bug'`);
  });

  it("task.description? rejects embedded newlines", () => {
    const ctx = baseCtx();
    ctx.task.description = "first line\nsecond line";
    expect(() =>
      substitutePlaceholders("{task.description?}", ctx, "posix"),
    ).toThrow(InvalidDescriptionError);
  });

  it("task.phase validates against allowedPhaseIds", () => {
    const ctx = baseCtx();
    expect(substitutePlaceholders("{task.phase}", ctx, "posix")).toBe("build");
    ctx.task.phase = "nonexistent";
    expect(() =>
      substitutePlaceholders("{task.phase}", ctx, "posix"),
    ).toThrow(UnknownPhaseError);
  });

  it("task.phase_label is user-editable so it IS escaped", () => {
    const ctx = baseCtx({ phase_label: "my custom label with 'quotes'" });
    const posix = substitutePlaceholders("{task.phase_label}", ctx, "posix");
    expect(posix).toBe(`'my custom label with '\\''quotes'\\'''`);
  });

  it("task.autonomy_flag? renders --autonomous with prefix when autonomous", () => {
    // 2026-04-23 — post-processing flattens the continuation-prefix
    // `\<newline>    ` to a single space.
    const ctx = baseCtx();
    ctx.task.autonomy = "autonomous";
    expect(substitutePlaceholders("{task.autonomy_flag?}", ctx, "posix")).toBe(
      ` --autonomous`,
    );
  });

  it("task.autonomy_flag? empty when guided / unset", () => {
    const ctx = baseCtx();
    expect(substitutePlaceholders("{task.autonomy_flag?}", ctx, "posix")).toBe("");
    ctx.task.autonomy = "guided";
    expect(substitutePlaceholders("{task.autonomy_flag?}", ctx, "posix")).toBe("");
  });

  it("plugin.dirs empty produces empty string", () => {
    const ctx = baseCtx();
    expect(substitutePlaceholders("{plugin.dirs}", ctx, "posix")).toBe("");
  });

  it("plugin.dirs expands to space-joined --plugin-dir chunks, each escaped", () => {
    const ctx = baseCtx();
    ctx.pluginDirs = ["/home/sven/plugin a", "/home/sven/plugin b"];
    const out = substitutePlaceholders("{plugin.dirs}", ctx, "posix");
    expect(out).toBe(
      `--plugin-dir '/home/sven/plugin a' --plugin-dir '/home/sven/plugin b'`,
    );
  });
});

describe("actions-substitute — negative cases", () => {
  it("unknown placeholder throws InvalidPlaceholderError with actionId + template", () => {
    const ctx = baseCtx();
    try {
      substitutePlaceholders("hello {task.priority}", ctx, "posix");
      throw new Error("should have thrown");
    } catch (err) {
      expect(err).toBeInstanceOf(InvalidPlaceholderError);
      const ipe = err as InvalidPlaceholderError;
      expect(ipe.placeholder).toBe("task.priority");
      expect(ipe.actionId).toBe("new-task");
      expect(ipe.template).toBe("hello {task.priority}");
    }
  });

  it("unsupported shell form throws UnsupportedShellError", () => {
    const ctx = baseCtx();
    expect(() =>
      substitutePlaceholders("{task.title}", ctx, "fish" as ShellForm),
    ).toThrow(UnsupportedShellError);
  });

  it("description newline rejected even when the template does not reference description", () => {
    // Input-validation pre-flight — protects future templates.
    const ctx = baseCtx();
    ctx.task.description = "first\nsecond";
    expect(() =>
      substitutePlaceholders("{task.title}", ctx, "posix"),
    ).toThrow(InvalidDescriptionError);
  });
});

describe("actions-substitute — substituteAllForms", () => {
  it("returns three parallel shell forms for the Shipwright new-task template", () => {
    const template =
      "claude /shipwright-{task.phase}{task.autonomy_flag?} \\\n    --project-root {project.path} \\\n    --session-id {task.uuid} \\\n    --name \"{task.phase_label}: {task.title}\" \\\n    {plugin.dirs}{task.description?}";
    const ctx = baseCtx();
    ctx.task.description = "Write docs";
    ctx.pluginDirs = ["/home/sven/plugin"];
    const out = substituteAllForms(template, ctx);
    expect(out.posix).toContain("claude /shipwright-build");
    expect(out.posix).toContain("--project-root '/home/sven/app'");
    // phase_label + title are user-editable, so they emerge POSIX-escaped
    // (single-quoted) inside the surrounding literal double-quotes from the
    // template. This is the security contract — escaping never relaxes
    // even when the surrounding template uses a different quote style.
    expect(out.posix).toContain(`--name "'Build': 'Write docs'"`);
    expect(out.posix).toContain("--plugin-dir '/home/sven/plugin'");
    // 2026-04-23 — output is flattened to a single line (post-processing).
    // Description trailer is now space-separated, not on a continuation.
    expect(out.posix).toMatch(/'Write docs'$/);
    expect(out.posix.split("\n")).toHaveLength(1);
    expect(out.powershell).toContain("claude /shipwright-build");
    expect(out.cmd).toContain("claude /shipwright-build");
  });

  it("autonomous flag appears space-separated (flattened), not on a continuation line", () => {
    // 2026-04-23 — was `\<newline>    --autonomous`, now a single space
    // delimiter so PowerShell + cmd.exe parse the command correctly.
    const template =
      "claude /shipwright-run \\\n    --project-root {project.path} \\\n    --session-id {task.uuid}{task.autonomy_flag?}";
    const ctx = baseCtx();
    ctx.task.autonomy = "autonomous";
    const out = substituteAllForms(template, ctx);
    expect(out.posix).toMatch(/--session-id 00000000-.* --autonomous$/);
    expect(out.posix.split("\n")).toHaveLength(1);
  });
});

describe("actions-substitute — validateTemplate dry-run", () => {
  it("returns null for a well-formed template", () => {
    const result = validateTemplate(
      "claude /shipwright-{task.phase} --session-id {task.uuid} --name {task.title}",
      "new-task",
      ["build", "test"],
    );
    expect(result).toBeNull();
  });

  it("returns InvalidPlaceholderError for a typo", () => {
    const result = validateTemplate(
      "claude --project {project.paht}",
      "bogus-action",
      ["build"],
    );
    expect(result).toBeInstanceOf(InvalidPlaceholderError);
    expect(result?.placeholder).toBe("project.paht");
    expect(result?.actionId).toBe("bogus-action");
  });
});

// ── 2026-04-23 — iterate-20260423-shell-line-continuations ──
//
// The bundled default-actions.json command_template ships with `\\\n    `
// POSIX-style line continuations for readability. Those MUST NOT appear in
// the final copy command — PowerShell and cmd.exe do not honour backslash
// continuation, so the user pastes the first line only and all flags
// after it are silently dropped. (ADR-046 regression from iterate
// 20260423-launch-command-wiring.) The renderer now collapses any
// `<space> \\\n<spaces>` sequence into a single space before returning.
describe("actions-substitute — single-line output (2026-04-23)", () => {
  const MULTILINE = `claude /shipwright-{task.phase}{task.autonomy_flag?} \\
    --project-root {project.path} \\
    --session-id {task.uuid} \\
    --name "{task.phase_label}: {task.title}" \\
    {plugin.dirs}{task.description?}`;

  function assertSingleLine(output: string): void {
    expect(output).not.toContain("\\\n");
    expect(output).not.toContain("\\ \n");
    expect(output.split("\n")).toHaveLength(1);
  }

  it("flattens multi-line template to one line in powershell", () => {
    const ctx = baseCtx({ description: "fix login" });
    const out = substitutePlaceholders(MULTILINE, ctx, "powershell");
    assertSingleLine(out);
    // All key tokens must still be present.
    expect(out).toContain("/shipwright-build");
    expect(out).toContain("--project-root");
    expect(out).toContain("--session-id");
    expect(out).toContain("--name");
    expect(out).toContain("fix login");
  });

  it("flattens multi-line template to one line in cmd", () => {
    const ctx = baseCtx({ description: "fix login" });
    const out = substitutePlaceholders(MULTILINE, ctx, "cmd");
    assertSingleLine(out);
    expect(out).toContain("/shipwright-build");
  });

  it("flattens multi-line template to one line in posix", () => {
    const ctx = baseCtx({ description: "fix login" });
    const out = substitutePlaceholders(MULTILINE, ctx, "posix");
    assertSingleLine(out);
    expect(out).toContain("/shipwright-build");
  });

  it("collapses the empty-plugin-dirs gap without leaving a dangling continuation", () => {
    // `{plugin.dirs}` expands to "" when pluginDirs is empty. Without
    // flattening, the prior ` \\\n    ` from the preceding `--name` line
    // leaked a `\\ \\\n    ` artefact into the output.
    const ctx = baseCtx({ description: "desc" });
    for (const shell of SHELL_FORMS) {
      const out = substitutePlaceholders(MULTILINE, ctx, shell);
      expect(out).not.toMatch(/\\\s*\\/); // no double-backslash artifacts
      expect(out).not.toContain("  \\"); // no orphan continuation-backslash
    }
  });

  it("collapses when description is absent (optional suffix empty)", () => {
    const ctx = baseCtx(); // no description
    for (const shell of SHELL_FORMS) {
      const out = substitutePlaceholders(MULTILINE, ctx, shell);
      expect(out).not.toContain("\\\n");
      expect(out.split("\n")).toHaveLength(1);
    }
  });
});
