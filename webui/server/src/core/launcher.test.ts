import { describe, it, expect } from "vitest";

import { buildCopyCommands, copyLauncher, buildCdPrefix } from "./launcher.js";

const SAMPLE_UUID = "00000000-1111-2222-3333-444444444444";
const WINDOWS_PATH_WITH_SPACE = String.raw`C:\Users\SvenRoth\dinovo GmbH\AI Backup - Documents\03 Development\shipwright`;

describe("launcher.buildCopyCommands", () => {
  it("emits three shell forms with session-id + cwd", () => {
    // 2026-04-23 — iterate-20260423-resume-cwd-prefix. Each shell form
    // now starts with a `cd`-style prefix so the pasted command sets
    // cwd to <cwd> before invoking claude. The claude invocation still
    // appears — just preceded by the prefix.
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.powershell).toContain(`--session-id '${SAMPLE_UUID}'`);
    expect(c.cmd).toContain(`--session-id "${SAMPLE_UUID}"`);
    expect(c.posix).toContain(`--session-id '${SAMPLE_UUID}'`);
    expect(c.powershell).toContain("& claude ");
    expect(c.cmd).toContain("claude ");
    expect(c.posix).toContain("claude ");
  });

  it("preserves embedded spaces in PowerShell single-quoted args", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.powershell).toContain(`'${WINDOWS_PATH_WITH_SPACE}'`);
  });

  it("preserves embedded spaces in cmd.exe double-quoted args", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.cmd).toContain(`"${WINDOWS_PATH_WITH_SPACE}"`);
  });

  it("converts path separators to forward slashes for POSIX form", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.posix).toContain("'C:/Users/SvenRoth/dinovo GmbH/AI Backup - Documents/03 Development/shipwright'");
    expect(c.posix).not.toContain("\\");
  });

  it("appends --resume when resume=true", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE, resume: true });
    expect(c.powershell).toContain(`--resume '${SAMPLE_UUID}'`);
    expect(c.cmd).toContain(`--resume "${SAMPLE_UUID}"`);
    expect(c.posix).toContain(`--resume '${SAMPLE_UUID}'`);
  });

  it("OMITS --session-id on plain resume (CLI 2.1+ rejects the combo without --fork-session)", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE, resume: true });
    expect(c.powershell).not.toContain("--session-id");
    expect(c.cmd).not.toContain("--session-id");
    expect(c.posix).not.toContain("--session-id");
  });

  it("KEEPS --session-id on fork (--fork-session is the required combinator)", () => {
    const parent = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      fork: true,
      parentSessionUuid: parent,
    });
    expect(c.powershell).toContain(`--session-id '${SAMPLE_UUID}'`);
    expect(c.powershell).toContain("--fork-session");
  });

  it("appends --resume <parent> --fork-session when fork=true", () => {
    const parent = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      fork: true,
      parentSessionUuid: parent,
    });
    expect(c.powershell).toContain(`--resume '${parent}' --fork-session`);
    expect(c.cmd).toContain(`--resume "${parent}" --fork-session`);
    expect(c.posix).toContain(`--resume '${parent}' --fork-session`);
  });

  it("throws when fork=true but parentSessionUuid is missing", () => {
    expect(() =>
      buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE, fork: true }),
    ).toThrow();
  });

  it("appends --plugin-dir per entry for all three forms", () => {
    const plugins = [
      String.raw`C:\Users\SvenRoth\.claude\plugins\cache\shipwright\shipwright-iterate\0.3.0`,
    ];
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      pluginDirs: plugins,
    });
    expect(c.powershell).toContain(`--plugin-dir '${plugins[0]}'`);
    expect(c.cmd).toContain(`--plugin-dir "${plugins[0]}"`);
    expect(c.posix).toContain(`--plugin-dir '${plugins[0].replace(/\\/g, "/")}'`);
  });

  it("escapes embedded single quote in PowerShell by doubling", () => {
    const odd = "path'with/quote";
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: odd });
    expect(c.powershell).toContain(`'path''with/quote'`);
  });

  it("escapes embedded double quote in cmd.exe by backslash", () => {
    const odd = 'path"with/quote';
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: odd });
    expect(c.cmd).toContain(`"path\\"with/quote"`);
  });

  it("escapes embedded single quote in POSIX via '\\'' concat trick", () => {
    const odd = "path'with/quote";
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: odd });
    expect(c.posix).toContain(`'path'\\''with/quote'`);
  });
});

