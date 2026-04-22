/*
 * Projects — list all projects registered in the WebUI.
 *
 * Iterate 3.7e-b3 (2026-04-22) — Table rebuild + color picker + settings
 * dialog + fix "Create creates nothing" error surfacing.
 *
 * Columns (per plan §"S3 — Projects"):
 *   Color     — 10 px circle; uses getProjectColor(id, settings.color)
 *   Name      — click → opens the Settings dialog (replaces old "card click
 *               → board" navigation; row is now a settings affordance)
 *   Path      — monospace, truncated (max 400 px); full path in title="..."
 *   Tasks     — count of tasks with task.projectId === project.id
 *               (source: useExternalTasks with all-projects scope)
 *   Actions   — gear icon (Settings dialog) + trash icon (delete w/ confirm)
 *
 * Load-bearing testids (preserved + new):
 *   projects-page, projects-create-button, projects-empty
 *   projects-header-count, projects-table, projects-row-<id>
 *   projects-cell-<id>-{color,name,path,tasks,actions}
 *   projects-settings-<id>, projects-delete-<id>
 *   aria-label="Project settings" — ProjectsPage.test.tsx (gear button)
 *
 * Bug fix (Sven UAT 2026-04-22): previous "Create Project erstellt kein
 * Project" reports were caused by the wizard swallowing the POST error —
 * a 4xx/5xx response never surfaced in the UI, so the user clicked +
 * nothing happened. Fix landed in ProjectWizard.tsx: the confirmation
 * step now renders createProject.error via an inline red banner (role=
 * alert) and keeps the dialog open on failure. Root cause: wizard only
 * closed on `onSuccess`; useCreateProject error state was unrendered.
 */
import { useMemo, useState } from 'react';
import { Plus, FolderOpen, Settings as SettingsIcon, Trash2 } from 'lucide-react';
import { useProjects } from '../hooks/useProjects';
import { useDeleteProject } from '../hooks/useDeleteProject';
import { useExternalTasks } from '../hooks/useExternalTasks';
import { ProjectWizard } from '../components/wizard/ProjectWizard';
import { ProjectSettingsDialog } from '../components/wizard/ProjectSettingsDialog';
import { getProjectColor } from '../lib/projectColor';
import type { Project } from '../types';

