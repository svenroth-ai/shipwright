import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FolderOpen } from 'lucide-react';
import { useProjects } from '../hooks/useProjects';
import { ProjectWizard } from '../components/wizard/ProjectWizard';
import { formatRelativeTime } from '../lib/formatTime';

export default function ProjectsPage() {
  const { data: projects = [], isLoading } = useProjects();
  const [showWizard, setShowWizard] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
        <button
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90"
          onClick={() => setShowWizard(true)}
        >
          <Plus size={16} /> New Project
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <FolderOpen size={48} className="mx-auto mb-3 opacity-50" />
          <p className="text-lg">No projects yet</p>
          <p className="text-sm">Create your first project to get started</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="flex items-center gap-4 p-4 bg-white rounded-xl border border-gray-200 hover:shadow-sm cursor-pointer transition-shadow"
              onClick={() => navigate(`/?project=${project.id}`)}
            >
              <div className={`w-3 h-3 rounded-full ${project.status === 'active' ? 'bg-green-500' : project.status === 'error' ? 'bg-red-500' : 'bg-gray-400'}`} />
              <div className="flex-1">
                <div className="text-sm font-semibold text-gray-900">{project.name}</div>
                <div className="text-xs text-gray-500 font-mono">{project.path}</div>
              </div>
              <div className="text-xs text-gray-400">
                {formatRelativeTime(project.lastActive)}
              </div>
              <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 text-gray-600">
                {project.profile}
              </span>
            </div>
          ))}
        </div>
      )}

      <ProjectWizard open={showWizard} onOpenChange={setShowWizard} />
    </div>
  );
}
