import type { ProjectMode } from '../../types/project';

/**
 * Iterate 14.7.1 — project mode badge.
 *
 * Rendered diagonally in the top-right of modals that need to surface which
 * mode (pipeline / iterate / standalone) the parent project is operating in.
 * Positioned absolutely, so the parent container must have
 * `position: relative` (modal content wrappers already do). Color-coded by
 * mode for quick visual anchoring.
 *
 * Note: the component lives in `components/common/` (not a conventional
 * `ui/` folder — the webui uses `common/` for its own shared primitives).
 */

const MODE_STYLES: Record<ProjectMode, { label: string; bg: string; text: string }> = {
  pipeline: { label: 'Pipeline', bg: 'bg-blue-100', text: 'text-blue-900' },
  iterate: { label: 'Iterate', bg: 'bg-amber-100', text: 'text-amber-900' },
  standalone: { label: 'Standalone', bg: 'bg-gray-100', text: 'text-gray-700' },
};

export interface ModeBadgeProps {
  mode: ProjectMode | undefined;
}

export function ModeBadge({ mode }: ModeBadgeProps) {
  if (!mode) return null;
  const style = MODE_STYLES[mode];
  if (!style) return null;
  return (
    <span
      data-testid={`mode-badge-${mode}`}
      className={`absolute top-4 right-12 px-2 py-0.5 text-[10px] font-semibold rounded shadow-sm ${style.bg} ${style.text} transform rotate-[12deg] select-none pointer-events-none`}
      aria-label={`Mode: ${style.label}`}
    >
      {style.label}
    </span>
  );
}
