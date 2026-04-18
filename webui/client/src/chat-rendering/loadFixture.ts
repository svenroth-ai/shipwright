import type { ChatMessage } from '../types';

/**
 * Eagerly glob every fixture via Vite at build/test time. Raw JSONL contents
 * are inlined — no Node fs dependency, which keeps the browser bundle happy
 * and tsc (no @types/node) clean.
 *
 * Test-only helper. Do NOT import from production code.
 */
const fixtureModules = import.meta.glob<string>(
  '../test/fixtures/ndjson-transcripts/*.jsonl',
  { query: '?raw', import: 'default', eager: true }
);

const fixtures: Record<string, string> = {};
for (const [path, raw] of Object.entries(fixtureModules)) {
  const match = path.match(/([^/\\]+)\.jsonl$/);
  if (match) fixtures[match[1]] = raw;
}

export function loadFixture(name: string): ChatMessage[] {
  const key = name.endsWith('.jsonl') ? name.replace(/\.jsonl$/, '') : name;
  const raw = fixtures[key];
  if (!raw) {
    throw new Error(`Fixture not found: ${name}. Available: ${Object.keys(fixtures).join(', ')}`);
  }
  return raw
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as ChatMessage);
}

export function listFixtureNames(): string[] {
  return Object.keys(fixtures).sort();
}
