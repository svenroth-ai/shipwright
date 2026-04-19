import { describe, it, expect } from "vitest";

import { buildCopyCommands, copyLauncher } from "./launcher.js";

const SAMPLE_UUID = "00000000-1111-2222-3333-444444444444";
const WINDOWS_PATH_WITH_SPACE = String.raw`C:\Users\SvenRoth\dinovo GmbH\AI Backup - Documents\03 Development\shipwright`;

describe("launcher.buildCopyCommands", () => {
  it("emits three shell forms with session-id + cwd", () => {
    const c = buildCopyCommands({ sessionUuid: SAMPLE_UUID, cwd: WINDOWS_PATH_WITH_SPACE });
    expect(c.powershell).toContain(`--session-id '${SAMPLE_UUID}'`);
    expect(c.cmd).toContain(`--session-id "${SAMPLE_UUID}"`);
    expect(c.posix).toContain(`--session-id '${SAMPLE_UUID}'`);
    expect(c.powershell).toMatch(/^& claude /);
    expect(c.cmd.startsWith("claude ")).toBe(true);
    expect(c.posix.startsWith("claude ")).toBe(true);
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
