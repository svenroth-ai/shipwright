#!/usr/bin/env node
/* eslint-disable no-console */
/*
 * External-launch PoC — Sub-iterate 0 of Plan D'' (variant a).
 *
 * 10 contract-level checks for the copy-launcher + mtime-discovery architecture.
 * Does NOT spawn any Terminal / VS Code launcher. Does NOT install watchers.
 * Writes results to ~/.claude/plans/external-launch-poc-results.md
 * and JSONL fixtures to webui/server/src/test/fixtures/jsonl/.
 *
 * Invoke from webui/server/:  npx tsx scripts/sdk-poc.ts
 */

import { spawn, spawnSync } from 'node:child_process';
import { mkdir, writeFile, readFile, readdir, stat, appendFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir, homedir, platform } from 'node:os';
import { randomUUID } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const SERVER_DIR = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = path.resolve(SERVER_DIR, '..', '..');
const PROJECTS_DIR = path.join(homedir(), '.claude', 'projects');
const FIXTURE_DIR = path.join(SERVER_DIR, 'src', 'test', 'fixtures', 'jsonl');
const RESULTS_PATH = path.join(homedir(), '.claude', 'plans', 'external-launch-poc-results.md');
const IS_WIN = platform() === 'win32';

// Sven's repo path with embedded space — canonical escaping test subject.
const REPO_ROOT_WITH_SPACE = REPO_ROOT;

// Resolve an absolute path to the claude CLI so spawn() works on Windows without `shell: true`.
// On Windows, `claude` lives as `claude.cmd` (npm shim); plain spawn cannot find it without a shell
// or an explicit extension. `where claude` / `which claude` returns the entries; we pick the .cmd
// on Windows (which cmd.exe understands when we use shell: true — see claudeSpawn below).
function resolveClaudeExecutable(): string {
  const cmd = IS_WIN ? 'where' : 'which';
  const arg = 'claude';
  const r = spawnSync(cmd, [arg], { encoding: 'utf-8', shell: false });
  const lines = ((r.stdout ?? '') as string).split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (IS_WIN) {
    const dotCmd = lines.find((l) => /\.cmd$/i.test(l));
    if (dotCmd) return dotCmd;
  }
  if (lines.length > 0) return lines[0];
  throw new Error(`Cannot locate claude executable on PATH (${cmd} ${arg} returned empty)`);
}

const CLAUDE_BIN = resolveClaudeExecutable();

// Wrapper around child_process.spawn that handles Windows .cmd shim: shell: true + absolute path
// + manual quoting (spawn with shell: true re-parses args as a single shell command). For POSIX
// we use shell: false + the absolute path.
function claudeSpawn(args: string[], opts: { cwd?: string; env?: NodeJS.ProcessEnv }) {
  if (IS_WIN) {
    // Use shell: true so cmd.exe can resolve .cmd. We wrap each arg in double quotes and escape
    // embedded double quotes. Paths with spaces and UUIDs are safe with this minimal escaping.
    const escaped = args.map((a) => `"${String(a).replace(/"/g, '\\"')}"`).join(' ');
    return spawn(`"${CLAUDE_BIN}" ${escaped}`, [], {
      cwd: opts.cwd ?? process.cwd(),
      env: opts.env ?? process.env,
      stdio: ['ignore', 'pipe', 'pipe'],
      shell: true,
      windowsVerbatimArguments: false,
    });
  }
  return spawn(CLAUDE_BIN, args, {
    cwd: opts.cwd ?? process.cwd(),
    env: opts.env ?? process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });
}

// -------- utilities --------

function sleep(ms: number) { return new Promise((r) => setTimeout(r, ms)); }

interface RunResult {
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  durationMs: number;
}

async function runClaude(
  args: string[],
  opts: { cwd?: string; timeoutMs?: number; env?: NodeJS.ProcessEnv } = {},
): Promise<RunResult> {
  const start = performance.now();
  return new Promise((resolve) => {
    const p = claudeSpawn(args, { cwd: opts.cwd, env: opts.env });
    let stdout = '';
    let stderr = '';
    p.stdout?.on('data', (d) => { stdout += d.toString('utf-8'); });
    p.stderr?.on('data', (d) => { stderr += d.toString('utf-8'); });
    const timer = setTimeout(() => { try { p.kill('SIGTERM'); } catch { /* ignore */ } }, opts.timeoutMs ?? 120_000);
    p.on('close', (code, signal) => {
      clearTimeout(timer);
      resolve({ code, signal, stdout, stderr, durationMs: performance.now() - start });
    });
    p.on('error', (err) => {
      clearTimeout(timer);
      stderr += `\n[spawn-error] ${String(err)}`;
      resolve({ code: -1, signal: null, stdout, stderr, durationMs: performance.now() - start });
    });
  });
}

async function readFirstLine(filePath: string): Promise<string | null> {
  try {
    const data = await readFile(filePath, 'utf-8');
    const nl = data.indexOf('\n');
    if (nl === -1) return data.length > 0 ? data : null;
    const line = data.slice(0, nl);
    return line.length > 0 ? line : null;
  } catch { return null; }
}

interface JsonlCandidate { path: string; encodedCwd: string; mtime: number; size: number; }

