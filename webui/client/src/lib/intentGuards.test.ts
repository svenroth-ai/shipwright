import { describe, it, expect } from 'vitest';
import { shouldSkipClassification } from './intentGuards';

describe('shouldSkipClassification', () => {
  it('skips short messages', () => {
    expect(shouldSkipClassification('fix bug')).toBe(true);
  });

  it('skips slash commands', () => {
    expect(shouldSkipClassification('/shipwright-build @plan.md')).toBe(true);
  });

  it('skips questions', () => {
    expect(shouldSkipClassification('What does this function do?')).toBe(true);
    expect(shouldSkipClassification('Can you explain the auth flow?')).toBe(true);
  });

  it('skips greetings', () => {
    expect(shouldSkipClassification('Hello there')).toBe(true);
    expect(shouldSkipClassification('Thanks for the help')).toBe(true);
  });

  it('does not skip actionable messages', () => {
    expect(shouldSkipClassification('Add a dark mode toggle to the settings page')).toBe(false);
    expect(shouldSkipClassification('Fix the login bug where users get redirected to 404')).toBe(false);
  });
});
