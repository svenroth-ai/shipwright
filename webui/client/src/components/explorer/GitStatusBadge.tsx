const STATUS_MAP: Record<string, { label: string; color: string }> = {
  M: { label: 'M', color: 'text-amber-500' },
  A: { label: 'A', color: 'text-green-500' },
  D: { label: 'D', color: 'text-red-500' },
  '?': { label: '?', color: 'text-gray-400' },
};

interface GitStatusBadgeProps {
  status?: string;
}

export function GitStatusBadge({ status }: GitStatusBadgeProps) {
  if (!status) return null;
  const config = STATUS_MAP[status];
  if (!config) return null;

  return (
    <span className={`text-[10px] font-bold ${config.color}`} title={`Git: ${config.label}`}>
      {config.label}
    </span>
  );
}
