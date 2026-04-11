import * as Select from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';
import type { Project } from '../../types';

interface ProjectTabsProps {
  projects: Project[];
  activeProjectId: string | null;
  onSelect: (projectId: string | null) => void;
}

export function ProjectTabs({ projects, activeProjectId, onSelect }: ProjectTabsProps) {
  const activeProject = projects.find((p) => p.id === activeProjectId);
  const displayLabel = activeProject ? activeProject.name : 'All Projects';

  return (
    <Select.Root
      value={activeProjectId ?? '__all__'}
      onValueChange={(val) => onSelect(val === '__all__' ? null : val)}
    >
      <Select.Trigger
        className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-900 bg-white border border-[#e0dbd4] rounded-lg hover:border-gray-400 transition-colors min-w-[180px]"
        aria-label="Select project"
      >
        <Select.Value>{displayLabel}</Select.Value>
        <Select.Icon>
          <ChevronDown size={14} className="text-gray-400" />
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] p-1 min-w-[200px] z-50"
          position="popper"
          sideOffset={4}
        >
          <Select.Viewport>
            <Select.Item
              value="__all__"
              className="flex items-center px-3 py-2 text-sm rounded cursor-pointer hover:bg-gray-50 data-[highlighted]:bg-gray-50 outline-none"
            >
              <Select.ItemText>All Projects</Select.ItemText>
            </Select.Item>
            {projects.map((project) => (
              <Select.Item
                key={project.id}
                value={project.id}
                className="flex items-center px-3 py-2 text-sm rounded cursor-pointer hover:bg-gray-50 data-[highlighted]:bg-gray-50 outline-none"
              >
                <Select.ItemText>{project.name}</Select.ItemText>
              </Select.Item>
            ))}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
