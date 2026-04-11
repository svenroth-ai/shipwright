const INTENT_STYLES: Record<string, string> = {
  fix: 'bg-red-100 text-red-700',
  feat: 'bg-green-100 text-green-700',
  chg: 'bg-blue-100 text-blue-700',
};

interface IntentBadgeProps {
  intent?: string;
}

export function IntentBadge({ intent }: IntentBadgeProps) {
  if (!intent) return null;

  const style = INTENT_STYLES[intent] ?? 'bg-gray-100 text-gray-600';

  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[8px] font-bold uppercase ${style}`}>
      {intent}
    </span>
  );
}
