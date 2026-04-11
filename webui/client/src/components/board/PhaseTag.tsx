const PHASE_COLORS: Record<string, string> = {
  project: 'bg-gray-400',
  design: 'bg-purple-500',
  plan: 'bg-blue-500',
  build: 'bg-orange-500',
  test: 'bg-green-500',
  deploy: 'bg-teal-500',
};

interface PhaseTagProps {
  phase?: string;
}

export function PhaseTag({ phase }: PhaseTagProps) {
  if (!phase) return null;

  const colorClass = PHASE_COLORS[phase] ?? 'bg-gray-400';

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium text-white ${colorClass}`}
    >
      {phase}
    </span>
  );
}
