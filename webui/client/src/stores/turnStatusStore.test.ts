import { describe, it, expect, beforeEach } from 'vitest';
import { useTurnStatusStore, taskKeyOf } from './turnStatusStore';

function reset() {
  useTurnStatusStore.setState({ byTask: {} });
}

describe('turnStatusStore', () => {
  beforeEach(reset);

  it('ensure creates a slot for an unknown task and returns idle', () => {
    const slot = useTurnStatusStore.getState().ensure('p::t');
    expect(slot.status).toBe('idle');
    expect(slot.lastEventAt).toBe(0);
    expect(slot.watchdogStale).toBe(false);
    expect(useTurnStatusStore.getState().byTask['p::t']).toBeDefined();
  });

  it('ensure is idempotent — same call twice returns the existing slot', () => {
    const { ensure, setStatus } = useTurnStatusStore.getState();
    ensure('p::t');
    setStatus('p::t', 'streaming');
    const after = ensure('p::t');
    expect(after.status).toBe('streaming');
  });

  it('setStatus updates one task without touching others', () => {
    const { setStatus } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    setStatus('p::b', 'awaiting_model');

    const { byTask } = useTurnStatusStore.getState();
    expect(byTask['p::a'].status).toBe('streaming');
    expect(byTask['p::b'].status).toBe('awaiting_model');
  });

  it('setStatus is a no-op when status does not change', () => {
    const { setStatus } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    const before = useTurnStatusStore.getState().byTask;
    setStatus('p::a', 'streaming');
    expect(useTurnStatusStore.getState().byTask).toBe(before);
  });

  it('setStatus clears watchdogStale when leaving streaming', () => {
    const { setStatus, markWatchdogStale } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    markWatchdogStale('p::a', true);
    expect(useTurnStatusStore.getState().byTask['p::a'].watchdogStale).toBe(true);

    setStatus('p::a', 'idle');
    expect(useTurnStatusStore.getState().byTask['p::a'].watchdogStale).toBe(false);
  });

  it('recordEvent advances lastEventAt and resets watchdogStale', () => {
    const { setStatus, markWatchdogStale, recordEvent } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    markWatchdogStale('p::a', true);

    recordEvent('p::a', 42);
    const slot = useTurnStatusStore.getState().byTask['p::a'];
    expect(slot.lastEventAt).toBe(42);
    expect(slot.watchdogStale).toBe(false);
  });

  it('markWatchdogStale toggles without touching status', () => {
    const { setStatus, markWatchdogStale } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    markWatchdogStale('p::a', true);
    let slot = useTurnStatusStore.getState().byTask['p::a'];
    expect(slot.watchdogStale).toBe(true);
    expect(slot.status).toBe('streaming');

    markWatchdogStale('p::a', false);
    slot = useTurnStatusStore.getState().byTask['p::a'];
    expect(slot.watchdogStale).toBe(false);
    expect(slot.status).toBe('streaming');
  });

  it('markWatchdogStale is a no-op when value unchanged', () => {
    const { markWatchdogStale } = useTurnStatusStore.getState();
    markWatchdogStale('p::a', false);
    const before = useTurnStatusStore.getState().byTask;
    markWatchdogStale('p::a', false);
    expect(useTurnStatusStore.getState().byTask).toBe(before);
  });

  it('clear wipes only the targeted task', () => {
    const { setStatus, clear } = useTurnStatusStore.getState();
    setStatus('p::a', 'streaming');
    setStatus('p::b', 'stalled');

    clear('p::a');
    const { byTask } = useTurnStatusStore.getState();
    expect(byTask['p::a']).toBeUndefined();
    expect(byTask['p::b'].status).toBe('stalled');
  });

  it('clear is safe on unknown tasks', () => {
    const { clear } = useTurnStatusStore.getState();
    const before = useTurnStatusStore.getState().byTask;
    clear('nonexistent');
    expect(useTurnStatusStore.getState().byTask).toBe(before);
  });
});

describe('taskKeyOf', () => {
  it('joins projectId and taskId with ::', () => {
    expect(taskKeyOf('proj-1', 'task-abc')).toBe('proj-1::task-abc');
  });
});
