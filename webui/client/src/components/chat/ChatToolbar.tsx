import { ModelSelector } from './ModelSelector';
import { PermissionMode } from './PermissionMode';
import { EffortPill } from './EffortPill';
import { AutonomyPill } from './AutonomyPill';
import type { ModelOption, ModeOption, EffortOption } from '../../hooks/useChatSettings';
import type { AutonomyOption } from '../../types/settings';

interface ChatToolbarProps {
  model: ModelOption;
  setModel: (m: ModelOption) => void;
  mode: ModeOption;
  setMode: (m: ModeOption) => void;
  effort: EffortOption;
  setEffort: (e: EffortOption) => void;
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
  effort,
  setEffort,
  autonomy,
  projectId,
  taskId,
}: ChatToolbarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector model={model} onChange={setModel} />
      <PermissionMode mode={mode} onChange={setMode} projectId={projectId} taskId={taskId} />
      <EffortPill effort={effort} onChange={setEffort} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
