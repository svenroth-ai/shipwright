// No browser, no model: the operator inputs, the auth source and the temp HOME provisioning.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { AuthError, copyLogin, loginFile, pickAuthSource } from "../../src/auth.js";
import { ConfigError, defaultEnvFile, loadConfig, parseEnvFile } from "../../src/env.js";
import { provisionHome } from "../../src/provision.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const noFile = () => null;
const all = {
  SHIPWRIGHT_E2E_PERMISSION_MODE: "acceptEdits",
  SHIPWRIGHT_E2E_WEBUI_DIR: os.tmpdir(),
  SHIPWRIGHT_E2E_MAX_MINUTES: "90",
};

// @covers FR-01.04
test("refuses to start without each required input, naming it (no defaults)", () => {
  for (const name of Object.keys(all)) {
    const env = { ...all } as Record<string, string | undefined>;
    delete env[name];
    expect(() => loadConfig(repo, env, noFile)).toThrow(new RegExp(`${name} not set`));
  }
  expect(() => loadConfig(repo, {}, noFile)).toThrow(ConfigError);
});

// @covers FR-01.04
test("rejects a bad budget and a non-word permission mode", () => {
  expect(() => loadConfig(repo, { ...all, SHIPWRIGHT_E2E_MAX_MINUTES: "0" }, noFile)).toThrow(/whole number/);
  expect(() => loadConfig(repo, { ...all, SHIPWRIGHT_E2E_PERMISSION_MODE: "a b; rm" }, noFile)).toThrow(/single word/);
});

// @covers FR-01.04
test("the real environment wins over the env file, and each source is recorded", () => {
  const file = "SHIPWRIGHT_E2E_PERMISSION_MODE=plan\nSHIPWRIGHT_E2E_MAX_MINUTES=5\n# c\nSHIPWRIGHT_E2E_WORKDIR=\"/w\"\n";
  const env = { SHIPWRIGHT_E2E_PERMISSION_MODE: "acceptEdits", SHIPWRIGHT_E2E_WEBUI_DIR: os.tmpdir() };
  const cfg = loadConfig(repo, env, () => file);
  expect(cfg.permissionMode).toBe("acceptEdits");
  expect(cfg.maxMinutes).toBe(5);
  expect(cfg.sources).toMatchObject({
    SHIPWRIGHT_E2E_PERMISSION_MODE: "process-env",
    SHIPWRIGHT_E2E_MAX_MINUTES: "env-file",
    SHIPWRIGHT_E2E_WORKDIR: "env-file",
  });
  expect(cfg.workdir).toBe(path.resolve("/w"));
});

// @covers FR-01.04
test("default env file is ../autorune2e/.env relative to the repo root; parser skips comments", () => {
  expect(defaultEnvFile("/x/repo").replace(/\\/g, "/")).toMatch(/\/x\/autorune2e\/\.env$/);
  expect(parseEnvFile("# a\n\nK=v\nbad line\nQ='x y'\n")).toEqual({ K: "v", Q: "x y" });
});

