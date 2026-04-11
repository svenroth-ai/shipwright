import { Check } from 'lucide-react';

const STEPS = ['Project Info', 'Stack & Profile', 'Environment', 'Confirm'];

interface StepIndicatorProps {
  currentStep: number;
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {STEPS.map((label, i) => {
        const isDone = i < currentStep;
        const isActive = i === currentStep;
        return (
          <div key={i} className="flex items-center gap-2">
            {i > 0 && <div className={`w-8 h-px ${isDone ? 'bg-[var(--color-primary)]' : 'bg-gray-200'}`} />}
            <div className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                isDone ? 'bg-[var(--color-primary)] text-white' :
                isActive ? 'border-2 border-[var(--color-primary)] text-[var(--color-primary)]' :
                'border-2 border-gray-200 text-gray-400'
              }`}>
                {isDone ? <Check size={14} /> : i + 1}
              </div>
              <span className={`text-xs font-medium ${isActive ? 'text-gray-900' : 'text-gray-400'}`}>
                {label}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
