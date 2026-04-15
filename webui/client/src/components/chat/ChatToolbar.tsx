import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
import { formatModelLabel } from '../../lib/formatModelLabel';
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
  // Iterate 14.6 — dynamic model label sourced from the CLI `system/init`
  // event for this task. Falls back to "Claude" until the first system
  // message arrives.
  const taskKey = projectId && taskId ? taskKeyOf(projectId, taskId) : '';
  const systemModel = useSystemInitModel(taskKey);
  const runningLabel = formatModelLabel(systemModel);

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector model={model} onChange={setModel} />
      <span
        className="text-[10px] text-gray-400 font-medium"
        data-testid="running-model-label"
        title={systemModel ? `Running: ${systemModel}` : 'Running model unknown (system/init not yet received)'}
      >
        {runningLabel}
      </span>
      <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
