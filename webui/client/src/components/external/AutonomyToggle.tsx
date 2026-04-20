/*
 * Segmented <button role="radio"> pair for the NewIssueModal's autonomy
 * selector (pipeline + iterate modals only — FR-03.72 means the task
 * modal does NOT render this).
 *
 * Values:
 *   guided    — Claude pauses at every AskUser; user answers in terminal.
 *   autonomous — Claude runs through AskUser defaults without pausing.
 *
 * Controlled by the parent: default comes from `actions.defaults.autonomy`.
 *
 * Visual language matches new-pipeline-dialog.html (.segmented / .segmented-row).
 */

import { CheckCircle, Gauge } from "lucide-react";

export type AutonomyValue = "guided" | "autonomous";

interface AutonomyToggleProps {
  value: AutonomyValue;
  onChange: (next: AutonomyValue) => void;
  /** Override the two-line hint text. Defaults to mockup-matching copy. */
  guidedHint?: React.ReactNode;
  autonomousHint?: React.ReactNode;
}

const DEFAULT_GUIDED_HINT = (
  <>
    <strong>Guided</strong>: Claude pauses at every AskUser — you answer in
    your terminal. Slower, full oversight.
  </>
);
const DEFAULT_AUTONOMOUS_HINT = (
  <>
    <strong>Autonomous</strong>: Claude runs through AskUser defaults without
    pausing. Fastest; good for well-scoped work you trust to its spec.
  </>
);

export function AutonomyToggle({
  value,
  onChange,
  guidedHint = DEFAULT_GUIDED_HINT,
  autonomousHint = DEFAULT_AUTONOMOUS_HINT,
}: AutonomyToggleProps) {
  const hint = value === "autonomous" ? autonomousHint : guidedHint;
  return (
    <div className="flex items-center gap-3" data-testid="autonomy-toggle">
      <div
        className="inline-flex overflow-hidden rounded-[var(--radius-button,8px)] border-[1.5px] border-[var(--color-border,#e0dbd4)]"
        role="radiogroup"
        aria-label="Autonomy"
      >
        <SegmentButton
          active={value === "guided"}
          onClick={() => onChange("guided")}
          label="Guided"
          icon={<Gauge size={12} />}
          testId="autonomy-guided"
        />
        <SegmentButton
          active={value === "autonomous"}
          onClick={() => onChange("autonomous")}
          label="Autonomous"
          icon={<CheckCircle size={12} />}
          testId="autonomy-autonomous"
        />
      </div>
      <div
        className="flex-1 text-[11px] leading-[1.5] text-neutral-500"
        data-testid="autonomy-hint"
      >
        {hint}
      </div>
    </div>
  );
}

function SegmentButton({
  active,
  onClick,
  label,
  icon,
  testId,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
  testId: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      data-active={active ? "true" : undefined}
      data-testid={testId}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 border-0 px-3 py-1.5 text-[12px] font-medium transition-colors first:border-r-[1.5px] first:border-[var(--color-border,#e0dbd4)] ${
        active
          ? "bg-[var(--color-primary,#6b5e56)] text-white"
          : "bg-white text-neutral-500 hover:bg-neutral-50 hover:text-neutral-800"
      }`}
    >
      {icon} {label}
    </button>
  );
}
