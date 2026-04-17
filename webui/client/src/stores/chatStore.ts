import { create } from 'zustand';

/**
 * Iterate 14.6 — captures the per-task `system/init` metadata reported by
 * the Claude CLI. Today we only track the running model id so the chat
 * toolbar can show "Opus 4.5" instead of a hardcoded label. Extend this
 * slice if future iterates need more init fields (session id, tools, etc).
 *
 * Iterate 14.14 — semantics switched from first-write-wins to
 * "last-write-wins when the model changes". Identical writes are
 * idempotent no-ops (preserves 14.6's duplicate-SSE guard); a different
 * model id overwrites (respawn after 14.12 mid-task model switch).
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
      // Iterate 14.14 — last-write-wins *when the model changes*. Identical
      // writes are short-circuited to preserve idempotency for duplicate
      // SSE events (14.6's original intent). A mid-task model switch
      // (14.12) respawns Claude and emits a new system/init with a
      // different model id — that case must overwrite so ModelSelector
      // and the chat "Session started · {model}" line stay in sync.
      const current = state.systemInitByTask[taskKey];
      const nextModel = info.model;
      if (current?.model && nextModel && current.model === nextModel) {
        return state;
      }
      return {
        systemInitByTask: {
          ...state.systemInitByTask,
          [taskKey]: { ...current, ...info },
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
