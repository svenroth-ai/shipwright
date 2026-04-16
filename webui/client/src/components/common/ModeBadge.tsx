import type { ProjectMode } from '../../types/project';

/**
 * Iterate 14.8.1 — project mode badge, rendered inline next to the modal title.
 *
 * Color-coded by mode for quick visual anchoring:
 *   pipeline  → blue
 *   iterate   → amber
 *   standalone → gray
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
      className={`inline-flex items-center px-2 py-0.5 text-[10px] font-semibold rounded ${style.bg} ${style.text} select-none pointer-events-none`}
      aria-label={`Mode: ${style.label}`}
    >
      {style.label}
    </span>
  );
}
