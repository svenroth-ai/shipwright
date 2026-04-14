import { create } from 'zustand';

/**
 * Iterate 13 / Step 3: per-task turn status that must survive ChatPanel
 * unmount (solves the task-switch amnesia bug from review round 2).
 *
 * This store is INTENTIONALLY minimal. Committed chat messages live in the
 * TanStack Query cache keyed by queryKeys.chat.byTask(pid, tid) — NOT here.
 * This store only holds the per-task turn lifecycle state (status,
 * lastEventAt, watchdogStale) that the UI uses to decide when to show the
 * "thinking" / "stalled" indicator.
 *
 * taskKey format: `${projectId}::${taskId}` — matches chat-store server convention.
 */

export type TurnStatus =
  | 'idle'
  | 'awaiting_model' // user sent, no events yet
  | 'streaming' // events arriving
  | 'awaiting_user' // AskUserQuestion shown, waiting for inbox answer
  | 'stalled'; // watchdog fired or terminal race lost

export interface TurnAssembly {
  status: TurnStatus;
  lastEventAt: number;
  watchdogStale: boolean;
}

const IDLE: TurnAssembly = { status: 'idle', lastEventAt: 0, watchdogStale: false };

interface TurnStatusStore {
  byTask: Record<string, TurnAssembly>;
  ensure: (taskKey: string) => TurnAssembly;
  setStatus: (taskKey: string, status: TurnStatus) => void;
  recordEvent: (taskKey: string, at: number) => void;
  markWatchdogStale: (taskKey: string, stale: boolean) => void;
  clear: (taskKey: string) => void;
}

export const useTurnStatusStore = create<TurnStatusStore>((set, get) => ({
  byTask: {},

  ensure: (taskKey) => {
    const existing = get().byTask[taskKey];
    if (existing) return existing;
    set((state) => ({ byTask: { ...state.byTask, [taskKey]: IDLE } }));
    return IDLE;
  },

  setStatus: (taskKey, status) => {
    set((state) => {
      const prev = state.byTask[taskKey] ?? IDLE;
      if (prev.status === status) return state;
      return {
        byTask: {
          ...state.byTask,
          [taskKey]: { ...prev, status, watchdogStale: status === 'streaming' ? prev.watchdogStale : false },
        },
      };
    });
  },

  recordEvent: (taskKey, at) => {
    set((state) => {
      const prev = state.byTask[taskKey] ?? IDLE;
      return {
        byTask: {
          ...state.byTask,
          [taskKey]: { ...prev, lastEventAt: at, watchdogStale: false },
        },
      };
    });
  },

  markWatchdogStale: (taskKey, stale) => {
    set((state) => {
      const prev = state.byTask[taskKey] ?? IDLE;
      if (prev.watchdogStale === stale) return state;
      return {
        byTask: { ...state.byTask, [taskKey]: { ...prev, watchdogStale: stale } },
      };
    });
  },

  clear: (taskKey) => {
    set((state) => {
      if (!(taskKey in state.byTask)) return state;
      const next = { ...state.byTask };
      delete next[taskKey];
      return { byTask: next };
    });
  },
}));

/** Helper to build the canonical task key used throughout the UI. */
export function taskKeyOf(projectId: string, taskId: string): string {
  return `${projectId}::${taskId}`;
}
