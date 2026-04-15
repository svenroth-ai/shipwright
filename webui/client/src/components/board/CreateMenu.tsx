import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { Plus, ChevronDown, ListChecks, Workflow } from 'lucide-react';

export interface CreateMenuProps {
  onNewTask: () => void;
  onNewPipeline: () => void;
}

/**
 * Iterate 14.4 — split-button "New" trigger that replaces the bare
 * NewIssueButton. Single trigger surface, but reveals two creation paths:
 *
 *   - New Task     (`c`)        — adds an issue to the active project
 *   - New Pipeline (`Shift+C`)  — registers a brand-new pipeline project
 */
export function CreateMenu({ onNewTask, onNewPipeline }: CreateMenuProps) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          className="flex items-center gap-1.5 px-4 py-[7px] rounded-lg text-[13px] font-semibold text-white bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover,#5a4f48)] hover:shadow-sm transition-all cursor-pointer whitespace-nowrap"
          aria-label="Create new"
        >
          <Plus size={14} />
          <span>New</span>
          <ChevronDown size={14} />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={4}
          className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] py-1 min-w-[200px] z-50"
        >
          <DropdownMenu.Item
            className="flex items-center justify-between gap-3 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 outline-none"
            onSelect={onNewTask}
          >
            <span className="flex items-center gap-2">
              <ListChecks size={14} />
              New Task
            </span>
            <kbd className="text-[11px] text-gray-400 font-mono">C</kbd>
          </DropdownMenu.Item>
          <DropdownMenu.Item
            className="flex items-center justify-between gap-3 px-3 py-2 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 outline-none"
            onSelect={onNewPipeline}
          >
            <span className="flex items-center gap-2">
              <Workflow size={14} />
              New Pipeline…
            </span>
            <kbd className="text-[11px] text-gray-400 font-mono">⇧C</kbd>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
