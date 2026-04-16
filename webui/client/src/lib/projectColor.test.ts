import { describe, it, expect } from 'vitest';
import { getProjectColor } from './projectColor';

describe('getProjectColor', () => {
  it('is deterministic — same projectId yields same color', () => {
    const a = getProjectColor('proj-alpha');
    const b = getProjectColor('proj-alpha');
    expect(a.hue).toBe(b.hue);
    expect(a.hsl).toBe(b.hsl);
    expect(a.hslStripe).toBe(b.hslStripe);
  });

  it('produces an HSL color string', () => {
    const c = getProjectColor('anything');
    expect(c.hsl).toMatch(/^hsl\(\d+(?:\.\d+)? 65% 55%\)$/);
  });

  it('hue is a multiple of 30 and within 0–360', () => {
    const ids = ['a', 'proj-1', 'proj-2', 'xxxxx', 'Shipwright', 'banana'];
    for (const id of ids) {
      const { hue } = getProjectColor(id);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
      expect(hue % 30).toBe(0);
    }
  });

  it('distinct projectIds usually yield distinct hues', () => {
    const ids = ['proj-1', 'proj-2', 'proj-3', 'proj-4', 'proj-5', 'proj-6'];
    const hues = new Set(ids.map((id) => getProjectColor(id).hue));
    // With 12 buckets and 6 unique strings, we expect mostly distinct
    // — at least 3 unique hues. This guards the "most of the time"
    // assertion without over-constraining the hash.
    expect(hues.size).toBeGreaterThanOrEqual(3);
  });

  it('empty string does not crash', () => {
    expect(() => getProjectColor('')).not.toThrow();
    const c = getProjectColor('');
    expect(typeof c.hue).toBe('number');
  });

  // Iterate 14.8.2 — custom color override
  it('returns custom color when customColor param is provided', () => {
    const c = getProjectColor('proj-1', '#ff0000');
    expect(c.hsl).toBe('#ff0000');
    expect(c.hslStripe).toBe('#ff0000');
  });

  it('ignores customColor when undefined (falls back to hash)', () => {
    const withoutOverride = getProjectColor('proj-1');
    const withUndefined = getProjectColor('proj-1', undefined);
    expect(withoutOverride.hsl).toBe(withUndefined.hsl);
    expect(withoutOverride.hslStripe).toBe(withUndefined.hslStripe);
  });
});
