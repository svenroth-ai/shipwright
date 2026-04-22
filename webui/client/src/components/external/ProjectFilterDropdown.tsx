/*
 * ProjectFilterDropdown — shared primitive for the TaskBoard header and
 * Inbox header project filter.
 *
 * Iterate 3 remediation Phase A6 (2026-04-20). Scaffolded here; mounted
 * by Phase B1 (TaskBoardPage header) and Phase B4 (InboxPage header).
 * The existing per-page chip-bar implementations stay in place for now;
 * B1/B4 swap them out.
 *
 * Visual shape follows `webui/designs/screens/kanban-with-projects.html`:
 *
 *   ┌─────────────────────────────────────────┐
 *   │ ● shipwright-auth       8 tasks    ▾   │   ← 220px min-width, bordered
 *   └─────────────────────────────────────────┘
 *
 * On open:
 *   • All projects — N tasks
 *   • (synthesized unassigned row — muted)
 *   • shipwright-auth — 8 tasks   ✓  ← active
 *   • dinovo-vision — 2 tasks
 *   ─────────────────
 *   + New project…  (footer — navigates to /projects)
 *
 * State source: consumes the same `useProjectFilter()` context that
 * the existing chip-bar + sidebar list use (external-review O27: single
 * source of truth for active-project selection).
 *
 * Load-bearing testids (Playwright specs across iterate 3 depend on
 * predictable ids):
 *   project-filter-dropdown           — the button
 *   project-filter-dropdown-item-all  — "All projects" row
 *   project-filter-dropdown-item-<id> — per-project row (or `unassigned`)
 *   project-filter-dropdown-new       — footer link to /projects
 */

import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, Plus } from "lucide-react";

import { useProjects } from "../../hooks/useProjects";
import { useProjectFilter } from "../../hooks/useProjectFilter";
import { useExternalTasks } from "../../hooks/useExternalTasks";
import { UNASSIGNED_PROJECT_ID } from "../../lib/projectIds";
import { getProjectColor } from "../../lib/projectColor";
import type { Project } from "../../types";

export interface ProjectFilterDropdownProps {
  /** Optional className forwarded to the root button (outer wrapper). */
  className?: string;
}

