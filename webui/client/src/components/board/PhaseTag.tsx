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

// Iterate 14.7.2 — when the Kanban board is in "All Projects" mode,
// each card already carries a colored project strip on its left edge.
// Rendering phase badges in their normal hues on top of that produces
// a noisy, color-overloaded card. The monochrome variant neutralises
// the phase tag so the project strip stays the dominant color signal.
const MONOCHROME_COLOR = { bg: 'bg-gray-100', text: 'text-gray-700' };

interface PhaseTagProps {
  phase?: string;
  monochrome?: boolean;
}

export function PhaseTag({ phase, monochrome = false }: PhaseTagProps) {
  if (!phase) return null;

  const { bg, text } = monochrome
    ? MONOCHROME_COLOR
    : (PHASE_COLORS[phase] ?? DEFAULT_COLOR);

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${bg} ${text}`}
    >
      {phase}
    </span>
  );
}
