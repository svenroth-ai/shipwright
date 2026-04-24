/* eslint-disable @typescript-eslint/no-require-imports */
/**
 * Port-selection helper for dev-restart.js.
 *
 * Pure function: no subprocess calls, no filesystem. The kill-scope is
 * exactly the two configured ports (Hono + Vite), each with a default.
 *
 * Worktree-parallel contract: if the operator sets PORT and VITE_PORT for
 * their worktree, this function returns ONLY those ports — nothing
 * hardcoded, nothing leaked from a different worktree's config. The
 * historic VITE_ALT_PORT=5177 hardcode was removed in v0.3.2.
 */

const DEFAULT_HONO_PORT = 3847;
const DEFAULT_VITE_PORT = 5173;

/**
 * @param {Record<string,string|undefined>} env
 * @param {string} _platform  // reserved for future platform-specific overrides
 * @returns {number[]} deduped, finite, positive kill targets
 */
function computeKillTargets(env, _platform) {
  const honoPort = parsePort(env.PORT, DEFAULT_HONO_PORT);
  const vitePort = parsePort(env.VITE_PORT, DEFAULT_VITE_PORT);
  const seen = new Set();
  const out = [];
  for (const p of [honoPort, vitePort]) {
    if (!Number.isFinite(p) || p <= 0) continue;
    if (seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  return out;
}

function parsePort(raw, fallback) {
  if (raw === undefined || raw === null || raw === '') return fallback;
  const n = parseInt(String(raw), 10);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return n;
}

module.exports = { computeKillTargets };
