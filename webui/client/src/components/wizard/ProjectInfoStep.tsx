interface ProjectInfoStepProps {
  name: string;
  path: string;
  onNameChange: (name: string) => void;
  onPathChange: (path: string) => void;
}

export function ProjectInfoStep({ name, path, onNameChange, onPathChange }: ProjectInfoStepProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Project Name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder="My Awesome App"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Project Directory</label>
        <input
          type="text"
          value={path}
          onChange={(e) => onPathChange(e.target.value)}
          placeholder="/home/user/projects/my-app"
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
        />
        <p className="text-xs text-gray-400 mt-1">Directory must exist. Existing project files are fine.</p>
      </div>
    </div>
  );
}
