const PRIORITY_MAP: Record<string, { dotColor: string; label: string }> = {
  P1: { dotColor: 'bg-red-500', label: 'P1' },
  P2: { dotColor: 'bg-amber-500', label: 'P2' },
  P3: { dotColor: 'bg-gray-400', label: 'P3' },
};

interface PriorityIndicatorProps {
  priority?: string;
}

export function PriorityIndicator({ priority }: PriorityIndicatorProps) {
  if (!priority) return null;

  const config = PRIORITY_MAP[priority];
  if (!config) return null;

  return (
    <span className="flex items-center gap-1 text-xs text-gray-500">
      <span className={`w-2 h-2 rounded-full ${config.dotColor}`} />
      {config.label}
    </span>
  );
}