async function listJsonlCandidates(): Promise<JsonlCandidate[]> {
  let subs: string[] = [];
  try { subs = await readdir(PROJECTS_DIR); } catch { return []; }
  const out: JsonlCandidate[] = [];
  for (const sub of subs) {
    const subPath = path.join(PROJECTS_DIR, sub);
    try {
      const s = await stat(subPath);
      if (!s.isDirectory()) continue;
    } catch { continue; }
    let files: string[] = [];
    try { files = await readdir(subPath); } catch { continue; }
    for (const f of files) {
      if (!f.endsWith('.jsonl')) continue;
      const fp = path.join(subPath, f);
      try {
        const fs = await stat(fp);
        out.push({ path: fp, encodedCwd: sub, mtime: fs.mtimeMs, size: fs.size });
      } catch { /* ignore */ }
    }
  }
  out.sort((a, b) => b.mtime - a.mtime);
  return out;
}

function extractSessionId(obj: unknown): string | null {
  if (!obj || typeof obj !== 'object') return null;
  const anyObj = obj as Record<string, unknown>;
  if (typeof anyObj.sessionId === 'string') return anyObj.sessionId;
  if (typeof anyObj.session_id === 'string') return anyObj.session_id;
  return null;
}

// Discovery algorithm (corrected per PoC findings 2026-04-19):
//   1. PRIMARY: file whose basename is `<uuid>.jsonl` — claude 2.1.114 writes the JSONL under
//      exactly this filename when `--session-id <uuid>` is passed. Works for plain sessions,
//      `--resume` (appends to same file), and `--fork-session` (new file with child uuid).
//   2. SECONDARY (sanity-check, not discovery): scan the FIRST 10 lines of the matched file for
//      a line whose `sessionId` / `session_id` equals our UUID. Required because fork-session
//      files begin with `file-history-snapshot` lines that lack sessionId; the first lines that
//      carry sessionId appear at index 2+.
async function discoverByUuid(uuid: string, topN = 40): Promise<JsonlCandidate | null> {
  const cands = await listJsonlCandidates();
  const wanted = `${uuid}.jsonl`.toLowerCase();
  // 1. Filename-first discovery.
  for (const c of cands) {
    if (path.basename(c.path).toLowerCase() === wanted) {
      if (await fileHasSessionId(c.path, uuid)) return c;
      // Filename matches but sessionId never appears in first lines — still consider a match
      // because filename IS claude's authoritative naming, and this file may still be in the
      // early "file-history-snapshot" prologue phase.
      return c;
    }
  }
  // 2. Fallback: mtime-sorted first-N-lines scan (covers hypothetical future CLI naming change).
  for (const c of cands.slice(0, topN)) {
    if (await fileHasSessionId(c.path, uuid)) return c;
  }
  return null;
}

async function fileHasSessionId(filePath: string, uuid: string, scanLines = 10): Promise<boolean> {
  let data: string;
  try { data = await readFile(filePath, 'utf-8'); } catch { return false; }
  const lines = data.split(/\r?\n/, scanLines + 1);
  for (const line of lines.slice(0, scanLines)) {
    if (!line) continue;
    try {
      const obj = JSON.parse(line);
      if (extractSessionId(obj) === uuid) return true;
    } catch { /* skip malformed line */ }
  }
  return false;
}

async function waitForUuid(
  uuid: string,
  timeoutMs: number,
): Promise<{ candidate: JsonlCandidate; elapsedMs: number } | null> {
  const start = performance.now();
  while (performance.now() - start < timeoutMs) {
    const r = await discoverByUuid(uuid);
    if (r) return { candidate: r, elapsedMs: performance.now() - start };
    await sleep(150);
  }
  return null;
}

async function countLines(filePath: string): Promise<number> {
  try {
    const data = await readFile(filePath, 'utf-8');
    if (!data) return 0;
    return data.split('\n').filter((l) => l.length > 0).length;
  } catch { return 0; }
}

// -------- result accumulator --------

interface CheckResult {
  name: string;
  title: string;
  status: 'pass' | 'fail' | 'skipped';
  durationMs: number;
  evidence: string;
  observations?: Record<string, unknown>;
}

const results: CheckResult[] = [];
const meta = {
  startedAt: new Date().toISOString(),
  claudeVersion: '',
  anthropicApiKeyPresent: Boolean(process.env.ANTHROPIC_API_KEY),
  platform: platform(),
  nodeVersion: process.version,
  projectsDir: PROJECTS_DIR,
  fixtureDir: FIXTURE_DIR,
};

function record(r: CheckResult) {
  results.push(r);
  const icon = r.status === 'pass' ? '✓' : r.status === 'fail' ? '✗' : '–';
  console.log(`[${icon}] ${r.name.padEnd(2)} ${r.title} (${Math.round(r.durationMs)}ms)`);
  if (r.status === 'fail') console.log(`        → ${r.evidence.slice(0, 500)}`);
}

// -------- checks --------

interface SeedSession { uuid: string; workDir: string; }

