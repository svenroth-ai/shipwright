import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { AutonomyPill } from './AutonomyPill';
import { useSystemInitModel } from '../../stores/chatStore';
import { taskKeyOf } from '../../stores/turnStatusStore';
import { useSwitchModel } from '../../hooks/useSwitchModel';
import { useChatSettings, type ModeOption } from '../../hooks/useChatSettings';
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
  const taskKey = projectId && taskId ? taskKeyOf(projectId, taskId) : '';
  const systemModel = useSystemInitModel(taskKey);
  const { setModel } = useChatSettings();

  const switchModel = useSwitchModel(projectId ?? '', taskId ?? '');
  const handleSwitchModel = (modelId: string) => {
    // Persist the pick so the next fresh task picks up the concrete id
    // instead of falling back to settings.defaultModel.
    setModel(modelId);
    if (!projectId || !taskId) return;
    switchModel.mutate(modelId);
  };

  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector
        systemInitModel={systemModel}
        onSwitchModel={handleSwitchModel}
        isSwitching={switchModel.isPending}
      />
      <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
