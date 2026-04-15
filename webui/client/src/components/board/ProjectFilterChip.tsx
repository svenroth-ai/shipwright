import * as Popover from '@radix-ui/react-popover';
import { ChevronDown } from 'lucide-react';
import type { Project } from '../../types';
import { getProjectColor } from '../../lib/projectColor';

// Iterate 14.7.2 — multi-select project filter for the All Projects
// Kanban view. Empty set = show all (no filter). Each project row
// shows its matching color dot so users can cross-reference the
// colored left-edge strips on task cards.

interface ProjectFilterChipProps {
  projects: Project[];
  selectedProjectIds: Set<string>;
  onToggle: (projectId: string) => void;
  onClear: () => void;
}

export function ProjectFilterChip({
  projects,
  selectedProjectIds,
  onToggle,
  onClear,
}: ProjectFilterChipProps) {
  const count = selectedProjectIds.size;
  const label = count === 0 ? 'Projects' : `Projects (${count})`;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          data-testid="project-filter-chip"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[13px] font-medium text-gray-500 bg-[var(--color-muted-bg,#ede8e1)] hover:bg-gray-200 transition-colors"
        >
          {label}
          {count > 0 && (
            <span className="min-w-[18px] h-[18px] rounded-full bg-[var(--color-primary)] text-white text-[10px] font-bold flex items-center justify-center">
              {count}
            </span>
          )}
          <ChevronDown size={12} />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] p-2 min-w-[220px] max-h-[320px] overflow-y-auto z-50"
          sideOffset={4}
        >
          {projects.length === 0 ? (
            <div className="px-2 py-1.5 text-xs text-gray-400">No projects</div>
          ) : (
            projects.map((project) => {
              const checked = selectedProjectIds.has(project.id);
              const color = getProjectColor(project.id);
              return (
                <label
                  key={project.id}
                  className="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-gray-50 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle(project.id)}
                    className="rounded border-gray-300"
                  />
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: color.hsl }}
                    aria-hidden="true"
                    data-testid={`project-color-dot-${project.id}`}
                  />
                  <span className="truncate">{project.name}</span>
                </label>
              );
            })
          )}
          {count > 0 && (
            <button
              className="w-full text-center text-xs text-[var(--color-primary)] mt-1 pt-1 border-t border-gray-100 hover:underline"
              onClick={onClear}
            >
              Clear all
            </button>
          )}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
