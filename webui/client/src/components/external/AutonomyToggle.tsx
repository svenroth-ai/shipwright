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
 *
 * Iterate 3.7c-3 — the hint block is wrapped in a fixed-height slot
 * (min-h-[50px]) so switching Guided↔Autonomous does not reflow the
 * modal. Autonomous copy is the taller of the two (3 wrapped lines at
 * 11px / 1.5 line-height ≈ 49.5 px in the default 540/580-px modal
 * widths); Guided fits inside the same slot without growing it.
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
    <div className="flex items-start gap-3" data-testid="autonomy-toggle">
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
      {/*
        Fixed-height slot: 50 px holds the taller Autonomous copy (3 lines)
        and leaves Guided's 2 lines top-aligned so the modal does not shift
        vertically when the user toggles. Iterate 3.7c-3.
      */}
      <div
        className="flex-1 min-h-[50px] text-[11px] leading-[1.5] text-[var(--color-muted,#6b7280)]"
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
          : "bg-white text-[var(--color-muted,#6b7280)] hover:bg-[var(--color-muted-bg,#ede8e1)] hover:text-[var(--color-text,#1a1a1a)]"
      }`}
    >
      {icon} {label}
    </button>
  );
}