// Check A: --session-id + mtime discovery + capture cwd-encoding algorithm.
async function checkA(): Promise<SeedSession | null> {
  const t0 = performance.now();
  const uuid = randomUUID();
  const workDir = path.join(tmpdir(), `sdk-poc-a-${Date.now()}`);
  await mkdir(workDir, { recursive: true });
  const run = await runClaude(
    ['--session-id', uuid, '--print', 'Reply with exactly: hello'],
    { cwd: workDir, timeoutMs: 90_000 },
  );
  if (run.code !== 0) {
    record({
      name: 'a', title: '--session-id + mtime discovery', status: 'fail',
      durationMs: performance.now() - t0,
      evidence: `claude exit=${run.code} signal=${run.signal}\nstderr: ${run.stderr.slice(0, 800)}`,
    });
    return null;
  }
  const found = await waitForUuid(uuid, 15_000);
  if (!found) {
    record({
      name: 'a', title: '--session-id + mtime discovery', status: 'fail',
      durationMs: performance.now() - t0,
      evidence: `JSONL with session_id=${uuid} not found in ${PROJECTS_DIR} within 15s`,
    });
    return null;
  }
  record({
    name: 'a', title: '--session-id + mtime discovery', status: 'pass',
    durationMs: performance.now() - t0,
    evidence: `uuid=${uuid}; file=${found.candidate.path}; discovery=${Math.round(found.elapsedMs)}ms; encoded-cwd="${found.candidate.encodedCwd}"; workDir="${workDir}"`,
    observations: {
      uuid,
      workDir,
      encodedCwd: found.candidate.encodedCwd,
      jsonlPath: found.candidate.path,
      discoveryMs: Math.round(found.elapsedMs),
      cwdEncodingObservation: encodingObservation(workDir, found.candidate.encodedCwd),
    },
  });
  return { uuid, workDir };
}

function encodingObservation(cwd: string, encoded: string): Record<string, string> {
  // Windows cwd typical: C:\Users\SvenRoth\AppData\Local\Temp\sdk-poc-a-12345
  // Encoded typical: ----C--Users-SvenRoth-AppData-Local-Temp-sdk-poc-a-12345
  // Hypothesis: replace drive letter + colon + backslash with dashes; backslash -> dash.
  return {
    originalCwd: cwd,
    encodedSubdir: encoded,
    hypothesizedRule: IS_WIN
      ? 'Windows: leading dashes represent the empty root; drive-letter colon is collapsed; every path separator becomes a single dash; no additional escaping of literal dashes or spaces observed here (use mtime+session_id verification, not prediction, as primary discovery).'
      : 'POSIX: leading slash becomes leading dash; every path separator becomes a single dash.',
  };
}

// Check B: launch-bind timing (first-file-appear + first-line-parseable).
async function checkB(): Promise<void> {
  const t0 = performance.now();
  const uuid = randomUUID();
  const workDir = path.join(tmpdir(), `sdk-poc-b-${Date.now()}`);
  await mkdir(workDir, { recursive: true });
  const spawnStart = performance.now();
  const proc = claudeSpawn(['--session-id', uuid, '--print', 'Reply with: bind-timing-ok'], { cwd: workDir });
  proc.stdout?.on('data', () => {});
  proc.stderr?.on('data', () => {});
  let firstAppearMs: number | null = null;
  let firstParseableMs: number | null = null;
  const deadline = performance.now() + 60_000;
  while (performance.now() < deadline) {
    const cand = await discoverByUuidFileOnly(uuid);
    if (cand && firstAppearMs === null) firstAppearMs = performance.now() - spawnStart;
    if (cand) {
      const head = await readFirstLine(cand.path);
      if (head) {
        try {
          JSON.parse(head);
          firstParseableMs = performance.now() - spawnStart;
          break;
        } catch { /* keep polling */ }
      }
    }
    await sleep(50);
  }
  await new Promise((resolve) => proc.on('close', resolve));
  if (firstAppearMs === null || firstParseableMs === null) {
    record({
      name: 'b', title: 'launch-bind timing', status: 'fail',
      durationMs: performance.now() - t0,
      evidence: `firstAppear=${firstAppearMs}ms firstParseable=${firstParseableMs}ms (deadline reached)`,
    });
    return;
  }
  record({
    name: 'b', title: 'launch-bind timing', status: 'pass',
    durationMs: performance.now() - t0,
    evidence: `file first appeared ${Math.round(firstAppearMs)}ms after spawn; first line JSON-parseable ${Math.round(firstParseableMs)}ms after spawn`,
    observations: { firstAppearMs: Math.round(firstAppearMs), firstParseableMs: Math.round(firstParseableMs), uuid },
  });
}

// Discovery variant used in check B — filename-first, for measuring file-appearance latency
// before any JSON content is flushed. Delegates to the same algorithm as discoverByUuid for
// consistency; falls back to filename-match even if no sessionId found anywhere yet.
async function discoverByUuidFileOnly(uuid: string): Promise<JsonlCandidate | null> {
  return discoverByUuid(uuid);
}

// Check C: subscription auth (ANTHROPIC_API_KEY unset → CLI still works).
async function checkC(): Promise<void> {
  const t0 = performance.now();
  if (process.env.ANTHROPIC_API_KEY) {
    record({
      name: 'c', title: 'subscription auth (no API key)', status: 'fail',
      durationMs: performance.now() - t0,
      evidence: 'ANTHROPIC_API_KEY is set — PoC invariant violated; rerun after unsetting.',
    });
    return;
  }
  const env = { ...process.env };
  delete env.ANTHROPIC_API_KEY;
  const uuid = randomUUID();
  const run = await runClaude(
    ['--session-id', uuid, '--print', 'Reply with exactly: subscription-ok'],
    { env, timeoutMs: 60_000 },
  );
  if (run.code !== 0) {
    record({
      name: 'c', title: 'subscription auth (no API key)', status: 'fail',
      durationMs: performance.now() - t0,
      evidence: `claude exit=${run.code}\nstderr: ${run.stderr.slice(0, 600)}`,
    });
    return;
  }
  record({
    name: 'c', title: 'subscription auth (no API key)', status: 'pass',
    durationMs: performance.now() - t0,
    evidence: `ANTHROPIC_API_KEY unset; claude --print exit 0; stdout=${JSON.stringify(run.stdout.slice(0, 120))}`,
  });
}

