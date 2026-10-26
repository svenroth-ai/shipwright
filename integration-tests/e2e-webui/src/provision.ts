// Provisions the temp HOME a real agent run needs: the real Shipwright plugins from THIS checkout in the
// plugin cache (same layout update-marketplace.sh produces), settings with the permission mode, and the
// onboarding / folder-trust state. Deliberately NOT the WebUI harness's fake plugin cache and uv shim.
import fs from "node:fs";
import path from "node:path";

const SKIP_DIRS = new Set(["node_modules", "__pycache__", ".venv", ".git", ".pytest_cache"]);
const MARKETPLACE = "shipwright";

function copyTree(from: string, to: string): void {
  fs.cpSync(from, to, { recursive: true, filter: (src) => !SKIP_DIRS.has(path.basename(src)) });
}

export interface PluginInfo {
  name: string;
  version: string;
  dir: string;
}

export function listPlugins(repoRoot: string): PluginInfo[] {
  const root = path.join(repoRoot, "plugins");
  const out: PluginInfo[] = [];
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const manifest = path.join(root, entry.name, ".claude-plugin", "plugin.json");
    if (!entry.isDirectory() || !fs.existsSync(manifest)) continue;
    const json = JSON.parse(fs.readFileSync(manifest, "utf8")) as { name?: string; version?: string };
    out.push({ name: json.name ?? entry.name, version: json.version ?? "0.0.0", dir: path.join(root, entry.name) });
  }
  return out;
}

export interface ProvisionInput {
  repoRoot: string;
  tempHome: string;
  projectPath: string;
  permissionMode: string;
  /** Last 20 characters of ANTHROPIC_API_KEY, when that is the auth source (Claude Code asks once otherwise). */
  apiKeyTail?: string;
}

function writeJson(file: string, data: unknown): void {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(data, null, 2), "utf8");
}

export function provisionHome(input: ProvisionInput): PluginInfo[] {
  const { repoRoot, tempHome, projectPath, permissionMode } = input;
  const claude = path.join(tempHome, ".claude");
  const cache = path.join(claude, "plugins", "cache", MARKETPLACE);
  const now = new Date().toISOString();

  copyTree(path.join(repoRoot, "shared"), path.join(cache, "shared"));
  const plugins = listPlugins(repoRoot);
  const installed: Record<string, unknown[]> = {};
  const enabled: Record<string, boolean> = {};
  for (const p of plugins) {
    const target = path.join(cache, p.name, p.version);
    copyTree(p.dir, target);
    const id = `${p.name}@${MARKETPLACE}`;
    installed[id] = [{ scope: "user", installPath: target, version: p.version, installedAt: now, lastUpdated: now }];
    enabled[id] = true;
  }
  writeJson(path.join(claude, "plugins", "installed_plugins.json"), { version: 2, plugins: installed });
  writeJson(path.join(claude, "plugins", "known_marketplaces.json"), {
    [MARKETPLACE]: { source: { source: "directory", path: repoRoot }, installLocation: repoRoot, lastUpdated: now },
  });

  const settings: Record<string, unknown> = { enabledPlugins: enabled, permissions: { defaultMode: permissionMode } };
  // The acceptance flag the dangerous mode needs; harmless for the other modes, so only set for this one.
  if (permissionMode === "bypassPermissions") settings.skipDangerousModePermissionPrompt = true;
  writeJson(path.join(claude, "settings.json"), settings);

  const trusted = { hasTrustDialogAccepted: true, hasCompletedProjectOnboarding: true, allowedTools: [] };
  // Claude Code keys projects by path; Windows may use either slash style, so trust both spellings.
  const state: Record<string, unknown> = {
    hasCompletedOnboarding: true,
    projects: { [projectPath]: trusted, [projectPath.replace(/\\/g, "/")]: trusted },
  };
  if (input.apiKeyTail) state.customApiKeyResponses = { approved: [input.apiKeyTail], rejected: [] };
  writeJson(path.join(tempHome, ".claude.json"), state);
  // The agent commits run with HOME = the temp HOME, which has no git identity of its own.
  fs.writeFileSync(path.join(tempHome, ".gitconfig"), "[user]\n\tname = Shipwright E2E\n\temail = e2e@example.invalid\n", "utf8");
  return plugins;
}
