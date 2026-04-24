#!/usr/bin/env node
/**
 * Dev-server restart helper.
 *
 * Kills every stale `tsx watch`, `vite`, or node process that owns webui
 * ports (Hono server + Vite) and then respawns `npm run dev`.
 * Cross-platform (Windows / macOS / Linux).
 *
 * Port discovery:
 *   - PORT env       -> Hono   (default 3847)
 *   - VITE_PORT env  -> Vite   (default 5173)
 *
 * Kill scope is EXACTLY the two configured ports. Prior versions of this
 * script carried a hardcoded VITE_ALT_PORT=5177 entry for "legacy cleanup"
 * — removed in v0.3.2 because it broke the worktree-local contract: with
 * PORT/VITE_PORT overrides in two worktrees, the 5177 hardcode could still
 * terminate an unrelated process on that port.
 *
 * Parallel-worktree scenario: set PORT + VITE_PORT to non-default values in
 * the secondary worktree so the two dev-server stacks do not collide. The
 * `computeKillTargets` helper filters malformed env (empty, negative, NaN)
 * back to defaults and dedups when PORT === VITE_PORT.
 *
 * Motivation: on long-running dev sessions, tsx watch on Windows + chokidar
 * can miss file-change events after git merges, leaving the server running
 * with stale code. Multiple `npm run dev` invocations spawn orphan
 * child processes. This script cleans them up in one command.
 *
 * Usage:
 *     npm run dev:fresh
 *
 * See ADR-018.
 */

/* eslint-disable @typescript-eslint/no-require-imports */
const { execSync, spawn } = require('node:child_process');
const path = require('node:path');
const { computeKillTargets } = require('./kill-targets');

const WEBUI_PORTS = computeKillTargets(process.env, process.platform);
const isWin = process.platform === 'win32';

function log(msg) {
  console.log(`[dev-restart] ${msg}`);
}

/** Return a Set of PIDs listening on any of the given ports. */
function findPidsOnPorts(ports) {
  const pids = new Set();
  if (isWin) {
    for (const port of ports) {
      try {
        const out = execSync(`netstat -ano -p TCP | findstr :${port}`, {
          encoding: 'utf-8',
          stdio: ['ignore', 'pipe', 'ignore'],
        });
        for (const line of out.split(/\r?\n/)) {
          const match = line.trim().match(/\s(\d+)$/);
          if (match) pids.add(match[1]);
        }
      } catch {
        // No listeners on this port — fine.
      }
    }
  } else {
    try {
      const portList = ports.join(',');
      const out = execSync(`lsof -ti tcp:${portList}`, {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      });
      for (const pid of out.split(/\s+/).filter(Boolean)) pids.add(pid);
    } catch {
      // lsof exits 1 when no processes found — fine.
    }
  }
  return pids;
}

/** Return a Set of PIDs whose command line matches tsx*watch*src/index.ts or vite. */
function findWebuiNodeProcesses() {
  const pids = new Set();
  if (isWin) {
    try {
      const out = execSync(
        `powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'tsx.*watch.*src/index\\.ts' -or $_.CommandLine -match 'vite' } | Select-Object -ExpandProperty ProcessId"`,
        { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] },
      );
      for (const pid of out.split(/\r?\n/).filter(Boolean)) pids.add(pid.trim());
    } catch {
      // ignore
    }
  } else {
    try {
      const out = execSync(`pgrep -f "tsx.*watch.*src/index\\.ts|vite"`, {
        encoding: 'utf-8',
        stdio: ['ignore', 'pipe', 'ignore'],
      });
      for (const pid of out.split(/\s+/).filter(Boolean)) pids.add(pid);
    } catch {
      // ignore
    }
  }
  return pids;
}

function killPid(pid) {
  try {
    if (isWin) {
      execSync(`taskkill /PID ${pid} /F /T`, { stdio: 'ignore' });
    } else {
      process.kill(Number(pid), 'SIGKILL');
    }
    return true;
  } catch {
    return false;
  }
}

function main() {
  const portPids = findPidsOnPorts(WEBUI_PORTS);
  const cmdPids = findWebuiNodeProcesses();
  const allPids = new Set([...portPids, ...cmdPids]);

  if (allPids.size === 0) {
    log('No stale processes found. Starting fresh dev server…');
  } else {
    log(`Killing ${allPids.size} stale process(es): ${[...allPids].join(', ')}`);
    for (const pid of allPids) killPid(pid);
  }

  // Give the OS a moment to release the ports.
  const waitMs = 400;
  const start = Date.now();
  while (Date.now() - start < waitMs) {
    // Busy-wait; can't easily do async here without top-level await.
  }

  // Spawn `npm run dev` inside webui/server where tsx watch lives. The
  // client (vite) is not restarted automatically because (a) vite HMR
  // usually makes restart unnecessary and (b) it runs in a separate
  // process the user owns. If you need a fresh client too, run
  //   cd ../client && npm run dev
  // in another terminal.
  const webuiRoot = path.resolve(__dirname, '..');
  const serverDir = path.join(webuiRoot, 'server');
  log(`Spawning "npm run dev" in ${serverDir}`);
  const npmCmd = isWin ? 'npm.cmd' : 'npm';
  const child = spawn(npmCmd, ['run', 'dev'], {
    cwd: serverDir,
    stdio: 'inherit',
    shell: false,
  });

  child.on('exit', (code) => {
    process.exit(code ?? 0);
  });

  // Forward Ctrl+C to the child so it dies cleanly.
  process.on('SIGINT', () => {
    child.kill('SIGINT');
  });
}

main();
