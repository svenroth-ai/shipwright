import { Sparkles } from 'lucide-react';

const INTENT_LABELS: Record<string, string> = {
  fix: 'Bug fix detected',
  feat: 'New feature detected',
  chg: 'Change request detected',
  refactor: 'Refactoring detected',
  docs: 'Documentation task detected',
};

interface IntentHintProps {
  intent: string;
  confidence: number;
}

export function IntentHint({ intent, confidence }: IntentHintProps) {
  const label = INTENT_LABELS[intent] ?? `Intent: ${intent}`;
  const pct = Math.round(confidence * 100);

  return (
    <div className="flex items-center gap-1.5 px-3 py-1 text-xs text-[var(--color-primary)] animate-in fade-in duration-300">
      <Sparkles size={12} />
      <span>{label}</span>
      <span className="text-gray-400">({pct}%)</span>
    </div>
  );
}
