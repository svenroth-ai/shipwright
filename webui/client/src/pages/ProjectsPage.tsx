/*
 * Projects — list all projects registered in the WebUI.
 *
 * Iterate 3 remediation v2 Phase 1 Surface 5 (2026-04-21) — layout
 * alignment pass. Per plan §"S5 — Projects page" + decision #4:
 *   - Wrap page body in `.page-container` (1280 max-width, centered,
 *     24px horizontal padding — utility defined in index.css Phase 0).
 *   - Match Inbox header style: full-bleed surface bar with bottom
 *     border, 20px/32px padding, 24px/700 title + inline muted count.
 *   - Single-column vertical list of cards (per mockup 14-projects.html)
 *     with 12px gap — cards grow to full container width.
 *   - Migrate all `gray-*` tailwind classes to warm-beige CSS tokens
 *     (constraint: no `gray-*`/`neutral-*` in touched files).
 *   - Content unchanged: same cards, same actions, same testids — this
 *     is a layout-only pass.
 *
 * Load-bearing testids (preserved):
 *   aria-label="Project settings" (gear button) — ProjectsPage.test.tsx.
 */
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
    <div
      className="flex h-full flex-col"
      style={{ background: 'var(--color-bg)' }}
      data-testid="projects-page"
    >
      {/* Header — matches Inbox: full-bleed surface bar, bottom border,
          24px/700 title + inline muted count, right-aligned primary CTA.
          R1/R2 (iterate 3.7e-a Foundation, 2026-04-22): header content is
          wrapped inside `.page-container` so the title aligns with the
          cards in the body column (same 24 px L/R padding, same 1280 px
          max-width). The full-bleed surface strip stays outside the
          container — only the inner row uses the container. */}
      <div
        style={{
          background: 'var(--color-surface)',
          borderBottom: '1px solid var(--color-border)',
        }}
      >
        <header
          className="page-container flex items-center justify-between"
          style={{ paddingTop: '20px', paddingBottom: '20px' }}
        >
          <div className="flex items-baseline gap-[10px]">
            <h1
              className="font-bold"
              style={{
                fontSize: '24px',
                color: 'var(--color-text)',
                letterSpacing: '-0.01em',
              }}
            >
              Projects
            </h1>
            {projects.length > 0 && (
              <span
                className="font-medium"
                style={{
                  fontSize: '14px',
                  color: 'var(--color-muted)',
                }}
                data-testid="projects-header-count"
              >
                ({projects.length} total)
              </span>
            )}
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--color-primary-hover)]"
            style={{ background: 'var(--color-primary)' }}
            onClick={() => setShowWizard(true)}
            data-testid="projects-create-button"
          >
            <Plus size={16} /> Create Project
          </button>
        </header>
      </div>

      {/* Body — scrollable, content centered to .page-container (1280).
          Same 24 px L/R padding via `.page-container` → header title and
          body cards share a pixel-perfect left edge (R1). */}
      <div className="flex-1 overflow-y-auto">
        <div
          className="page-container"
          style={{ paddingTop: '24px', paddingBottom: '24px' }}
        >
          {isLoading ? (
            <div className="flex flex-col" style={{ gap: '12px' }}>
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="animate-pulse"
                  style={{
                    height: '120px',
                    background: 'var(--color-muted-bg)',
                    borderRadius: 'var(--radius-card)',
                  }}
                />
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div
              className="flex flex-col items-center text-center"
              style={{
                padding: '64px 16px',
                color: 'var(--color-muted)',
              }}
              data-testid="projects-empty"
            >
              <FolderOpen size={48} className="mb-3 opacity-50" />
              <p className="text-lg" style={{ color: 'var(--color-text)' }}>
                No projects yet
              </p>
              <p className="text-sm mb-4">
                Create your first project to get started
              </p>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-[var(--color-primary-hover)]"
                style={{ background: 'var(--color-primary)' }}
                onClick={() => setShowWizard(true)}
              >
                <Plus size={16} /> Create Project
              </button>
            </div>
          ) : (
            <div className="flex flex-col" style={{ gap: '12px' }}>
              {projects.map((project) => {
                const statusColor =
                  project.status === 'active'
                    ? 'var(--color-success)'
                    : project.status === 'error'
                      ? 'var(--color-error)'
                      : 'var(--color-muted)';
                return (
                  <div
                    key={project.id}
                    className="cursor-pointer transition-shadow"
                    style={{
                      background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-card)',
                      padding: '18px 22px',
                      boxShadow: 'var(--shadow-sm)',
                      display: 'flex',
                      flexDirection: 'column',
                    }}
                    onClick={() => navigate(`/?project=${project.id}`)}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.boxShadow = 'var(--shadow-card-hover)';
                      e.currentTarget.style.borderColor = 'var(--color-accent)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
                      e.currentTarget.style.borderColor = 'var(--color-border)';
                    }}
                    data-testid={`project-card-${project.id}`}
                  >
                    {/* Top: name + status + profile pill */}
                    <div className="flex items-start justify-between gap-2" style={{ marginBottom: '6px' }}>
                      <div className="flex items-center gap-2 min-w-0">
                        <div
                          className="shrink-0"
                          style={{
                            width: '10px',
                            height: '10px',
                            borderRadius: '9999px',
                            background: statusColor,
                          }}
                          aria-hidden="true"
                        />
                        <h3
                          className="font-semibold truncate"
                          style={{ fontSize: '15px', color: 'var(--color-text)' }}
                        >
                          {project.name}
                        </h3>
                      </div>
                      <span
                        className="inline-flex items-center uppercase"
                        style={{
                          padding: '3px 10px',
                          borderRadius: '20px',
                          fontSize: '11px',
                          fontWeight: 600,
                          background: 'var(--color-muted-bg)',
                          color: 'var(--color-accent)',
                          letterSpacing: '0.02em',
                        }}
                      >
                        {project.profile}
                      </span>
                    </div>

                    {/* Path */}
                    <p
                      className="font-mono truncate"
                      style={{
                        fontSize: '12px',
                        color: 'var(--color-muted)',
                        marginBottom: '14px',
                      }}
                    >
                      {project.path}
                    </p>

                    {/* Bottom: last active + actions */}
                    <div
                      className="flex items-center justify-between"
                      style={{
                        paddingTop: '12px',
                        borderTop: '1px solid var(--color-border)',
                      }}
                    >
                      <span
                        style={{ fontSize: '12px', color: 'var(--color-muted)' }}
                      >
                        Last active {formatRelativeTime(project.lastActive)}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          className="inline-flex items-center gap-1 rounded-[var(--radius-button)] transition-colors"
                          style={{
                            padding: '6px 12px',
                            fontSize: '12px',
                            fontWeight: 500,
                            color: 'var(--color-primary)',
                            background: 'transparent',
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/?project=${project.id}`);
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'var(--color-muted-bg)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'transparent';
                          }}
                        >
                          <ExternalLink size={12} /> Open Board
                        </button>
                        <button
                          type="button"
                          className="rounded-[var(--radius-button)] transition-colors"
                          style={{
                            padding: '6px',
                            color: 'var(--color-muted)',
                            background: 'transparent',
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/settings?projectId=${project.id}&tab=project`);
                          }}
                          aria-label="Project settings"
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'var(--color-muted-bg)';
                            e.currentTarget.style.color = 'var(--color-text)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.color = 'var(--color-muted)';
                          }}
                        >
                          <SettingsIcon size={14} />
                        </button>
                        <button
                          type="button"
                          className="rounded-[var(--radius-button)] transition-colors"
                          style={{
                            padding: '6px',
                            color: 'var(--color-muted)',
                            background: 'transparent',
                          }}
                          onClick={(e) => handleDelete(e, project.id, project.name)}
                          aria-label="Remove project"
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = 'var(--color-error-bg)';
                            e.currentTarget.style.color = 'var(--color-error)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = 'transparent';
                            e.currentTarget.style.color = 'var(--color-muted)';
                          }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      <ProjectWizard open={showWizard} onOpenChange={setShowWizard} />
    </div>
  );
}
