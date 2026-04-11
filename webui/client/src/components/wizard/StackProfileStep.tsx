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
      <p className="text-sm text-gray-600 mb-3">Choose a stack profile for your project:</p>
      {PROFILES.map((p) => (
        <button
          key={p.id}
          className={`w-full text-left px-4 py-3 rounded-lg border transition-colors ${
            profile === p.id
              ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5'
              : 'border-[#e0dbd4] hover:border-gray-300'
          }`}
          onClick={() => onProfileChange(p.id)}
        >
          <div className="text-sm font-medium text-gray-900">{p.name}</div>
          <div className="text-xs text-gray-500">{p.desc}</div>
        </button>
      ))}
    </div>
  );
}
