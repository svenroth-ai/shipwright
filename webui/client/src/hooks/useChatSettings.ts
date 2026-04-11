import { useLocalStorage } from './useLocalStorage';

export type ModelOption = 'opus' | 'sonnet' | 'haiku';
export type ModeOption = 'auto' | 'ask' | 'edit' | 'plan' | 'bypass';
export type EffortOption = 'low' | 'medium' | 'high';
export type AutonomyOption = 'guided' | 'autonomous';

export interface ChatSettings {
  model: ModelOption;
  mode: ModeOption;
  effort: EffortOption;
  autonomy: AutonomyOption;
}

export function useChatSettings() {
  const [model, setModel] = useLocalStorage<ModelOption>('chat-model', 'sonnet');
  const [mode, setMode] = useLocalStorage<ModeOption>('chat-mode', 'auto');
  const [effort, setEffort] = useLocalStorage<EffortOption>('chat-effort', 'medium');
  const [autonomy, setAutonomy] = useLocalStorage<AutonomyOption>('chat-autonomy', 'guided');

  return { model, setModel, mode, setMode, effort, setEffort, autonomy, setAutonomy };
}
