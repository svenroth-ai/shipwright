import { Plus } from 'lucide-react';

interface NewIssueButtonProps {
  onClick: () => void;
}

export function NewIssueButton({ onClick }: NewIssueButtonProps) {
  return (
    <button
      className="flex items-center gap-1.5 px-4 py-[7px] rounded-lg text-[13px] font-semibold text-white bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover,#5a4f48)] hover:shadow-sm transition-all cursor-pointer whitespace-nowrap"
      onClick={onClick}
    >
      <Plus size={14} />
      New Issue
    </button>
  );
}
