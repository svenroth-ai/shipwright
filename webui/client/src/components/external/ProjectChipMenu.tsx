/*
 * ProjectChipMenu — Radix Popover listing every known project plus the
 * synthesized Unassigned bucket (iterate 3 section 04, FR-03.03
 * follow-through).
 *
 * This is the primary UI path to move a task between projects. Click the
 * chip → popover opens → select a project → `useReassignTask` mutation
 * fires with optimistic update. Clicking the currently-selected entry is
 * a no-op (we don't round-trip the server for a no-op).
 *
 * 3.7d-b2 — the chip is no longer rendered in the TaskDetail header
 * (breadcrumb already shows the project name). Instead a "Move to
 * project…" entry in the 3-dots menu programmatically opens this same
 * popover via controlled `open` / `onOpenChange`. Pass `triggerless`
 * when you want the popover-content only (no chip button), anchored
 * around the parent. The default chip variant is still used in other
 * surfaces (Inbox, elsewhere).
 */

import { useState, type ReactNode } from "react";
import { Check, ChevronDown, Folder } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";

import type { ExternalTask } from "../../lib/externalApi";
import { UNASSIGNED_PROJECT_ID } from "../../lib/projectIds";
import { useProjects } from "../../hooks/useProjects";
import { useReassignTask } from "../../hooks/useReassignTask";

interface Props {
  task: ExternalTask;
  /**
   * Controlled open state. When provided together with `onOpenChange`,
   * the component is fully controlled (used by TaskDetail 3-dots menu to
   * open the project-picker from a menu item). Leaving both unset keeps
   * the default uncontrolled chip behavior.
   */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /**
   * Custom trigger element. When set, replaces the default chip button
   * (used rarely — the controlled-open path is usually sufficient).
   */
  trigger?: ReactNode;
}

interface OptionRow {
  id: string;
  name: string;
  color?: string;
  synthesized?: boolean;
}

export function ProjectChipMenu({ task, open: openProp, onOpenChange, trigger }: Props) {
  const isControlled = openProp !== undefined && onOpenChange !== undefined;
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const open = isControlled ? openProp! : uncontrolledOpen;
  const setOpen = (next: boolean) => {
    if (isControlled) {
      onOpenChange!(next);
    } else {
      setUncontrolledOpen(next);
    }
  };
  const projectsQ = useProjects();
  const reassign = useReassignTask();

  const realProjects: OptionRow[] = (projectsQ.data ?? [])
    .filter((p) => p.id !== UNASSIGNED_PROJECT_ID)
    .map((p) => ({
      id: p.id,
      name: p.name,
      color: p.settings?.color,
    }));

  const options: OptionRow[] = [
    ...realProjects,
    {
      id: UNASSIGNED_PROJECT_ID,
      name: "Unassigned",
      synthesized: true,
    },
  ];

  const currentOption =
    options.find((o) => o.id === task.projectId) ?? options[options.length - 1];

  const handlePick = (next: string) => {
    if (next === task.projectId) {
      setOpen(false);
      return;
    }
    reassign.mutate(
      { taskId: task.taskId, projectId: next },
      {
        onSettled: () => setOpen(false),
      },
    );
    // Close eagerly; onSettled is a safety net for slow responses.
    setOpen(false);
  };

  // Triggerless controlled mode (e.g., opened from the TaskDetail 3-dots
  // menu): render a tiny anchor element so Radix still has positioning
  // context, but no visible trigger button.
  const triggerNode =
    trigger !== undefined ? (
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
    ) : isControlled ? (
      <Popover.Anchor className="absolute right-2 top-full h-0 w-0" />
    ) : (
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border,#e0dbd4)] bg-[var(--color-muted-bg,#ede8e1)] px-2.5 py-0.5 text-[11px] font-medium text-[var(--color-text,#1a1a1a)] transition hover:border-[var(--color-primary,#6b5e56)]"
          data-testid="project-chip-trigger"
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <Folder size={11} className="text-[var(--color-accent,#857568)]" />
          <span data-testid="project-chip-name">{currentOption.name}</span>
          <ChevronDown size={11} className="text-[var(--color-accent,#857568)]" />
        </button>
      </Popover.Trigger>
    );

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      {triggerNode}
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 min-w-[220px] rounded-lg border border-[var(--color-border,#e0dbd4)] bg-[var(--color-surface,#ffffff)] p-1 shadow-[var(--shadow-card,0_6px_30px_rgba(0,0,0,0.10))]"
          data-testid="project-chip-popover"
        >
          <ul role="listbox" aria-label="Reassign project" className="flex flex-col">
            {options.map((opt) => {
              const selected = opt.id === task.projectId;
              return (
                <li key={opt.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => handlePick(opt.id)}
                    disabled={reassign.isPending}
                    className={`flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[12px] transition hover:bg-[var(--color-muted-bg,#ede8e1)] disabled:opacity-60 ${
                      opt.synthesized ? "text-[var(--color-muted,#6b7280)]" : "text-[var(--color-text,#1a1a1a)]"
                    }`}
                    data-testid={`project-chip-option-${opt.id}`}
                  >
                    <span
                      aria-hidden="true"
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{
                        background:
                          opt.color ??
                          (opt.synthesized
                            ? "var(--color-muted, #9ca3af)"
                            : "var(--color-accent, #857568)"),
                      }}
                    />
                    <span className="flex-1 truncate">{opt.name}</span>
                    {selected && (
                      <Check
                        size={12}
                        className="text-[var(--color-primary,#6b5e56)]"
                        data-testid={`project-chip-check-${opt.id}`}
                      />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
