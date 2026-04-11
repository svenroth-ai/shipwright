import { Circle, CircleDot, CircleDashed, CheckCircle2, XCircle, MinusCircle } from 'lucide-react';
import type { KanbanStatus } from '../../types';

const STATUS_CONFIG: Record<KanbanStatus, { icon: typeof Circle; color: string; label: string }> = {
  backlog: { icon: Circle, color: 'text-gray-400', label: 'Backlog' },
  in_progress: { icon: CircleDot, color: 'text-blue-500', label: 'In Progress' },
  in_review: { icon: CircleDashed, color: 'text-amber-500', label: 'In Review' },
  done: { icon: CheckCircle2, color: 'text-green-500', label: 'Done' },
  failed: { icon: XCircle, color: 'text-red-500', label: 'Failed' },
  cancelled: { icon: MinusCircle, color: 'text-gray-400', label: 'Cancelled' },
};

interface StatusIconProps {
  status: KanbanStatus;
}

export function StatusIcon({ status }: StatusIconProps) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.backlog;
  const Icon = config.icon;

  return <Icon size={16} className={config.color} aria-label={config.label} />;
}