describe("launcher.buildCopyCommands — --name title flag", () => {
  it("emits --name <title> after --session-id when title provided", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: "Fix login bug",
    });
    expect(c.powershell).toContain(`--name 'Fix login bug'`);
    expect(c.cmd).toContain(`--name "Fix login bug"`);
    expect(c.posix).toContain(`--name 'Fix login bug'`);
  });

  it("omits --name entirely when title is undefined", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.powershell).not.toContain("--name");
    expect(c.cmd).not.toContain("--name");
    expect(c.posix).not.toContain("--name");
  });

  it("omits --name when title is empty / whitespace", () => {
    for (const empty of ["", "   ", "\t  \t"]) {
      const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE, title: empty });
      expect(c.powershell).not.toContain("--name");
      expect(c.posix).not.toContain("--name");
    }
  });

  it("trims surrounding whitespace from title before emitting", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: "  Trimmed  ",
    });
    expect(c.powershell).toContain(`--name 'Trimmed'`);
    expect(c.posix).toContain(`--name 'Trimmed'`);
  });

  it("rejects titles containing newlines (LF or CRLF)", () => {
    for (const bad of ["a\nb", "a\r\nb", "\n", "\r"]) {
      expect(() =>
        buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE, title: bad }),
      ).toThrow(/newlines/i);
    }
  });

  it("escapes PowerShell single-quote in title by doubling", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: "Test's title",
    });
    expect(c.powershell).toContain(`--name 'Test''s title'`);
  });

  it("preserves PowerShell-active chars inside single-quoted title literal", () => {
    // Inside PS single quotes, $ ` ; & | " stay literal.
    const tricky = `foo $bar \`baz; & | "quote"`;
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: tricky,
    });
    expect(c.powershell).toContain(`--name '${tricky}'`);
  });

  it("preserves Unicode in title (umlauts, emoji, CJK)", () => {
    const t = "Test ä ö ü 日本語 🚀";
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: t,
    });
    expect(c.powershell).toContain(`--name '${t}'`);
    expect(c.posix).toContain(`--name '${t}'`);
  });

  it("accepts a 200-character title verbatim", () => {
    const t = "x".repeat(200);
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: t,
    });
    expect(c.powershell).toContain(`--name '${t}'`);
  });

  it("places --name AFTER --resume when resume=true", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      resume: true,
      title: "Resume me",
    });
    const psResumeIdx = c.powershell.indexOf(`--resume '${SAMPLE_UUID}'`);
    const psNameIdx = c.powershell.indexOf(`--name 'Resume me'`);
    expect(psResumeIdx).toBeGreaterThan(0);
    expect(psNameIdx).toBeGreaterThan(psResumeIdx);
  });

  it("escapes POSIX single-quote in title via the '\\'' concat trick", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: "Test's title",
    });
    expect(c.posix).toContain(`--name 'Test'\\''s title'`);
  });

  it("escapes cmd.exe double-quote in title via backslash", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      title: 'Test "quoted" thing',
    });
    expect(c.cmd).toContain(`--name "Test \\"quoted\\" thing"`);
  });
});

