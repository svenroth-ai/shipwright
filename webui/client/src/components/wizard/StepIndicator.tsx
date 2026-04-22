import { Check } from 'lucide-react';

const STEPS = ['Project Info', 'Stack & Profile', 'Environment', 'Confirm'];

interface StepIndicatorProps {
  currentStep: number;
}

/**
 * Step indicator — mockup-faithful rebuild (05-project-wizard.html).
 *
 * 10px circles with three visual states:
 *   - pending    : border-only, transparent bg
 *   - active     : filled primary + 3px glow ring (rgba(107,94,86,0.15))
 *   - completed  : filled success + inset check icon
 *
 * Dots are joined by 20px / 2px horizontal connector lines:
 *   - pending  span → --color-border
 *   - completed span → --color-success
 *
 * Right of the dot row sits a compact label: "Step N of M — <name>".
 */
export function StepIndicator({ currentStep }: StepIndicatorProps) {
  const total = STEPS.length;
  return (
    <div
      className="flex items-center gap-[14px] px-7 pt-5 pb-0"
      data-testid="wizard-step-indicator"
    >
      <div className="flex items-center gap-2">
        {STEPS.map((_, i) => {
          const isDone = i < currentStep;
          const isActive = i === currentStep;
          return (
            <div key={i} className="flex items-center gap-2">
              {i > 0 && (
                <div
                  className={`w-5 h-[2px] rounded-[1px] transition-colors ${
                    isDone
                      ? 'bg-[var(--color-success)]'
                      : 'bg-[var(--color-border)]'
                  }`}
                />
              )}
              <div
                className={`w-[10px] h-[10px] rounded-full flex items-center justify-center transition-all shrink-0 ${
                  isDone
                    ? 'bg-[var(--color-success)] border-2 border-[var(--color-success)]'
                    : isActive
                      ? 'bg-[var(--color-primary)] border-2 border-[var(--color-primary)]'
                      : 'bg-transparent border-2 border-[var(--color-border)]'
                }`}
                style={
                  isActive
                    ? { boxShadow: '0 0 0 4px rgba(107, 94, 86, 0.15)' }
                    : undefined
                }
                aria-current={isActive ? 'step' : undefined}
              >
                {isDone && <Check size={8} className="text-white" strokeWidth={3} />}
              </div>
            </div>
          );
        })}
      </div>
      <span className="text-[13px] font-medium text-[var(--color-muted)]">
        Step {currentStep + 1} of {total} &mdash; {STEPS[currentStep]}
      </span>
    </div>
  );
}
