import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
import { useSwitchModel } from '../../hooks/useSwitchModel';
import { useChatSettings, type ModeOption } from '../../hooks/useChatSettings';
import { matchKnownModel } from './ModelSelector';
import type { AutonomyOption } from '../../types/settings';

interface ChatToolbarProps {
  mode: ModeOption;
  setMode: (m: ModeOption) => void;
  autonomy: AutonomyOption;
  projectId?: string;
  taskId?: string;
}

/**
 * Iterate 2026-04-18 modelswitch-spawn-ux — timeout after which a pending
 * model switch is cleared from the UI with a timeout error. The CLI
 * respawn normally completes in 1-2s; 15s is generous enough to tolerate
 * cold-start churn but short enough to avoid a permanently-pending state
 * when the server silently loses the respawn.
 */
const PENDING_SWITCH_TIMEOUT_MS = 15_000;

function normalizeModelId(id: string | undefined): string | undefined {
  if (!id) return undefined;
  const match = matchKnownModel(id);
  return match?.id ?? id;
}

export function ChatToolbar({
  mode,
  setMode,
  autonomy,
  projectId,
  taskId,
}: ChatToolbarProps) {
  const taskKey = projectId && taskId ? taskKeyOf(projectId, taskId) : '';
  const systemModel = useSystemInitModel(taskKey);
  const { setModel } = useChatSettings();

  const switchModel = useSwitchModel(projectId ?? '', taskId ?? '');

  // Sub-iterate 2026-04-18 — pending-target state machine.
  //
  // isSwitching (= useSwitchModel.isPending) only tracks the 200ms HTTP
  // mutation. The CLI respawn + new system/init takes 1-2s on top. While
  // the mutation resolved but system/init hasn't arrived yet, the old
  // label was stuck with no feedback. pendingTargetModel bridges that gap
  // by rendering the chosen target's label + spinner until one of:
  //   (a) systemInitModel matches the target → success, clear
  //   (b) switchModel.mutate onError → error, clear + show error
  //   (c) PENDING_SWITCH_TIMEOUT_MS elapses → timeout, clear + show error
  const [pendingTarget, setPendingTarget] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clearTimer(): void {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }

  // When systemInitModel catches up to the pending target, the switch is
  // complete — clear pending. Compare after normalization to absorb CLI
  // date suffixes (e.g. `claude-opus-4-7-20260101`).
  useEffect(() => {
    if (!pendingTarget) return;
    const normalized = normalizeModelId(systemModel);
    if (normalized && normalized === pendingTarget) {
      setPendingTarget(undefined);
      clearTimer();
    }
  }, [systemModel, pendingTarget]);

  useEffect(() => clearTimer, []);

  const handleSwitchModel = (modelId: string) => {
    setError(null);
    if (!projectId || !taskId) return;
    setPendingTarget(modelId);
    clearTimer();
    timeoutRef.current = setTimeout(() => {
      timeoutRef.current = null;
      setPendingTarget((prev) => {
        if (prev === modelId) {
          setError('Model switch timed out. Try again or restart the task.');
          return undefined;
        }
        return prev;
      });
    }, PENDING_SWITCH_TIMEOUT_MS);
    // Persist the pick so future fresh tasks pick up the concrete id.
    setModel(modelId);
    switchModel.mutate(modelId, {
      onSuccess: () => {
        // Do NOT clear pendingTarget here — we wait for the new
        // system/init to arrive via SSE. The effect above handles that.
      },
      onError: (err) => {
        clearTimer();
        setPendingTarget(undefined);
        const msg = err instanceof Error ? err.message : 'Model switch failed';
        setError(msg);
      },
    });
  };

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 px-3 py-2">
        <ModelSelector
          systemInitModel={systemModel}
          onSwitchModel={handleSwitchModel}
          isSwitching={switchModel.isPending}
          pendingTargetModel={pendingTarget}
        />
        <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
        <AutonomyPill autonomy={autonomy} />
      </div>
      {error && (
        <div
          className="mx-3 mb-1 flex items-start gap-2 px-2.5 py-1.5 text-[11px] text-red-700 bg-red-50 border border-red-200 rounded-md"
          data-testid="model-switch-error"
          role="status"
        >
          <AlertTriangle size={12} className="shrink-0 mt-0.5" />
          <span className="flex-1">{error}</span>
          <button
            className="shrink-0 text-red-500 hover:text-red-700"
            onClick={() => setError(null)}
            aria-label="Dismiss"
          >
            <X size={12} />
          </button>
        </div>
      )}
    </div>
  );
}
