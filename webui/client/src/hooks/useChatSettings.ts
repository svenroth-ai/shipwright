import { useLocalStorage } from './useLocalStorage';

export type ModelOption = 'opus' | 'sonnet' | 'haiku';
export type ModeOption = 'default' | 'plan' | 'auto-accept';
export type EffortOption = 'low' | 'medium' | 'high';

export interface ChatSettings {
  model: ModelOption;
  mode: ModeOption;
  effort: EffortOption;
}

export function useChatSettings() {
  const [model, setModel] = useLocalStorage<ModelOption>('chat-model', 'sonnet');
  const [mode, setMode] = useLocalStorage<ModeOption>('chat-mode', 'default');
  const [effort, setEffort] = useLocalStorage<EffortOption>('chat-effort', 'medium');

  return { model, setModel, mode, setMode, effort, setEffort };
}
