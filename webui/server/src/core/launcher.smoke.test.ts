/*
 * Shell-execution smoke test for the generated launch command.
 *
 * Catches "string valid but command fails" regressions: spawn a real
 * PowerShell child process, define a stub `claude` function that just
 * echoes its arguments, then run the generated command. We assert the
 * shell exits 0 and stdout reflects the expected --session-id, --name,
 * and --add-dir tokens after the shell has parsed them.
 *
 * Skipped when no PowerShell is available (Linux CI without `pwsh`).
 * The PowerShell escape spec lives in launcher.ts; this test is the
 * end-to-end check that the emitted PS literal survives a real parse.
 */

import { describe, it, expect, beforeAll } from "vitest";
import { spawn, spawnSync } from "node:child_process";

import { buildCopyCommands } from "./launcher.js";

const SAMPLE_UUID = "00000000-1111-2222-3333-444444444444";

function findPowerShell(): string | null {
  for (const candidate of ["pwsh", "powershell"]) {
    const result = spawnSync(candidate, ["-NoProfile", "-Command", "$PSVersionTable.PSVersion.Major"], {
      stdio: "pipe",
    });
    if (result.status === 0) return candidate;
  }
  return null;
}

let powershell: string | null = null;
beforeAll(() => {
  powershell = findPowerShell();
});

function runInPowerShell(generatedCommand: string): Promise<{ exit: number; stdout: string; stderr: string }> {
  // Wrap the generated command in a script that defines a stub `claude`
  // function. The real `claude` would launch the CLI; the stub just
  // echoes the parsed args so we can assert what PowerShell saw.
  // The generated PS form starts with "& claude …"; stripping the leading
  // "& " is unnecessary because the stub `claude` is a function — & also
  // works on functions in PS.
  // Build the wrapper as concatenated single-quoted JS strings to keep
  // PowerShell's backtick escapes (`n) out of JS template-literal grammar.
  const wrapper =
    'function claude {\n' +
    '  $tokens = @()\n' +
    '  for ($i = 0; $i -lt $args.Length; $i++) {\n' +
    '    $tokens += "ARG[$i]=" + $args[$i]\n' +
    '  }\n' +
    '  Write-Output ($tokens -join "`n")\n' +
    '}\n' +
    generatedCommand + '\n';
  return new Promise((resolve, reject) => {
    if (!powershell) {
      reject(new Error("No PowerShell available"));
      return;
    }
    const child = spawn(powershell, ["-NoProfile", "-Command", wrapper], { stdio: "pipe" });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (b) => (stdout += b.toString()));
    child.stderr.on("data", (b) => (stderr += b.toString()));
    child.on("error", reject);
    child.on("close", (code) => resolve({ exit: code ?? -1, stdout, stderr }));
  });
}

describe("launcher smoke — generated PS command actually parses + runs", () => {
  it.skipIf(!findPowerShell())(
    "tricky-char title (single quote, $, backtick, semicolon, &) parses cleanly",
    async () => {
      const trickyTitle = `Test's $tring \`with semicolons; & pipes |`;
      // 2026-04-23 — Set-Location -ErrorAction Stop requires a real dir.
      // process.cwd() is guaranteed present at test runtime.
      const cwd = process.cwd();
      const cmd = buildCopyCommands({
        sessionUuid: SAMPLE_UUID,
        cwd,
        title: trickyTitle,
      });
      const { exit, stdout, stderr } = await runInPowerShell(cmd.powershell);
      expect(stderr).toBe("");
      expect(exit).toBe(0);
      // PS strips outer quotes — the stub function sees the unescaped value.
      expect(stdout).toContain(`--session-id`);
      expect(stdout).toContain(SAMPLE_UUID);
      expect(stdout).toContain(`--name`);
      expect(stdout).toContain(trickyTitle);
      // Assertion: --add-dir appears in claude's parsed args. We don't assert
      // cwd verbatim because PowerShell path-normalizes (e.g. C:\ ↔ C:/) and
      // the Set-Location prefix consumes the cwd value too.
      expect(stdout).toContain("--add-dir");
    },
    20_000,
  );

  it.skipIf(!findPowerShell())(
    "Unicode title (umlauts, emoji, CJK) survives the round-trip",
    async () => {
      const t = "Test ä ö ü 日本語 🚀";
      // 2026-04-23 — cwd must actually exist now that the rendered
      // command starts with `Set-Location <cwd> -ErrorAction Stop; `
      // (iterate-20260423-resume-cwd-prefix). `process.cwd()` is
      // guaranteed to be a real directory at test time.
      const cwd = process.cwd();
      const cmd = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd, title: t });
      const { exit, stderr } = await runInPowerShell(cmd.powershell);
      expect(stderr).toBe("");
      expect(exit).toBe(0);
      // Asserting umlaut/CJK round-trip via stdout is shell-encoding-fragile
      // (Windows code page mismatches Node's UTF-8). Exit code 0 + clean
      // stderr is the load-bearing check: the shell parsed the literal.
    },
    20_000,
  );

  it.skipIf(!findPowerShell())(
    "command without --name (empty title) still parses",
    async () => {
      const cmd = buildCopyCommands({
        sessionUuid: SAMPLE_UUID,
        cwd: process.cwd(),
        title: "",
      });
      expect(cmd.powershell).not.toContain("--name");
      const { exit, stderr } = await runInPowerShell(cmd.powershell);
      expect(stderr).toBe("");
      expect(exit).toBe(0);
    },
    20_000,
  );
});
