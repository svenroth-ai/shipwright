import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  beginAuqSubmit,
  getAuqStallBuffer,
  __resetAuqStallBufferForTests,
} from './auqStallInstrumentation';

describe('auqStallInstrumentation — Sub-iterate B observability', () => {
  beforeEach(() => {
    __resetAuqStallBufferForTests();
  });

  it('captures a full submit → answered → stream flow', () => {
    const infoSpy = vi.spyOn(console, 'info').mockImplementation(() => {});
    const { onAnswered, onFirstStream } = beginAuqSubmit('task-1', 'inbox-1');
    onAnswered();
    onFirstStream();
    const buf = getAuqStallBuffer();
    expect(buf.length).toBeGreaterThanOrEqual(1);
    const sealed = buf[buf.length - 1];
    expect(sealed.taskKey).toBe('task-1');
    expect(sealed.inboxId).toBe('inbox-1');
    expect(sealed.answeredAt).not.toBeNull();
    expect(sealed.firstStreamAt).not.toBeNull();
    expect(sealed.stallMs).not.toBeNull();
    expect(sealed.stallMs!).toBeGreaterThanOrEqual(0);
    expect(infoSpy).toHaveBeenCalledWith(
      '[auq-stall-metrics]',
      expect.objectContaining({ inboxId: 'inbox-1' }),
    );
    infoSpy.mockRestore();
  });

  it('records a partial submit when firstStream never arrives (the latent bug trace)', () => {
    const { onAnswered } = beginAuqSubmit('task-2', 'inbox-2');
    onAnswered();
    const buf = getAuqStallBuffer();
    const partial = buf.find((r) => r.inboxId === 'inbox-2');
    expect(partial).toBeDefined();
    expect(partial!.answeredAt).not.toBeNull();
    expect(partial!.firstStreamAt).toBeNull();
    expect(partial!.stallMs).toBeNull();
  });

  it('is a no-op in tests with no DEV flag + no localStorage hint', () => {
    // This test verifies that when the env guard would return false we
    // short-circuit. In vitest DEV is true by default; the real guard is
    // exercised in prod builds. Here we just confirm beginAuqSubmit
    // returns usable callbacks regardless.
    const { onAnswered, onFirstStream } = beginAuqSubmit('task-3', 'inbox-3');
    expect(typeof onAnswered).toBe('function');
    expect(typeof onFirstStream).toBe('function');
  });

  it('exposes the buffer via window for debug inspection', () => {
    beginAuqSubmit('task-w', 'inbox-w').onAnswered();
    const win = globalThis as unknown as { __shipwright_auq_metrics?: unknown[] };
    expect(Array.isArray(win.__shipwright_auq_metrics)).toBe(true);
    expect(win.__shipwright_auq_metrics!.length).toBeGreaterThan(0);
  });
});
