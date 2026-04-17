import { describe, it, expect, beforeEach } from 'vitest';
import { useChatStore } from './chatStore';

/**
 * Iterate 14.14 — chatStore semantics. First-write-wins was correct for
 * the intra-session "ignore duplicate system/init SSE events" case, but
 * blocked the respawn case (iterate 14.12 mid-task model switch) where
 * a second system/init event legitimately reports a different model.
 * New contract: last-write-wins when the model changes; identical writes
 * remain no-ops (preserves idempotency for duplicate SSE events).
 */
describe('chatStore.setSystemInit', () => {
  beforeEach(() => {
    useChatStore.setState({ systemInitByTask: {} });
  });

  it('records the first system/init model', () => {
    useChatStore.getState().setSystemInit('proj::task', { model: 'claude-opus-4-7' });
    expect(useChatStore.getState().systemInitByTask['proj::task']?.model).toBe('claude-opus-4-7');
  });

  it('is a no-op when the same model is written again (idempotent duplicate SSE)', () => {
    const store = useChatStore.getState();
    store.setSystemInit('proj::task', { model: 'claude-opus-4-7' });
    const stateBefore = useChatStore.getState().systemInitByTask;
    store.setSystemInit('proj::task', { model: 'claude-opus-4-7' });
    const stateAfter = useChatStore.getState().systemInitByTask;
    // reference-equal — set() short-circuits on no-op.
    expect(stateAfter).toBe(stateBefore);
  });

  it('REPLACES the model when a new system/init reports a different id (respawn case)', () => {
    const store = useChatStore.getState();
    store.setSystemInit('proj::task', { model: 'claude-opus-4-7' });
    store.setSystemInit('proj::task', { model: 'claude-opus-4-5' });
    expect(useChatStore.getState().systemInitByTask['proj::task']?.model).toBe('claude-opus-4-5');
  });

  it('only touches the specified task key, leaves others untouched', () => {
    const store = useChatStore.getState();
    store.setSystemInit('proj::task-a', { model: 'claude-opus-4-7' });
    store.setSystemInit('proj::task-b', { model: 'claude-sonnet-4-6' });
    store.setSystemInit('proj::task-a', { model: 'claude-opus-4-5' });
    expect(useChatStore.getState().systemInitByTask['proj::task-a']?.model).toBe('claude-opus-4-5');
    expect(useChatStore.getState().systemInitByTask['proj::task-b']?.model).toBe('claude-sonnet-4-6');
  });
});

describe('chatStore.clearSystemInit', () => {
  beforeEach(() => {
    useChatStore.setState({ systemInitByTask: {} });
  });

  it('removes the entry for the given task key', () => {
    const store = useChatStore.getState();
    store.setSystemInit('proj::task', { model: 'claude-opus-4-7' });
    store.clearSystemInit('proj::task');
    expect(useChatStore.getState().systemInitByTask['proj::task']).toBeUndefined();
  });

  it('is a no-op when the task key has no entry', () => {
    const store = useChatStore.getState();
    const stateBefore = useChatStore.getState().systemInitByTask;
    store.clearSystemInit('proj::task');
    const stateAfter = useChatStore.getState().systemInitByTask;
    expect(stateAfter).toBe(stateBefore);
  });
});
