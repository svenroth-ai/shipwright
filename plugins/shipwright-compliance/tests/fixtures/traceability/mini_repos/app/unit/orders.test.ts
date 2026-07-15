// Vitest unit — traceability fixture (DATA, not executed here).
// Demonstrates BOTH TS/JS non-native forms: the `// @covers` comment (binds to
// the next test) and the title-suffix form. Both bind to FR-03.03.

import { describe, it, expect } from 'vitest';

describe('order persistence', () => {
  // @covers FR-03.03
  it('writes the order row', () => {
    expect(persistOrder({ id: 1 })).toBe(true);
  });

  it('rejects a duplicate order @FR-03.03', () => {
    expect(() => persistOrder({ id: 1, dup: true })).toThrow();
  });
});