// Check D: --resume appends to the same JSONL.
async function checkD(seed: SeedSession | null): Promise<void> {
  const t0 = performance.now();
  if (!seed) { record({ name: 'd', title: '--resume appends', status: 'skipped', durationMs: 0, evidence: 'check a did not seed a UUID' }); return; }
  const { uuid: seedUuid, workDir } = seed;
  const foundBefore = await discoverByUuid(seedUuid);
  if (!foundBefore) { record({ name: 'd', title: '--resume appends', status: 'fail', durationMs: performance.now() - t0, evidence: `seed UUID ${seedUuid} not discoverable pre-resume` }); return; }
  const beforeLines = await countLines(foundBefore.path);
  const beforeSize = (await stat(foundBefore.path)).size;
  // --resume must run from the ORIGINAL cwd; claude scopes session lookup by cwd-encoded subdir.
  const run = await runClaude(
    ['--resume', seedUuid, '--print', 'Reply with exactly: carrot'],
    { cwd: workDir, timeoutMs: 60_000 },
  );
  if (run.code !== 0) { record({ name: 'd', title: '--resume appends', status: 'fail', durationMs: performance.now() - t0, evidence: `exit=${run.code}; stderr=${run.stderr.slice(0, 400)}; workDir="${workDir}"` }); return; }
  const foundAfter = await discoverByUuid(seedUuid);
  if (!foundAfter) { record({ name: 'd', title: '--resume appends', status: 'fail', durationMs: performance.now() - t0, evidence: 'post-resume discovery lost the UUID' }); return; }
  const afterLines = await countLines(foundAfter.path);
  const afterSize = (await stat(foundAfter.path)).size;
  const sameFile = foundBefore.path === foundAfter.path;
  const grew = afterLines > beforeLines && afterSize > beforeSize;
  record({
    name: 'd', title: '--resume appends',
    status: sameFile && grew ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `sameFile=${sameFile}; lines ${beforeLines}→${afterLines}; size ${beforeSize}→${afterSize}; path=${foundAfter.path}`,
    observations: { sameFile, beforeLines, afterLines, beforeSize, afterSize, workDir },
  });
}

// Check E: --fork-session creates a NEW file; parent untouched.
async function checkE(seed: SeedSession | null): Promise<void> {
  const t0 = performance.now();
  if (!seed) { record({ name: 'e', title: '--fork-session new file', status: 'skipped', durationMs: 0, evidence: 'check a did not seed a UUID' }); return; }
  const { uuid: seedUuid, workDir } = seed;
  const parent = await discoverByUuid(seedUuid);
  if (!parent) { record({ name: 'e', title: '--fork-session new file', status: 'fail', durationMs: performance.now() - t0, evidence: `parent UUID ${seedUuid} not discoverable` }); return; }
  const parentLinesBefore = await countLines(parent.path);
  const parentSizeBefore = (await stat(parent.path)).size;
  const childUuid = randomUUID();
  const run = await runClaude(
    ['--session-id', childUuid, '--resume', seedUuid, '--fork-session', '--print', 'Reply with exactly: dolphin'],
    { cwd: workDir, timeoutMs: 60_000 },
  );
  if (run.code !== 0) { record({ name: 'e', title: '--fork-session new file', status: 'fail', durationMs: performance.now() - t0, evidence: `exit=${run.code}; stderr=${run.stderr.slice(0, 400)}; workDir="${workDir}"` }); return; }
  const child = await waitForUuid(childUuid, 20_000);
  const parentAfterLines = await countLines(parent.path);
  const parentAfterSize = (await stat(parent.path)).size;
  const parentUntouched = parentAfterLines === parentLinesBefore && parentAfterSize === parentSizeBefore;
  if (!child) { record({ name: 'e', title: '--fork-session new file', status: 'fail', durationMs: performance.now() - t0, evidence: `child UUID ${childUuid} never appeared; parentUntouched=${parentUntouched}` }); return; }
  const differentFile = child.candidate.path !== parent.path;
  record({
    name: 'e', title: '--fork-session new file',
    status: differentFile && parentUntouched ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `child file=${child.candidate.path}; parent=${parent.path}; parentUntouched=${parentUntouched}; differentFile=${differentFile}`,
    observations: { childUuid, parentUuid: seedUuid, parentUntouched, differentFile, childPath: child.candidate.path, workDir },
  });
}

