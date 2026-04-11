import type { Task } from '../../types';
import { IntentBadge } from './IntentBadge';
import { ComplexityIndicator } from './ComplexityIndicator';

interface CardEnrichmentProps {
  task: Task;
}

export function CardEnrichment({ task }: CardEnrichmentProps) {
  const isRecent = Date.now() - new Date(task.createdAt).getTime() < 30_000;
  const isPending = !task.intent && isRecent;

  return (
    <div className="flex items-center gap-1.5">
      {isPending ? (
        <span className="text-[10px] text-gray-400 animate-pulse">Classifying...</span>
      ) : (
        <>
          <span className="transition-opacity duration-300">
            <IntentBadge intent={task.intent} />
          </span>
          <span className="transition-opacity duration-300">
            <ComplexityIndicator complexity={task.complexity} />
          </span>
        </>
      )}
    </div>
  );
}
