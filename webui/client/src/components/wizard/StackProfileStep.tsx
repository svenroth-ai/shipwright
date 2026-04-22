const PROFILES = [
  { id: 'supabase-nextjs', name: 'Next.js + Supabase', desc: 'Full-stack TypeScript with Supabase Auth, DB, and Storage' },
  { id: 'custom', name: 'Custom', desc: 'Manual configuration — define your own stack' },
];

interface StackProfileStepProps {
  profile: string;
  onProfileChange: (profile: string) => void;
}

export function StackProfileStep({ profile, onProfileChange }: StackProfileStepProps) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--color-muted)] mb-3">
        Choose a stack profile for your project:
      </p>
      {PROFILES.map((p) => {
        const isSelected = profile === p.id;
        return (
          <button
            key={p.id}
            type="button"
            onClick={() => onProfileChange(p.id)}
            className={`w-full text-left px-4 py-3.5 rounded-[var(--radius-button)] border-[1.5px] transition-colors ${
              isSelected
                ? 'border-[var(--color-primary)] bg-[#f9f6f3] shadow-[0_0_0_1px_var(--color-primary)]'
                : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-accent)] hover:bg-[#faf8f6]'
            }`}
          >
            <div className="text-sm font-semibold text-[var(--color-text)]">{p.name}</div>
            <div className="text-[13px] text-[var(--color-muted)] mt-0.5 leading-snug">
              {p.desc}
            </div>
          </button>
        );
      })}
    </div>
  );
}