// Check F: --plugin-dir surfaces Shipwright slash commands.
async function checkF(): Promise<void> {
  const t0 = performance.now();
  const pluginRoot = path.join(homedir(), '.claude', 'plugins', 'cache', 'shipwright');
  // Collect all plugin.json-containing dirs one level deep from cache/shipwright/*/<version>.
  const pluginDirs: string[] = [];
  try {
    for (const entry of await readdir(pluginRoot)) {
      const plugDir = path.join(pluginRoot, entry);
      try {
        const s = await stat(plugDir);
        if (!s.isDirectory()) continue;
      } catch { continue; }
      let versions: string[] = [];
      try { versions = await readdir(plugDir); } catch { continue; }
      for (const v of versions) {
        const candidate = path.join(plugDir, v, '.claude-plugin', 'plugin.json');
        if (existsSync(candidate)) pluginDirs.push(path.join(plugDir, v));
      }
    }
  } catch { /* ignore */ }
  if (pluginDirs.length === 0) {
    record({ name: 'f', title: '--plugin-dir surfaces shipwright', status: 'fail', durationMs: performance.now() - t0, evidence: `no plugins found under ${pluginRoot}` });
    return;
  }
  const uuid = randomUUID();
  const pluginArgs = pluginDirs.flatMap((d) => ['--plugin-dir', d]);
  const run = await runClaude(
    ['--session-id', uuid, ...pluginArgs, '--output-format', 'stream-json', '--verbose', '--print', '/help'],
    { timeoutMs: 90_000 },
  );
  if (run.code !== 0) {
    record({ name: 'f', title: '--plugin-dir surfaces shipwright', status: 'fail', durationMs: performance.now() - t0, evidence: `exit=${run.code}; stderr=${run.stderr.slice(0, 400)}` });
    return;
  }
  // Scan stream-json events for any mention of shipwright slash command.
  const mentionsShipwright = /shipwright-(iterate|build|plan|design|project|test|security|deploy|changelog|compliance|preview|run)/i.test(run.stdout);
  // Also: parse any `system` event with a `slash_commands` list.
  let slashCmds: string[] = [];
  for (const line of run.stdout.split(/\r?\n/)) {
    if (!line.trim()) continue;
    try {
      const obj = JSON.parse(line);
      const maybe = (obj as { slash_commands?: unknown }).slash_commands
        ?? (obj as { slashCommands?: unknown }).slashCommands;
      if (Array.isArray(maybe)) slashCmds = slashCmds.concat(maybe.filter((x): x is string => typeof x === 'string'));
    } catch { /* skip */ }
  }
  const hasShipwrightInList = slashCmds.some((c) => /shipwright/i.test(c));
  const pass = mentionsShipwright || hasShipwrightInList;
  record({
    name: 'f', title: '--plugin-dir surfaces shipwright',
    status: pass ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `${pluginDirs.length} plugin-dirs passed; mentionsShipwright=${mentionsShipwright}; slashCmdCount=${slashCmds.length}; slashCmdsShipwrightHits=${slashCmds.filter((c) => /shipwright/i.test(c)).length}`,
    observations: { pluginDirs, slashCmdsSample: slashCmds.slice(0, 20) },
  });
}

// Check G: copy-command escaping across PowerShell / cmd / POSIX with space-in-path.
async function checkG(): Promise<void> {
  const t0 = performance.now();
  const uuidPS = randomUUID();
  const uuidCmd = randomUUID();
  const uuidPosix = randomUUID();

  const sharedPrompt = 'Reply with exactly: shell-ok';
  const dirWithSpace = REPO_ROOT_WITH_SPACE; // guaranteed to contain "AI Backup - Documents"

  // --- PowerShell form ---
  // PS uses single-quotes + literal args; the & call operator executes a command with args.
  // Inside single-quoted PS strings, a literal single-quote would be doubled. No single-quote here.
  const psCommand = `& claude --session-id '${uuidPS}' --add-dir '${dirWithSpace}' --print '${sharedPrompt}'`;
  const psRun = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', psCommand], { encoding: 'utf-8', timeout: 90_000 });

  // --- cmd.exe form ---
  // spawnSync defaults to windowsVerbatimArguments=false, which causes Node to escape internal
  // double-quotes when our command string itself contains them. That mangles the /S /C payload
  // cmd.exe sees. With verbatim args, Node passes our full string untouched to CreateProcess,
  // and cmd.exe strips the outer `"..."` pair per its /S /C rule — which is exactly what a
  // user pasting "this command" into a cmd.exe window would experience.
  const cmdCommand = `claude --session-id "${uuidCmd}" --add-dir "${dirWithSpace}" --print "${sharedPrompt}"`;
  const cmdRun = spawnSync('cmd.exe', ['/S', '/C', `"${cmdCommand}"`], {
    encoding: 'utf-8', timeout: 90_000, windowsVerbatimArguments: true,
  });

  // --- POSIX / bash form (Git Bash on Windows) ---
  // POSIX uses single-quotes. We ship the path exactly as-is because bash interprets the string.
  // Convert backslashes to forward slashes for the bash-accepting form.
  const posixPath = dirWithSpace.replace(/\\/g, '/');
  const posixCommand = `claude --session-id '${uuidPosix}' --add-dir '${posixPath}' --print '${sharedPrompt}'`;
  const bashRun = spawnSync('bash', ['-c', posixCommand], { encoding: 'utf-8', timeout: 90_000 });

  const results = {
    ps: { status: psRun.status, ok: psRun.status === 0, stderr: (psRun.stderr ?? '').slice(0, 400) },
    cmd: { status: cmdRun.status, ok: cmdRun.status === 0, stderr: (cmdRun.stderr ?? '').slice(0, 400) },
    bash: { status: bashRun.status, ok: bashRun.status === 0, stderr: (bashRun.stderr ?? '').slice(0, 400) },
  };

  const passed = Number(results.ps.ok) + Number(results.cmd.ok) + Number(results.bash.ok);
  const allOk = results.ps.ok && results.cmd.ok && results.bash.ok;
  record({
    name: 'g', title: 'shell-escaping (PS / cmd / POSIX)',
    status: allOk ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `dirWithSpace="${dirWithSpace}"; PS=${results.ps.status}; cmd=${results.cmd.status}; bash=${results.bash.status}; passed=${passed}/3`,
    observations: {
      dirWithSpace,
      commandsExecuted: { ps: psCommand, cmd: cmdCommand, bash: posixCommand },
      results,
      uuids: { ps: uuidPS, cmd: uuidCmd, bash: uuidPosix },
    },
  });
}

