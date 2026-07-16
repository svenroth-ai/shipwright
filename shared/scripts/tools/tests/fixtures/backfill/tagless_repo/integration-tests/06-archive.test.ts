// Vitest integration — backfill fixture (DATA, not executed here).
// The `06-` filename prefix maps to split 06, whose sole active FR is FR-06.01
// → a deterministic unique_split match → the engine auto-writes a
// covers-comment. Starts untagged.

import { test, expect } from 'vitest';

test('archives an old campaign to cold storage', () => {
  expect(archive({ id: 1 })).toBe(true);
});