// ── 2026-04-23 — iterate-20260423-resume-cwd-prefix ──
//
// ADR-049 added {cd.prefix} to substitutePlaceholders so the Launch copy
// command sets cwd before invoking claude. The Resume / Fork paths go
// through buildCopyCommands (legacy) which had no cd prefix, so users
// pasting a Resume link in a HOME terminal hit the same missing-cwd bug
// the cd prefix was meant to fix. This iterate extends the cd prefix to
// the legacy launcher so Resume + Fork + any other buildCopyCommands
// caller emits identical shell-aware prefixes.
describe("launcher.buildCopyCommands — cd prefix (2026-04-23)", () => {
  it("plain Launch starts with Set-Location / cd /d / cd per shell", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.powershell.startsWith(`Set-Location '${WINDOWS_PATH_WITH_SPACE}' -ErrorAction Stop; `)).toBe(true);
    expect(c.cmd.startsWith(`cd /d "${WINDOWS_PATH_WITH_SPACE}" && `)).toBe(true);
    // POSIX converts backslashes to forward slashes.
    const posixCwd = WINDOWS_PATH_WITH_SPACE.replace(/\\/g, "/");
    expect(c.posix.startsWith(`cd '${posixCwd}' && `)).toBe(true);
  });

  it("Resume command carries the same cd prefix", () => {
    // Covers the original user-reported bug: a Resume link pasted in HOME
    // terminal was running claude with pwd=HOME before this fix.
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      resume: true,
    });
    expect(c.powershell.startsWith("Set-Location ")).toBe(true);
    expect(c.cmd.startsWith("cd /d ")).toBe(true);
    expect(c.posix.startsWith("cd ")).toBe(true);
    // Resume semantics preserved — claude sees --resume <uuid>.
    expect(c.powershell).toContain(`--resume '${SAMPLE_UUID}'`);
    expect(c.cmd).toContain(`--resume "${SAMPLE_UUID}"`);
    expect(c.posix).toContain(`--resume '${SAMPLE_UUID}'`);
  });

  it("Fork command carries the same cd prefix", () => {
    const parent = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
      fork: true,
      parentSessionUuid: parent,
    });
    expect(c.powershell.startsWith("Set-Location ")).toBe(true);
    expect(c.cmd.startsWith("cd /d ")).toBe(true);
    expect(c.posix.startsWith("cd ")).toBe(true);
    expect(c.powershell).toContain("--fork-session");
  });

  it("empty cwd emits no cd prefix (graceful degrade, identical to {cd.prefix})", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: "" });
    expect(c.powershell.startsWith("& claude ")).toBe(true);
    expect(c.cmd.startsWith("claude ")).toBe(true);
    expect(c.posix.startsWith("claude ")).toBe(true);
  });

  it("escapes embedded single quotes in cd prefix path (PS + POSIX)", () => {
    const c = buildCopyCommands({
      sessionUuid: SAMPLE_UUID,
      cwd: "/home/sven/o'malley/app",
    });
    // PS: ' → ''
    expect(c.powershell.startsWith("Set-Location '/home/sven/o''malley/app' -ErrorAction Stop; ")).toBe(true);
    // POSIX: ' → '\''
    expect(c.posix.startsWith("cd '/home/sven/o'\\''malley/app' && ")).toBe(true);
  });
});

describe("launcher.buildCdPrefix — exported shared helper (2026-04-23)", () => {
  it("returns the PowerShell form with Set-Location + -ErrorAction Stop", () => {
    expect(buildCdPrefix("powershell", "/home/sven/app")).toBe(
      "Set-Location '/home/sven/app' -ErrorAction Stop; ",
    );
  });

  it("returns the cmd.exe form with cd /d + &&", () => {
    expect(buildCdPrefix("cmd", "/home/sven/app")).toBe(
      `cd /d "/home/sven/app" && `,
    );
  });

  it("returns the POSIX form with cd + &&", () => {
    expect(buildCdPrefix("posix", "/home/sven/app")).toBe(
      "cd '/home/sven/app' && ",
    );
  });

  it("converts Windows backslashes to forward slashes only for POSIX", () => {
    expect(buildCdPrefix("posix", "C:\\dev\\app")).toBe(
      "cd 'C:/dev/app' && ",
    );
    expect(buildCdPrefix("powershell", "C:\\dev\\app")).toBe(
      "Set-Location 'C:\\dev\\app' -ErrorAction Stop; ",
    );
    expect(buildCdPrefix("cmd", "C:\\dev\\app")).toBe(
      `cd /d "C:\\dev\\app" && `,
    );
  });

  it("returns empty string on empty cwd (graceful degrade)", () => {
    expect(buildCdPrefix("powershell", "")).toBe("");
    expect(buildCdPrefix("cmd", "")).toBe("");
    expect(buildCdPrefix("posix", "")).toBe("");
  });
});

describe("launcher.copyLauncher adapter", () => {
  it("returns { commands, launcherUsed: 'copy' }", async () => {
    const result = await copyLauncher({
      sessionUuid: SAMPLE_UUID,
      cwd: WINDOWS_PATH_WITH_SPACE,
    });
    expect(result.launcherUsed).toBe("copy");
    expect(result.commands.powershell).toContain(SAMPLE_UUID);
  });
});