// Check H: JSONL torn-read + Windows filesystem errors during long response.
async function checkH(): Promise<void> {
  const t0 = performance.now();
  const uuid = randomUUID();
  const workDir = path.join(tmpdir(), `sdk-poc-h-${Date.now()}`);
  await mkdir(workDir, { recursive: true });

  // Prompt designed to produce a long, slow-streamed assistant block.
  const prompt = 'Explain the history of the Unix philosophy in exactly 800 words. Cover Bell Labs, the original Unix team, C, pipe composition, small tools, and the modern legacy. Do not use headings or bullets.';

  const proc = claudeSpawn(['--session-id', uuid, '--print', prompt], { cwd: workDir });
  proc.stdout?.on('data', () => {});
  proc.stderr?.on('data', () => {});

  // Wait for the file to appear.
  let filePath: string | null = null;
  const deadline = performance.now() + 60_000;
  while (performance.now() < deadline) {
    const cand = await discoverByUuidFileOnly(uuid);
    if (cand) { filePath = cand.path; break; }
    await sleep(100);
  }

  const tally = { reads: 0, jsonErrors: 0, ebusy: 0, eperm: 0, eacces: 0, enoent: 0, ok: 0, maxPartialLineBytes: 0 };

  if (!filePath) {
    proc.kill('SIGTERM');
    record({ name: 'h', title: 'torn-read behavior', status: 'fail', durationMs: performance.now() - t0, evidence: 'JSONL file never appeared for torn-read probe' });
    return;
  }

  // Tight read loop until the process closes.
  const closedPromise = new Promise<void>((resolve) => proc.on('close', () => resolve()));
  let closed = false;
  closedPromise.then(() => { closed = true; });

  while (!closed && performance.now() < performance.now() + 300_000 /* hard safety */) {
    tally.reads++;
    try {
      const data = await readFile(filePath, 'utf-8');
      let sawError = false;
      const lines = data.split('\n');
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.length === 0) continue;
        // The final line may be partial — track its byte length but don't parse.
        if (i === lines.length - 1 && !data.endsWith('\n')) {
          tally.maxPartialLineBytes = Math.max(tally.maxPartialLineBytes, Buffer.byteLength(line, 'utf-8'));
          continue;
        }
        try { JSON.parse(line); }
        catch { tally.jsonErrors++; sawError = true; break; }
      }
      if (!sawError) tally.ok++;
    } catch (e: unknown) {
      const code = (e as NodeJS.ErrnoException)?.code ?? '';
      if (code === 'EBUSY') tally.ebusy++;
      else if (code === 'EPERM') tally.eperm++;
      else if (code === 'EACCES') tally.eacces++;
      else if (code === 'ENOENT') tally.enoent++;
      else tally.jsonErrors++;
    }
    await sleep(5);
    if (closed) break;
  }
  await closedPromise;

  // One final read after close to confirm the whole file is JSON-clean.
  let finalClean = false;
  try {
    const data = await readFile(filePath, 'utf-8');
    const lines = data.split('\n').filter((l) => l.length > 0);
    finalClean = lines.every((l) => { try { JSON.parse(l); return true; } catch { return false; } });
  } catch { finalClean = false; }

  const tornEvents = tally.jsonErrors + tally.ebusy + tally.eperm + tally.eacces + tally.enoent;
  const tearFrequencyPct = tally.reads > 0 ? (tornEvents / tally.reads) * 100 : 0;

  record({
    name: 'h', title: 'torn-read behavior',
    status: finalClean ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `reads=${tally.reads}; torn=${tornEvents} (${tearFrequencyPct.toFixed(2)}%); EBUSY=${tally.ebusy}; EPERM=${tally.eperm}; EACCES=${tally.eacces}; ENOENT=${tally.enoent}; JSONparse=${tally.jsonErrors}; finalClean=${finalClean}; maxPartialLineBytes=${tally.maxPartialLineBytes}`,
    observations: { ...tally, tornEvents, tearFrequencyPct: Number(tearFrequencyPct.toFixed(2)), finalClean, filePath },
  });
}

