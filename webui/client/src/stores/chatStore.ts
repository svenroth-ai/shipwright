import { create } from 'zustand';

/**
 * Iterate 14.6 — captures the per-task `system/init` metadata reported by
 * the Claude CLI. Today we only track the running model id so the chat
 * toolbar can show "Opus 4.5" instead of a hardcoded label. Extend this
 * slice if future iterates need more init fields (session id, tools, etc).
 *
 * taskKey format matches `turnStatusStore`: `${projectId}::${taskId}`.
 */

export interface SystemInitInfo {
  /** Raw model id from CLI, e.g. `claude-opus-4-5-20251101`. */
  model?: string;
}

interface ChatStore {
  systemInitByTask: Record<string, SystemInitInfo>;
  setSystemInit: (taskKey: string, info: SystemInitInfo) => void;
  clearSystemInit: (taskKey: string) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  systemInitByTask: {},

  setSystemInit: (taskKey, info) =>
    set((state) => {
      // First capture wins — mirrors "first system/init SSE event" semantics.
      if (state.systemInitByTask[taskKey]?.model) return state;
      return {
        systemInitByTask: {
          ...state.systemInitByTask,
          [taskKey]: { ...state.systemInitByTask[taskKey], ...info },
        },
      };
    }),

  clearSystemInit: (taskKey) =>
    set((state) => {
      if (!state.systemInitByTask[taskKey]) return state;
      const next = { ...state.systemInitByTask };
      delete next[taskKey];
      return { systemInitByTask: next };
    }),
}));

/**
 * Selector helper for components that only need the model label of a
 * specific task. Returns `undefined` until the first `system` message with
 * a model arrives, so callers can show a fallback.
 */
export function useSystemInitModel(taskKey: string): string | undefined {
  return useChatStore((s) => s.systemInitByTask[taskKey]?.model);
}
