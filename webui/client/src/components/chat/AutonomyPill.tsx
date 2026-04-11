import type { AutonomyOption } from '../../types/settings';

interface AutonomyPillProps {
  autonomy: AutonomyOption;
}

export function AutonomyPill({ autonomy }: AutonomyPillProps) {
  const isGuided = autonomy === 'guided';

  return (
    <span
      className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-gray-100 text-xs font-medium text-gray-500"
      title={isGuided ? 'Guided: asks before acting (per-project setting)' : 'Autonomous: acts independently (per-project setting)'}
    >
      <span className={`w-2 h-2 rounded-full ${isGuided ? 'bg-green-500' : 'bg-amber-500'}`} />
      {isGuided ? 'Guided' : 'Auto'}
    </span>
  );
}
