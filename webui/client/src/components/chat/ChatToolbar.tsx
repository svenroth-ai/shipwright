import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
import type { ModelOption, ModeOption } from '../../hooks/useChatSettings';
import type { AutonomyOption } from '../../types/settings';

interface ChatToolbarProps {
  model: ModelOption;
  setModel: (m: ModelOption) => void;
  mode: ModeOption;
  setMode: (m: ModeOption) => void;
  autonomy: AutonomyOption;
  /** Iterate 10 — optional: when set, PermissionMode fires the mid-task
   *  mode-switch mutation in addition to updating the local setting. */
  projectId?: string;
  taskId?: string;
}

export function ChatToolbar({
  model,
  setModel,
  mode,
  setMode,
  autonomy,
  projectId,
  taskId,
}: ChatToolbarProps) {
  // Iterate 14.7.1 — collapsed ChatToolbar. The separate dynamic model label
  // from 14.6 was dropped; ModelSelector itself now handles system/init sync
  // and displays the concrete CLI model. We still thread the current task
  // identity so ModelSelector can reset its manual-override flag on switch.
  const taskKey = projectId && taskId ? taskKeyOf(projectId, taskId) : '';
  const systemModel = useSystemInitModel(taskKey);

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector
        model={model}
        onChange={setModel}
        systemInitModel={systemModel}
        taskKey={taskKey}
      />
      <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
