interface EnvVarsStepProps {
  profile: string;
}

export function EnvVarsStep({ profile }: EnvVarsStepProps) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--color-muted)]">
        Environment variables for{' '}
        <span className="font-medium text-[var(--color-text)]">{profile}</span> profile.
      </p>
      <div className="bg-[var(--color-muted-bg)] rounded-[var(--radius-button)] p-4 text-xs text-[var(--color-muted)] leading-relaxed">
        Environment variables will be configured in{' '}
        <code className="rounded bg-[var(--color-surface)] px-1 font-mono text-[var(--color-text)]">
          .env.local
        </code>{' '}
        after project creation. The build system will prompt for any required variables.
      </div>
    </div>
  );
}
