import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
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

  // onSwitchModel: integration point for future mid-task model switching.
  // The /mode endpoint currently only supports permission-mode changes.
  // When the CLI adds --model on --resume, this will fire a model-switch
  // mutation. For now, model selection is informational (display-only).
  const handleSwitchModel = (_modelId: string) => {
    // Future: POST /api/projects/:id/tasks/:taskId/model { model: alias }
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
