/*
 * Board / List view toggle for the TaskBoard header.
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21). Mirrors mockup
 * `webui/designs/screens/kanban-with-projects.html` lines 192–216 (.view-toggle).
 *
 * State lives on the parent TaskBoardPage via a controlled `value` / `onChange`
 * pair — this component is stateless.
 *
 * Testids:
 *   view-toggle-root, view-toggle-board, view-toggle-list.
 */
import { LayoutGrid, List } from "lucide-react";

export type TaskBoardView = "board" | "list";

interface Props {
  value: TaskBoardView;
  onChange: (next: TaskBoardView) => void;
}

export function ViewToggle({ value, onChange }: Props) {
  return (
    <div
      className={
        "inline-flex overflow-hidden rounded-[var(--radius-button)] " +
        "border-[1.5px] border-[var(--color-border)]"
      }
      data-testid="view-toggle-root"
      role="tablist"
      aria-label="Task view"
    >
      <ToggleButton
        active={value === "board"}
        onClick={() => onChange("board")}
        testId="view-toggle-board"
        icon={<LayoutGrid size={12} />}
        label="Board"
      />
      <div className="w-px self-stretch bg-[var(--color-border)]" aria-hidden="true" />
      <ToggleButton
        active={value === "list"}
        onClick={() => onChange("list")}
        testId="view-toggle-list"
        icon={<List size={12} />}
        label="List"
      />
    </div>
  );
}

interface ToggleButtonProps {
  active: boolean;
  onClick: () => void;
  testId: string;
  icon: React.ReactNode;
  label: string;
}

function ToggleButton({ active, onClick, testId, icon, label }: ToggleButtonProps) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      data-testid={testId}
      className={
        "inline-flex items-center gap-1.5 px-3 py-1 text-[12px] font-medium transition-colors " +
        (active
          ? "bg-[var(--color-muted-bg)] text-[var(--color-primary)]"
          : "bg-transparent text-[var(--color-muted)] hover:bg-[var(--color-muted-bg)] hover:text-[var(--color-text)]")
      }
    >
      {icon}
      {label}
    </button>
  );
}
