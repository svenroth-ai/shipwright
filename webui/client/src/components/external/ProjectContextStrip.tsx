/*
 * Read-only project chip rendered by NewIssueModal when
 * `useProjectFilter` returns a scoped project (not "All projects").
 *
 * Shape mirrors .project-context from new-task-dialog.html — a soft
 * neutral card with a color dot, name, and truncated path.
 */

import { FolderOpen } from "lucide-react";

export interface ProjectContextStripProps {
  name: string;
  /** Optional accent color from project.settings.color. */
  color?: string;
  /** Absolute path — UI truncates but we pass the full string for `title`. */
  path?: string;
}

export function ProjectContextStrip({
  name,
  color,
  path,
}: ProjectContextStripProps) {
  return (
    <div
      className="flex items-center gap-2 rounded-[var(--radius-button,8px)] border border-[var(--color-border,#e0dbd4)] bg-[var(--color-muted-bg,#ede8e1)] px-3 py-2 text-[12px] text-neutral-500"
      data-testid="project-context-strip"
    >
      <FolderOpen size={13} className="shrink-0 text-[var(--color-accent,#857568)]" />
      <span className="opacity-85">Creating in</span>
      <span
        aria-hidden="true"
        className="h-[9px] w-[9px] shrink-0 rounded-full"
        style={{ background: color ?? "var(--color-muted, #9ca3af)" }}
      />
      <span className="font-semibold text-neutral-900" data-testid="project-context-name">
        {name}
      </span>
      {path && (
        <span
          className="ml-auto max-w-[240px] overflow-hidden truncate font-mono text-[11px] opacity-80"
          title={path}
          data-testid="project-context-path"
        >
          {path}
        </span>
      )}
    </div>
  );
}