// @covers FR-01.04
test("auth: env token, env key, copied login, else refuse", () => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-auth-"));
  try {
    expect(pickAuthSource({ CLAUDE_CODE_OAUTH_TOKEN: "t" }, home)).toBe("env token");
    expect(pickAuthSource({ ANTHROPIC_API_KEY: "k" }, home)).toBe("env key");
    expect(() => pickAuthSource({}, home)).toThrow(AuthError);
    fs.mkdirSync(path.join(home, ".claude"));
    fs.writeFileSync(loginFile(home), "{}");
    expect(pickAuthSource({}, home)).toBe("copied login");
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("the copied login is removed again, and removal is repeatable", () => {
  const real = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-real-"));
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-temp-"));
  try {
    fs.mkdirSync(path.join(real, ".claude"));
    fs.writeFileSync(loginFile(real), "placeholder");
    const copy = copyLogin(real, temp);
    expect(fs.existsSync(loginFile(temp))).toBe(true);
    copy.remove();
    copy.remove();
    expect(fs.existsSync(loginFile(temp))).toBe(false);
    expect(fs.existsSync(loginFile(real))).toBe(true);
  } finally {
    fs.rmSync(real, { recursive: true, force: true });
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("provisioning writes the permission mode, the real plugins and the folder trust", () => {
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-prov-"));
  try {
    const project = path.join(temp, "p");
    const plugins = provisionHome({ repoRoot: repo, tempHome: temp, projectPath: project, permissionMode: "plan" });
    expect(plugins.length).toBeGreaterThan(5);
    const settings = JSON.parse(fs.readFileSync(path.join(temp, ".claude", "settings.json"), "utf8"));
    expect(settings.permissions.defaultMode).toBe("plan");
    expect(settings.skipDangerousModePermissionPrompt).toBeUndefined();
    const run = plugins.find((p) => p.name === "shipwright-run")!;
    const cache = path.join(temp, ".claude", "plugins", "cache", "shipwright");
    expect(fs.existsSync(path.join(cache, run.name, run.version, ".claude-plugin", "plugin.json"))).toBe(true);
    expect(fs.existsSync(path.join(cache, "shared", "constitution.md"))).toBe(true);
    const state = JSON.parse(fs.readFileSync(path.join(temp, ".claude.json"), "utf8"));
    expect(state.projects[project].hasTrustDialogAccepted).toBe(true);
    expect(JSON.stringify(state)).not.toContain("customApiKeyResponses");
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("shutdown runs every step once, in order, even when one throws", async () => {
  const { Shutdown } = await import("../../src/shutdown.js");
  const calls: string[] = [];
  const s = new Shutdown();
  s.add(() => { calls.push("kill"); throw new Error("already dead"); });
  s.add(() => calls.push("login"));
  expect(s.run()).toBe(1);
  expect(s.run()).toBe(0);
  expect(calls).toEqual(["kill", "login"]);
});

// @covers FR-01.04
test("stale login copies from killed runs are scrubbed; other files stay", async () => {
  const { scrubStaleLogins } = await import("../../src/auth.js");
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-scrub-"));
  try {
    const home = path.join(work, "run-2026-01-01", "home");
    fs.mkdirSync(path.join(home, ".claude"), { recursive: true });
    fs.writeFileSync(loginFile(home), "x");
    fs.writeFileSync(path.join(home, ".claude", "settings.json"), "{}");
    expect(scrubStaleLogins(work, 3_600_000)).toBe(0); // fresh copy: a live run may own it
    expect(scrubStaleLogins(work, 3_600_000, Date.now() + 7_200_000)).toBe(1);
    expect(fs.existsSync(loginFile(home))).toBe(false);
    expect(fs.existsSync(path.join(home, ".claude", "settings.json"))).toBe(true);
    expect(scrubStaleLogins(path.join(work, "missing"), 0)).toBe(0);
  } finally {
    fs.rmSync(work, { recursive: true, force: true });
  }
});

// @covers FR-01.04
test("child env points every home-like location at the temp HOME and keeps PATH and auth", async () => {
  const { childEnv } = await import("../../src/stack.js");
  const home = path.join(os.tmpdir(), "h");
  const env = childEnv(
    { PATH: "/bin", CLAUDE_CONFIG_DIR: "/real", XDG_CONFIG_HOME: "/real", APPDATA: "/real", HOME: "/real", ANTHROPIC_API_KEY: "k" },
    home, { PORT: "1" },
  );
  expect(env.CLAUDE_CONFIG_DIR).toBeUndefined();
  expect(env.XDG_CONFIG_HOME).toBeUndefined();
  expect([env.HOME, env.USERPROFILE]).toEqual([home, home]);
  expect(env.APPDATA?.startsWith(home) && env.LOCALAPPDATA?.startsWith(home)).toBe(true);
  expect([env.PATH, env.ANTHROPIC_API_KEY, env.PORT]).toEqual(["/bin", "k", "1"]);
});
