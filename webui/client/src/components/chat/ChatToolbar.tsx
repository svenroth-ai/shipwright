import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
import { useSwitchModel } from '../../hooks/useSwitchModel';
import type { ModeOption } from '../../hooks/useChatSettings';
import type { AutonomyOption } from '../../types/settings';

interface ChatToolbarProps {
  mode: ModeOption;
  setMode: (m: ModeOption) => void;
  autonomy: AutonomyOption;
  /** Iterate 10 — optional: when set, PermissionMode fires the mid-task
   *  mode-switch mutation in addition to updating the local setting. */
  projectId?: string;
  taskId?: string;
}

export function ChatToolbar({
  mode,
  setMode,
  autonomy,
  projectId,
  taskId,
}: ChatToolbarProps) {
  // Iterate 14.8.3 — ModelSelector is now purely props-driven from
  // chatStore.systemInit. No more model/setModel localStorage threading.
  // The label updates when the new system/init SSE event arrives.
  const taskKey = projectId && taskId ? taskKeyOf(projectId, taskId) : '';
  const systemModel = useSystemInitModel(taskKey);

  // Iterate 14.12 — mid-task model switching (Bug 1).
  // 14.8.3 left this as a no-op TODO; the user reported that clicking
  // Opus 4.7 in the dropdown did nothing. The hook is always called
  // (rules of hooks); we short-circuit to a no-op when project/task ids
  // aren't available (e.g. ChatToolbar rendered without an active task).
  const switchModel = useSwitchModel(projectId ?? '', taskId ?? '');
  const handleSwitchModel = (modelId: string) => {
    if (!projectId || !taskId) return;
    switchModel.mutate(modelId);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector
        systemInitModel={systemModel}
        onSwitchModel={handleSwitchModel}
      />
      <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
