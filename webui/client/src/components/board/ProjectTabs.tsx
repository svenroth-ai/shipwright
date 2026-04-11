import type { Project } from '../../types';

interface ProjectTabsProps {
  projects: Project[];
  activeProjectId: string | null;
  onSelect: (projectId: string | null) => void;
}

export function ProjectTabs({ projects, activeProjectId, onSelect }: ProjectTabsProps) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto" role="tablist">
      <TabButton
        label="All"
        isActive={activeProjectId === null}
        onClick={() => onSelect(null)}
      />
      {projects.map((project) => (
        <TabButton
          key={project.id}
          label={project.name}
          isActive={activeProjectId === project.id}
          onClick={() => onSelect(project.id)}
        />
      ))}
    </div>
  );
}

function TabButton({
  label,
  isActive,
  onClick,
}: {
  label: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      role="tab"
      aria-selected={isActive}
      className={`px-4 py-2 text-sm font-medium whitespace-nowrap cursor-pointer border-b-2 transition-colors ${
        isActive
          ? 'border-[var(--color-primary)] text-[var(--color-primary)]'
          : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