export default function ProjectsPage() {
  const { data: projects = [], isLoading } = useProjects();
  const { data: tasks = [] } = useExternalTasks({ projectId: null });
  const [showWizard, setShowWizard] = useState(false);
  const [settingsFor, setSettingsFor] = useState<Project | null>(null);
  const deleteProject = useDeleteProject();

  // Per-project task count. Memoized so re-renders don't rehash on every
  // row. `Map<projectId, count>`. Synthesized "Unassigned" row intentionally
  // gets whatever count falls out of the join.
  const taskCountByProject = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of tasks) {
      const pid = t.projectId ?? 'unassigned';
      m.set(pid, (m.get(pid) ?? 0) + 1);
    }
    return m;
  }, [tasks]);

  function handleDelete(e: React.MouseEvent, projectId: string, projectName: string) {
    e.stopPropagation();
    if (
      confirm(
        `Remove "${projectName}" from the WebUI?\n\nProject files on disk will NOT be deleted.`,
      )
    ) {
      deleteProject.mutate(projectId);
    }
  }

  return (
    <div
      className="flex h-full flex-col"
      style={{ background: 'var(--color-bg)' }}
      data-testid="projects-page"
    >
      {/* Header — full-bleed surface bar; inner row wrapped in .page-container
          so the title aligns with the table body below (R1/R2 from 3.7e-a). */}
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

      {/* Body — scrollable, content centered to .page-container (1280). */}
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
                    height: '48px',
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
            <div
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-card)',
                boxShadow: 'var(--shadow-sm)',
                overflow: 'hidden',
              }}
            >
              <table
                data-testid="projects-table"
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: '13px',
                  color: 'var(--color-text)',
                }}
              >
                <thead>
                  <tr
                    style={{
                      background: 'var(--color-muted-bg)',
                      borderBottom: '1px solid var(--color-border)',
                    }}
                  >
                    <th style={thStyle('48px')} aria-label="Color" />
                    <th style={thStyle('auto', 'left')}>Name</th>
                    <th style={thStyle('auto', 'left')}>Path</th>
                    <th style={thStyle('80px', 'right')}>Tasks</th>
                    <th style={thStyle('120px', 'right')}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.map((project, i) => {
                    const color = getProjectColor(project.id, project.settings?.color);
                    const taskCount = taskCountByProject.get(project.id) ?? 0;
                    const isLast = i === projects.length - 1;
                    return (
                      <tr
                        key={project.id}
                        data-testid={`projects-row-${project.id}`}
                        style={{
                          borderBottom: isLast
                            ? 'none'
                            : '1px solid var(--color-border)',
                          transition: 'background 120ms',
                          cursor: project.synthesized ? 'default' : 'pointer',
                        }}
                        onClick={() => {
                          if (!project.synthesized) setSettingsFor(project);
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.background =
                            'var(--color-muted-bg)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.background = 'transparent';
                        }}
                      >
                        {/* Color */}
                        <td
                          data-testid={`projects-cell-${project.id}-color`}
                          style={tdStyle()}
                        >
                          <div
                            aria-hidden="true"
                            style={{
                              width: '10px',
                              height: '10px',
                              borderRadius: '9999px',
                              background: color.hsl,
                              margin: '0 auto',
                            }}
                          />
                        </td>

                        {/* Name */}
                        <td
                          data-testid={`projects-cell-${project.id}-name`}
                          style={{ ...tdStyle(), fontWeight: 600 }}
                        >
                          <span
                            style={{
                              color: project.synthesized
                                ? 'var(--color-muted)'
                                : 'var(--color-text)',
                            }}
                          >
                            {project.name}
                          </span>
                          {project.synthesized && (
                            <span
                              style={{
                                marginLeft: '8px',
                                fontSize: '11px',
                                fontWeight: 500,
                                color: 'var(--color-muted)',
                              }}
                            >
                              (synthesized)
                            </span>
                          )}
                        </td>

                        {/* Path */}
                        <td
                          data-testid={`projects-cell-${project.id}-path`}
                          style={{
                            ...tdStyle(),
                            fontFamily:
                              'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                            fontSize: '12px',
                            color: 'var(--color-muted)',
                            maxWidth: '400px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                          title={project.path || '(synthesized)'}
                        >
                          {project.path || '—'}
                        </td>

                        {/* Tasks */}
                        <td
                          data-testid={`projects-cell-${project.id}-tasks`}
                          style={{
                            ...tdStyle(),
                            textAlign: 'right',
                            fontVariantNumeric: 'tabular-nums',
                            color:
                              taskCount > 0
                                ? 'var(--color-text)'
                                : 'var(--color-muted)',
                          }}
                        >
                          {taskCount}
                        </td>

                        {/* Actions */}
                        <td
                          data-testid={`projects-cell-${project.id}-actions`}
                          style={{ ...tdStyle(), textAlign: 'right' }}
                        >
                          <div className="inline-flex items-center gap-1">
                            {!project.synthesized && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSettingsFor(project);
                                }}
                                data-testid={`projects-settings-${project.id}`}
                                aria-label="Project settings"
                                className="rounded-[var(--radius-button)] transition-colors"
                                style={{
                                  padding: '6px',
                                  color: 'var(--color-muted)',
                                  background: 'transparent',
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background =
                                    'var(--color-muted-bg)';
                                  e.currentTarget.style.color =
                                    'var(--color-text)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background =
                                    'transparent';
                                  e.currentTarget.style.color =
                                    'var(--color-muted)';
                                }}
                              >
                                <SettingsIcon size={14} />
                              </button>
                            )}
                            {!project.synthesized && (
                              <button
                                type="button"
                                onClick={(e) =>
                                  handleDelete(e, project.id, project.name)
                                }
                                data-testid={`projects-delete-${project.id}`}
                                aria-label="Remove project"
                                className="rounded-[var(--radius-button)] transition-colors"
                                style={{
                                  padding: '6px',
                                  color: 'var(--color-muted)',
                                  background: 'transparent',
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.background =
                                    'var(--color-error-bg)';
                                  e.currentTarget.style.color =
                                    'var(--color-error)';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.background =
                                    'transparent';
                                  e.currentTarget.style.color =
                                    'var(--color-muted)';
                                }}
                              >
                                <Trash2 size={14} />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <ProjectWizard open={showWizard} onOpenChange={setShowWizard} />
      <ProjectSettingsDialog
        project={settingsFor}
        open={settingsFor !== null}
        onOpenChange={(open) => {
          if (!open) setSettingsFor(null);
        }}
      />
    </div>
  );
}

/** Shared <th> style — avoids Tailwind class thrash and keeps widths honest. */
function thStyle(
  width: string,
  align: 'left' | 'right' = 'left',
): React.CSSProperties {
  return {
    padding: '10px 16px',
    textAlign: align,
    fontSize: '11px',
    fontWeight: 600,
    letterSpacing: '0.04em',
    textTransform: 'uppercase',
    color: 'var(--color-muted)',
    width,
  };
}

/** Shared <td> style — vertical rhythm + border-bottom come from <tr>. */
function tdStyle(): React.CSSProperties {
  return {
    padding: '12px 16px',
    verticalAlign: 'middle',
  };
}
