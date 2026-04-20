interface ConfirmationStepProps {
  name: string;
  path: string;
  profile: string;
}

export function ConfirmationStep({ name, path, profile }: ConfirmationStepProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-[var(--color-muted)]">Review your project settings:</p>
      <div className="bg-[var(--color-muted-bg)] rounded-[var(--radius-button)] p-4 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-[var(--color-muted)]">Name</span>
          <span className="font-medium text-[var(--color-text)]">{name}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-[var(--color-muted)]">Directory</span>
          <span className="font-mono text-xs text-[var(--color-text)]">{path}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-[var(--color-muted)]">Profile</span>
          <span className="font-medium text-[var(--color-text)]">{profile}</span>
        </div>
      </div>
      <p className="text-xs text-[var(--color-muted)]">
        Click "Create Project" to register the project and add it to your board.
      </p>
    </div>
  );
}