export function ProjectFilterDropdown({ className }: ProjectFilterDropdownProps) {
  const navigate = useNavigate();
  const { data: projects = [] } = useProjects();
  const { data: tasks = [] } = useExternalTasks();
  const { activeProjectId, setActiveProjectId } = useProjectFilter();

  const countByProject = useMemo(() => {
    const m = new Map<string, number>();
    for (const t of tasks) m.set(t.projectId, (m.get(t.projectId) ?? 0) + 1);
    return m;
  }, [tasks]);

  const active = useMemo<Project | null>(() => {
    if (activeProjectId === null) return null;
    return projects.find((p) => p.id === activeProjectId) ?? null;
  }, [activeProjectId, projects]);

  const triggerLabel = active?.name ?? "All projects";
  const triggerCount = active ? (countByProject.get(active.id) ?? 0) : tasks.length;
  // iterate 3.7g (Sven UAT): use the deterministic projectColor helper so the
  // dropdown dot matches every other project-color surface (TaskCard strip,
  // Inbox group header, Projects table). Previously this fell back to
  // --color-muted when `settings.color` was unset, which diverged from the
  // hash-derived color used elsewhere. Active "All Projects" (null) gets the
  // muted tint as a neutral marker.
  const triggerDotColor = active
    ? active.synthesized
      ? undefined
      : getProjectColor(active.id, active.settings?.color).hsl
    : "var(--color-muted)";

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          data-testid="project-filter-dropdown"
          className={
            "inline-flex min-w-[220px] items-center gap-2 rounded-[var(--radius-button)] " +
            "border-[1.5px] border-[var(--color-border)] bg-[var(--color-surface)] " +
            "px-3 py-2 text-[13px] font-medium text-[var(--color-text)] " +
            "transition-colors hover:border-[var(--color-primary)] " +
            (className ?? "")
          }
        >
          {active?.synthesized ? (
            <span
              aria-hidden="true"
              className="h-[10px] w-[10px] shrink-0 rounded-full border border-[var(--color-border)]"
            />
          ) : (
            <span
              aria-hidden="true"
              className="h-[10px] w-[10px] shrink-0 rounded-full"
              style={{ background: triggerDotColor }}
            />
          )}
          <span className="flex-1 truncate text-left">{triggerLabel}</span>
          <span className="text-[11px] font-normal text-[var(--color-muted)]">
            {triggerCount} {triggerCount === 1 ? "task" : "tasks"}
          </span>
          <ChevronDown
            size={14}
            className="shrink-0 text-[var(--color-muted)]"
            aria-hidden="true"
          />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="start"
          sideOffset={6}
          className={
            "z-50 min-w-[260px] rounded-[var(--radius-button)] " +
            "border border-[var(--color-border)] bg-[var(--color-surface)] " +
            "p-1 shadow-[var(--shadow-card)]"
          }
        >
          <DropdownMenuRow
            label="All projects"
            active={activeProjectId === null}
            onSelect={() => setActiveProjectId(null)}
            count={tasks.length}
            testId="project-filter-dropdown-item-all"
          />
          {projects.length > 0 && (
            <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border)]" />
          )}
          {projects.map((p) => (
            <DropdownMenuRow
              key={p.id}
              label={p.name}
              active={activeProjectId === p.id}
              onSelect={() => setActiveProjectId(p.id)}
              count={countByProject.get(p.id) ?? 0}
              color={
                p.synthesized
                  ? undefined
                  : getProjectColor(p.id, p.settings?.color).hsl
              }
              synthesized={p.synthesized}
              testId={`project-filter-dropdown-item-${p.id === UNASSIGNED_PROJECT_ID ? "unassigned" : p.id}`}
            />
          ))}
          <DropdownMenu.Separator className="my-1 h-px bg-[var(--color-border)]" />
          <DropdownMenu.Item
            data-testid="project-filter-dropdown-new"
            onSelect={() => navigate("/projects")}
            className={
              "flex cursor-pointer items-center gap-2 rounded-[var(--radius-button)] " +
              "px-2 py-1.5 text-[13px] font-medium text-[var(--color-primary)] outline-none " +
              "focus:bg-[var(--color-muted-bg)] hover:bg-[var(--color-muted-bg)]"
            }
          >
            <Plus size={14} aria-hidden="true" />
            <span>New project…</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

interface DropdownMenuRowProps {
  label: string;
  active: boolean;
  onSelect: () => void;
  count: number;
  color?: string;
  synthesized?: boolean;
  testId: string;
}

function DropdownMenuRow({
  label,
  active,
  onSelect,
  count,
  color,
  synthesized,
  testId,
}: DropdownMenuRowProps) {
  return (
    <DropdownMenu.Item
      data-testid={testId}
      data-active={active ? "true" : undefined}
      onSelect={onSelect}
      className={
        "flex cursor-pointer items-center gap-2 rounded-[var(--radius-button)] " +
        "px-2 py-1.5 text-[13px] outline-none " +
        "focus:bg-[var(--color-muted-bg)] hover:bg-[var(--color-muted-bg)] " +
        (synthesized ? "italic text-[var(--color-muted)] " : "text-[var(--color-text)] ")
      }
    >
      {synthesized ? (
        <span
          aria-hidden="true"
          className="h-[10px] w-[10px] shrink-0 rounded-full border border-[var(--color-border)]"
        />
      ) : (
        <span
          aria-hidden="true"
          className="h-[10px] w-[10px] shrink-0 rounded-full"
          style={{ background: color ?? "var(--color-muted)" }}
        />
      )}
      <span className="flex-1 truncate">{label}</span>
      <span className="text-[11px] font-normal text-[var(--color-muted)]">
        {count}
      </span>
      <Check
        size={14}
        className="shrink-0"
        aria-hidden="true"
        style={{
          color: "var(--color-primary)",
          opacity: active ? 1 : 0,
        }}
      />
    </DropdownMenu.Item>
  );
}
