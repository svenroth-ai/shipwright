/**
 * Tests for computeKillTargets — the port-selection helper used by
 * dev-restart.js. Pure function, no I/O, cross-platform.
 *
 * Run: node --test webui/scripts/kill-targets.test.js
 */

const { test } = require('node:test');
const assert = require('node:assert/strict');
const { computeKillTargets } = require('./kill-targets');

test('defaults: both ports at their defaults', () => {
  const ports = computeKillTargets({}, 'linux');
  assert.deepEqual([...ports].sort((a, b) => a - b), [3847, 5173]);
});

test('PORT override only', () => {
  const ports = computeKillTargets({ PORT: '3848' }, 'linux');
  assert.deepEqual([...ports].sort((a, b) => a - b), [3848, 5173]);
});

test('VITE_PORT override only', () => {
  const ports = computeKillTargets({ VITE_PORT: '5174' }, 'linux');
  assert.deepEqual([...ports].sort((a, b) => a - b), [3847, 5174]);
});

test('both overrides — kill scope is exactly the two configured ports', () => {
  const ports = computeKillTargets(
    { PORT: '3848', VITE_PORT: '5174' },
    'linux',
  );
  assert.deepEqual([...ports].sort((a, b) => a - b), [3848, 5174]);
  // Regression for M1: explicit 5177 must NOT sneak into the kill list.
  assert.ok(!ports.includes(5177), 'kill list must not contain stale 5177');
});

test('user explicitly sets VITE_PORT=5177 — kill target honors it', () => {
  // The point: we do not suppress 5177, we just stop HARDCODING it.
  const ports = computeKillTargets({ VITE_PORT: '5177' }, 'linux');
  assert.deepEqual([...ports].sort((a, b) => a - b), [3847, 5177]);
});

test('malformed env values are filtered out', () => {
  // NaN, empty, negative, zero — defaults must fill in.
  const cases = [
    { PORT: '' },
    { PORT: 'abc' },
    { PORT: '-1' },
    { PORT: '0' },
    { VITE_PORT: 'NaN' },
    { VITE_PORT: '-5' },
    { VITE_PORT: '0' },
  ];
  for (const env of cases) {
    const ports = computeKillTargets(env, 'linux');
    assert.ok(
      ports.length === 2 || ports.length === 1,
      `expected 1-2 ports for env=${JSON.stringify(env)}, got ${ports.join(',')}`,
    );
    assert.ok(
      ports.every((p) => Number.isFinite(p) && p > 0),
      `malformed port leaked for env=${JSON.stringify(env)}: ${ports.join(',')}`,
    );
  }
});

test('windows and posix produce the same kill-target list', () => {
  const envA = { PORT: '3848', VITE_PORT: '5174' };
  assert.deepEqual(
    computeKillTargets(envA, 'win32'),
    computeKillTargets(envA, 'linux'),
  );
  assert.deepEqual(
    computeKillTargets(envA, 'win32'),
    computeKillTargets(envA, 'darwin'),
  );
});

test('deduplicates when PORT equals VITE_PORT', () => {
  // Pathological but possible — user mis-configures both to the same port.
  const ports = computeKillTargets({ PORT: '5555', VITE_PORT: '5555' }, 'linux');
  assert.deepEqual(ports, [5555]);
});

test('no hardcoded 5177 appears for any default-or-custom env', () => {
  // The whole point of M1: 5177 is never in the kill list unless the
  // user explicitly sets PORT or VITE_PORT to 5177.
  const scenarios = [
    {},
    { PORT: '3847' },
    { VITE_PORT: '5173' },
    { PORT: '3848', VITE_PORT: '5174' },
    { PORT: '9000', VITE_PORT: '9001' },
  ];
  for (const env of scenarios) {
    const ports = computeKillTargets(env, 'linux');
    assert.ok(
      !ports.includes(5177),
      `5177 leaked into kill list for env=${JSON.stringify(env)}`,
    );
  }
});