// Check I: event-surface enumeration across 5 scenarios. Captures fixtures.
async function checkI(): Promise<void> {
  const t0 = performance.now();
  await mkdir(FIXTURE_DIR, { recursive: true });

  interface Scenario { id: string; title: string; buildArgs: (uuid: string, sandbox: string) => string[]; envExtra?: Record<string, string>; setup?: (sandbox: string) => Promise<void>; timeoutMs?: number; }

  const scenarios: Scenario[] = [
    {
      id: '01-plain-qa',
      title: 'Plain Q+A',
      buildArgs: (uuid) => ['--session-id', uuid, '--output-format', 'stream-json', '--verbose', '--print', 'What is 2+2? Reply with only the number.'],
    },
    {
      id: '02-tool-read-bash',
      title: 'Read + Bash tool sequence',
      setup: async (sandbox) => {
        await writeFile(path.join(sandbox, 'target.txt'), 'the answer is 42\n', 'utf-8');
      },
      buildArgs: (uuid, sandbox) => [
        '--session-id', uuid,
        '--add-dir', sandbox,
        '--permission-mode', 'bypassPermissions',
        '--output-format', 'stream-json', '--verbose',
        '--print', `Read ${path.join(sandbox, 'target.txt').replace(/\\/g, '/')} and reply with its contents verbatim.`,
      ],
      timeoutMs: 120_000,
    },
    {
      id: '03-plan-mode',
      title: 'Plan mode',
      buildArgs: (uuid) => ['--session-id', uuid, '--permission-mode', 'plan', '--output-format', 'stream-json', '--verbose', '--print', 'Produce a plan (no file writes) for adding a CHANGELOG.md to a new repository.'],
    },
    {
      id: '04-slash-invocation',
      title: 'Slash-command invocation',
      buildArgs: (uuid) => ['--session-id', uuid, '--output-format', 'stream-json', '--verbose', '--print', '/help'],
    },
    {
      id: '05-error-induction',
      title: 'Error-inducing tool call',
      buildArgs: (uuid, sandbox) => [
        '--session-id', uuid,
        '--add-dir', sandbox,
        '--permission-mode', 'bypassPermissions',
        '--output-format', 'stream-json', '--verbose',
        '--print', `Attempt to read ${path.join(sandbox, 'nonexistent-file-that-does-not-exist.xyz').replace(/\\/g, '/')} and report what went wrong.`,
      ],
      timeoutMs: 120_000,
    },
  ];

  const allTypes = new Set<string>();
  const perScenario: Array<{ id: string; title: string; typeCounts: Record<string, number>; lineCount: number; exitCode: number | null; fixtureFile: string }> = [];

  for (const sc of scenarios) {
    const uuid = randomUUID();
    const sandbox = path.join(tmpdir(), `sdk-poc-i-${sc.id}-${Date.now()}`);
    await mkdir(sandbox, { recursive: true });
    if (sc.setup) await sc.setup(sandbox);
    const run = await runClaude(sc.buildArgs(uuid, sandbox), { cwd: sandbox, timeoutMs: sc.timeoutMs ?? 90_000 });
    const typeCounts: Record<string, number> = {};
    let lineCount = 0;
    for (const line of run.stdout.split(/\r?\n/)) {
      if (!line.trim()) continue;
      lineCount++;
      try {
        const obj = JSON.parse(line);
        const t = typeof (obj as { type?: unknown }).type === 'string' ? (obj as { type: string }).type : '(no-type)';
        const st = typeof (obj as { subtype?: unknown }).subtype === 'string' ? `:${(obj as { subtype: string }).subtype}` : '';
        const key = `${t}${st}`;
        typeCounts[key] = (typeCounts[key] ?? 0) + 1;
        allTypes.add(key);
      } catch {
        typeCounts['(parse-error)'] = (typeCounts['(parse-error)'] ?? 0) + 1;
      }
    }
    const fixtureFile = path.join(FIXTURE_DIR, `${sc.id}.stream.jsonl`);
    await writeFile(fixtureFile, run.stdout, 'utf-8');
    // Also capture the raw session JSONL (the on-disk session-parser target).
    const diskCand = await discoverByUuid(uuid);
    if (diskCand) {
      const diskFixture = path.join(FIXTURE_DIR, `${sc.id}.session.jsonl`);
      try { await writeFile(diskFixture, await readFile(diskCand.path, 'utf-8'), 'utf-8'); } catch { /* ignore */ }
    }
    perScenario.push({ id: sc.id, title: sc.title, typeCounts, lineCount, exitCode: run.code, fixtureFile });
    console.log(`      · ${sc.id} exit=${run.code} lines=${lineCount} types=${Object.keys(typeCounts).join(',')}`);
  }

  const passed = perScenario.every((p) => p.lineCount > 0);
  record({
    name: 'i', title: 'event-surface enumeration (5 scenarios)',
    status: passed ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `distinct top-level type[:subtype] values across scenarios: ${Array.from(allTypes).sort().join(', ')}`,
    observations: { allTypesSorted: Array.from(allTypes).sort(), perScenario, fixtureDir: FIXTURE_DIR },
  });
}

