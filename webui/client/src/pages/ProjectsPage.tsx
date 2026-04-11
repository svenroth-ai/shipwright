import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, FolderOpen, ExternalLink, Settings as SettingsIcon, Trash2 } from 'lucide-react';
import { useProjects } from '../hooks/useProjects';
import { useDeleteProject } from '../hooks/useDeleteProject';
import { ProjectWizard } from '../components/wizard/ProjectWizard';
import { formatRelativeTime } from '../lib/formatTime';

export default function ProjectsPage() {
  const { data: projects = [], isLoading } = useProjects();
  const [showWizard, setShowWizard] = useState(false);
  const deleteProject = useDeleteProject();
  const navigate = useNavigate();

  function handleDelete(e: React.MouseEvent, projectId: string, projectName: string) {
    e.stopPropagation();
    if (confirm(`Remove "${projectName}" from the WebUI?\n\nProject files on disk will NOT be deleted.`)) {
      deleteProject.mutate(projectId);
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-gray-900">Projects</h1>
          {projects.length > 0 && (
            <span className="text-sm text-gray-400">{projects.length} total</span>
          )}
        </div>
        <button
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90"
          onClick={() => setShowWizard(true)}
        >
          <Plus size={16} /> Create Project
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-40 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <FolderOpen size={48} className="mx-auto mb-3 opacity-50" />
          <p className="text-lg">No projects yet</p>
          <p className="text-sm mb-4">Create your first project to get started</p>
          <button
            className="px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90"
            onClick={() => setShowWizard(true)}
          >
            <Plus size={16} className="inline mr-1 -mt-0.5" /> Create Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects.map((project) => (
            <div
              key={project.id}
              className="bg-white rounded-xl border-0 p-5 shadow-[var(--shadow-card)] hover:shadow-[var(--shadow-card-hover)] cursor-pointer transition-shadow flex flex-col"
              onClick={() => navigate(`/?project=${project.id}`)}
            >
              {/* Top: name + status */}
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
                    project.status === 'active' ? 'bg-green-500' : project.status === 'error' ? 'bg-red-500' : 'bg-gray-400'
                  }`} />
                  <h3 className="text-sm font-semibold text-gray-900">{project.name}</h3>
                </div>
                <span className="px-2 py-0.5 text-[10px] font-semibold rounded-full bg-gray-100 text-gray-600 uppercase">
                  {project.profile}
                </span>
              </div>

              {/* Path */}
              <p className="text-xs text-gray-500 font-mono mb-3 line-clamp-1">{project.path}</p>

              {/* Spacer */}
              <div className="flex-1" />

              {/* Bottom: last active + actions */}
              <div className="flex items-center justify-between pt-3 border-t border-gray-100">
                <span className="text-[11px] text-gray-400">
                  Last active {formatRelativeTime(project.lastActive)}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-[var(--color-primary)] rounded-md hover:bg-gray-100 transition-colors"
                    onClick={(e) => { e.stopPropagation(); navigate(`/?project=${project.id}`); }}
                  >
                    <ExternalLink size={12} /> Open Board
                  </button>
                  <button
                    className="p-1.5 rounded-md hover:bg-gray-100 text-gray-400 transition-colors"
                    onClick={(e) => { e.stopPropagation(); navigate('/settings'); }}
                    aria-label="Project settings"
                  >
                    <SettingsIcon size={14} />
                  </button>
                  <button
                    className="p-1.5 rounded-md hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                    onClick={(e) => handleDelete(e, project.id, project.name)}
                    aria-label="Remove project"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <ProjectWizard open={showWizard} onOpenChange={setShowWizard} />
    </div>
  );
}
