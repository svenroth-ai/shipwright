import { describe, it, expect, vi, afterEach } from 'vitest';
import { pasteFromClipboard, looksLikePath } from './filePicker';

/**
 * Iterate 14.7.1 — unit tests for the clipboard-based directory picker.
 * The dual goals: returning a usable path from the clipboard, and
 * degrading gracefully when the browser lacks clipboard permission.
 */

const originalClipboard = Object.getOwnPropertyDescriptor(globalThis.navigator, 'clipboard');

afterEach(() => {
  if (originalClipboard) {
    Object.defineProperty(globalThis.navigator, 'clipboard', originalClipboard);
  } else {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    delete (globalThis.navigator as any).clipboard;
  }
});

function installClipboard(readText: () => Promise<string>) {
  Object.defineProperty(globalThis.navigator, 'clipboard', {
    configurable: true,
    value: { readText },
  });
}

describe('pasteFromClipboard', () => {
  it('returns the clipboard contents when the API succeeds', async () => {
    installClipboard(() => Promise.resolve('C:\\Users\\me\\my-app'));
    await expect(pasteFromClipboard()).resolves.toBe('C:\\Users\\me\\my-app');
  });

  it('returns null when clipboard API is missing', async () => {
    Object.defineProperty(globalThis.navigator, 'clipboard', {
      configurable: true,
      value: undefined,
    });
    await expect(pasteFromClipboard()).resolves.toBeNull();
  });

  it('returns null when clipboard.readText throws (permission denied)', async () => {
    installClipboard(() => Promise.reject(new Error('NotAllowedError')));
    await expect(pasteFromClipboard()).resolves.toBeNull();
  });

  it('returns null when clipboard is empty', async () => {
    installClipboard(() => Promise.resolve(''));
    await expect(pasteFromClipboard()).resolves.toBeNull();
  });
});

describe('looksLikePath', () => {
  it('accepts unix-style paths', () => {
    expect(looksLikePath('/tmp/my-app')).toBe(true);
    expect(looksLikePath('/Users/sven/projects/shipwright')).toBe(true);
  });

  it('accepts windows-style paths', () => {
    expect(looksLikePath('C:\\Users\\me\\app')).toBe(true);
    expect(looksLikePath('D:/projects/app')).toBe(true);
  });

  it('rejects plain text and empty strings', () => {
    expect(looksLikePath('')).toBe(false);
    expect(looksLikePath('hello world')).toBe(false);
    expect(looksLikePath('   ')).toBe(false);
  });

  // Ensures we silence the unused-import lint for vi in simple suites.
  it('safely ignores vi', () => {
    expect(typeof vi.fn).toBe('function');
  });
});