// Check J: concurrent-launch correlation — two spawns same cwd within 1s, distinct UUIDs.
async function checkJ(): Promise<void> {
  const t0 = performance.now();
  const sharedCwd = path.join(tmpdir(), `sdk-poc-j-${Date.now()}`);
  await mkdir(sharedCwd, { recursive: true });
  const uuidA = randomUUID();
  const uuidB = randomUUID();

  const procA = claudeSpawn(['--session-id', uuidA, '--print', 'Reply with: A'], { cwd: sharedCwd });
  // Small but <1s offset to simulate "same-second" launch.
  await sleep(150);
  const procB = claudeSpawn(['--session-id', uuidB, '--print', 'Reply with: B'], { cwd: sharedCwd });

  procA.stdout?.on('data', () => {});
  procA.stderr?.on('data', () => {});
  procB.stdout?.on('data', () => {});
  procB.stderr?.on('data', () => {});

  const waitClose = (p: ReturnType<typeof spawn>) => new Promise<number | null>((resolve) => p.on('close', (c) => resolve(c)));
  const [exitA, exitB] = await Promise.all([waitClose(procA), waitClose(procB)]);

  const foundA = await waitForUuid(uuidA, 20_000);
  const foundB = await waitForUuid(uuidB, 20_000);

  const distinctFiles = foundA && foundB ? foundA.candidate.path !== foundB.candidate.path : false;
  // Cross-binding check: open each file, assert first-line session_id matches the expected UUID (not the other one).
  let aBindsToA = false, bBindsToB = false;
  if (foundA) {
    const head = await readFirstLine(foundA.candidate.path);
    try { aBindsToA = head ? extractSessionId(JSON.parse(head)) === uuidA : false; } catch { aBindsToA = false; }
  }
  if (foundB) {
    const head = await readFirstLine(foundB.candidate.path);
    try { bBindsToB = head ? extractSessionId(JSON.parse(head)) === uuidB : false; } catch { bBindsToB = false; }
  }

  const pass = Boolean(foundA && foundB) && distinctFiles && aBindsToA && bBindsToB && exitA === 0 && exitB === 0;
  record({
    name: 'j', title: 'concurrent-launch correlation',
    status: pass ? 'pass' : 'fail',
    durationMs: performance.now() - t0,
    evidence: `exitA=${exitA} exitB=${exitB}; foundA=${Boolean(foundA)} foundB=${Boolean(foundB)}; distinctFiles=${distinctFiles}; aBindsToA=${aBindsToA}; bBindsToB=${bBindsToB}; sharedCwd="${sharedCwd}"`,
    observations: {
      uuidA, uuidB,
      pathA: foundA?.candidate.path ?? null, pathB: foundB?.candidate.path ?? null,
      distinctFiles, aBindsToA, bBindsToB,
    },
  });
}

// -------- markdown writer --------

function toMarkdown(): string {
  const rows = results.map((r) => `| ${r.name} | ${r.title} | ${r.status.toUpperCase()} | ${Math.round(r.durationMs)} ms |`).join('\n');
  const summary = {
    pass: results.filter((r) => r.status === 'pass').length,
    fail: results.filter((r) => r.status === 'fail').length,
    skipped: results.filter((r) => r.status === 'skipped').length,
  };

  const sections = results.map((r) => {
    const obs = r.observations ? '\n\n```json\n' + JSON.stringify(r.observations, null, 2) + '\n```' : '';
    return `### Check ${r.name} — ${r.title}\n\n- Status: **${r.status.toUpperCase()}**\n- Duration: ${Math.round(r.durationMs)} ms\n- Evidence: ${r.evidence}${obs}\n`;
  }).join('\n');

  return `# External-launch PoC results (Sub-iterate 0, Plan D'' variant a)

Generated: ${meta.startedAt}
Platform: ${meta.platform}
Node: ${meta.nodeVersion}
Claude CLI: ${meta.claudeVersion}
ANTHROPIC_API_KEY present at run time: ${meta.anthropicApiKeyPresent}
Projects dir scanned: ${meta.projectsDir}
Fixture dir: ${meta.fixtureDir}

## Summary

- Pass: ${summary.pass}
- Fail: ${summary.fail}
- Skipped: ${summary.skipped}

| # | Check | Status | Duration |
|---|-------|--------|----------|
${rows}

${summary.fail === 0
    ? '**VERDICT: all checks passed.** MIN_SUPPORTED_CLI = ' + meta.claudeVersion.trim()
    : '**VERDICT: failures present — do NOT proceed to Sub-iterate 0.5 without investigating.**'}

## Detail

${sections}
`;
}

// -------- main --------

async function main(): Promise<void> {
  console.log('External-launch PoC starting…');
  // Claude version — uses the same Windows-aware resolution as the PoC spawns.
  const v = IS_WIN
    ? spawnSync(`"${CLAUDE_BIN}"`, ['--version'], { encoding: 'utf-8', shell: true })
    : spawnSync(CLAUDE_BIN, ['--version'], { encoding: 'utf-8', shell: false });
  meta.claudeVersion = ((v.stdout ?? '') as string).trim();
  console.log(`Claude CLI: ${meta.claudeVersion}`);
  console.log(`Platform: ${meta.platform}  Node: ${meta.nodeVersion}`);
  console.log(`ANTHROPIC_API_KEY present: ${meta.anthropicApiKeyPresent}`);
  if (meta.anthropicApiKeyPresent) {
    console.error('ABORT: ANTHROPIC_API_KEY must be unset for subscription-auth invariant.');
    process.exit(2);
  }

  // Run checks sequentially to avoid cross-check interference in the mtime scan.
  const seedUuid = await checkA();
  await checkB();
  await checkC();
  await checkD(seedUuid);
  await checkE(seedUuid);
  await checkF();
  await checkG();
  await checkH();
  await checkI();
  await checkJ();

  // Persist results.
  await mkdir(path.dirname(RESULTS_PATH), { recursive: true });
  await writeFile(RESULTS_PATH, toMarkdown(), 'utf-8');
  console.log(`\nResults written to ${RESULTS_PATH}`);
  console.log(`Fixtures written to ${FIXTURE_DIR}`);

  const failed = results.filter((r) => r.status === 'fail').length;
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error('PoC crashed:', err);
  process.exit(2);
});
