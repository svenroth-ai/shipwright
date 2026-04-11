const PHASE_COLORS: Record<string, { bg: string; text: string }> = {
  project: { bg: 'bg-gray-100', text: 'text-gray-600' },
  design: { bg: 'bg-purple-100', text: 'text-purple-700' },
  plan: { bg: 'bg-blue-100', text: 'text-blue-700' },
  build: { bg: 'bg-orange-50', text: 'text-orange-700' },
  test: { bg: 'bg-green-100', text: 'text-green-700' },
  deploy: { bg: 'bg-cyan-100', text: 'text-cyan-700' },
  iterate: { bg: 'bg-teal-100', text: 'text-teal-700' },
};

const DEFAULT_COLOR = { bg: 'bg-gray-100', text: 'text-gray-600' };

interface PhaseTagProps {
  phase?: string;
}

export function PhaseTag({ phase }: PhaseTagProps) {
  if (!phase) return null;

  const { bg, text } = PHASE_COLORS[phase] ?? DEFAULT_COLOR;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${bg} ${text}`}
    >
      {phase}
    </span>
  );
}
