/*
 * Sidebar project list — iterate 3 section 02, FR-03.01..03.05.
 *
 * Lives below the main nav. Each row: color dot + project name. Clicking a
 * row sets the active-project filter via the shared useProjectFilter hook.
 * The top "All projects" row clears the filter.
 *
 * The synthesized "Unassigned" row (server-side ADR-037) arrives from
 * /api/projects with `synthesized: true` set. Rendered muted, with a ring
 * dot instead of a filled color dot (design: kanban-with-projects.html
 * line 863).
 *
 * Active row reads straight from useProjectFilter — no local state. Two
 * consumers (this list + TaskBoardPage filter chip) MUST NOT duplicate the
 * state (external review O27).
 */

import { useMemo } from "react";

import { useProjects } from "../../hooks/useProjects";
import { useProjectFilter } from "../../hooks/useProjectFilter";
import { UNASSIGNED_PROJECT_ID } from "../../lib/projectIds";
import type { Project } from "../../types";

interface SidebarProjectListProps {
  collapsed?: boolean;
}

export function SidebarProjectList({ collapsed }: SidebarProjectListProps) {
  const { data: projects } = useProjects();
  const { activeProjectId, setActiveProjectId } = useProjectFilter();

  const visible = useMemo<Project[]>(() => projects ?? [], [projects]);

  if (collapsed) return null;
  if (visible.length === 0) return null;

  return (
    <div
      className="mt-2 border-t border-white/10 px-3 py-3"
      data-testid="sidebar-project-list"
    >
      <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-white/40">
        Projects
      </div>
      <nav className="flex flex-col gap-0.5">
        <ProjectRow
          label="All projects"
          active={activeProjectId === null}
          onClick={() => setActiveProjectId(null)}
          testId="sidebar-project-all"
        />
        {visible.map((p) => (
          <ProjectRow
            key={p.id}
            label={p.name}
            active={activeProjectId === p.id}
            onClick={() => setActiveProjectId(p.id)}
            color={p.synthesized ? undefined : p.settings?.color}
            synthesized={p.synthesized}
            testId={`sidebar-project-${p.id === UNASSIGNED_PROJECT_ID ? "unassigned" : p.id}`}
          />
        ))}
      </nav>
    </div>
  );
}

interface ProjectRowProps {
  label: string;
  active: boolean;
  onClick: () => void;
  color?: string;
  synthesized?: boolean;
  testId?: string;
}

function ProjectRow({ label, active, onClick, color, synthesized, testId }: ProjectRowProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      data-active={active ? "true" : undefined}
      className={`flex items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors ${
        active
          ? "bg-white/[0.14] font-medium text-white"
          : "text-white/70 hover:bg-white/[0.08] hover:text-white"
      } ${synthesized ? "italic" : ""}`}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 shrink-0 rounded-full ${
          synthesized
            ? "border border-white/40"
            : ""
        }`}
        style={synthesized ? undefined : { background: color ?? "var(--color-muted, #9ca3af)" }}
      />
      <span className="flex-1 truncate">{label}</span>
    </button>
  );
}
