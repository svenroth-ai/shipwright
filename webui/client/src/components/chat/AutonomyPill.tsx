import type { AutonomyOption } from '../../hooks/useChatSettings';

interface AutonomyPillProps {
  autonomy: AutonomyOption;
  onChange: (autonomy: AutonomyOption) => void;
}

export function AutonomyPill({ autonomy, onChange }: AutonomyPillProps) {
  const isGuided = autonomy === 'guided';

  return (
    <button
      className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-gray-100 text-xs font-medium hover:bg-gray-200 cursor-pointer"
      onClick={() => onChange(isGuided ? 'autonomous' : 'guided')}
      title={isGuided ? 'Guided: asks before acting' : 'Autonomous: acts independently'}
    >
      <span className={`w-2 h-2 rounded-full ${isGuided ? 'bg-green-500' : 'bg-amber-500'}`} />
      {isGuided ? 'Guided' : 'Auto'}
    </button>
  );
}
