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
}

export function ChatToolbar({ model, setModel, mode, setMode, effort, setEffort, autonomy }: ChatToolbarProps) {
  return (
    <div className="flex items-center gap-2 px-3 py-2">
      <ModelSelector model={model} onChange={setModel} />
      <PermissionMode mode={mode} onChange={setMode} />
      <EffortPill effort={effort} onChange={setEffort} />
      <AutonomyPill autonomy={autonomy} />
    </div>
  );
}
