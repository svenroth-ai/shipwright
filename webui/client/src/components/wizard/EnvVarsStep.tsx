interface EnvVarsStepProps {
  profile: string;
}

export function EnvVarsStep({ profile }: EnvVarsStepProps) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600">
        Environment variables for <span className="font-medium">{profile}</span> profile.
      </p>
      <div className="bg-gray-50 rounded-lg p-4 text-xs text-gray-500">
        Environment variables will be configured in <code>.env.local</code> after project creation.
        The build system will prompt for any required variables.
      </div>
    </div>
  );
}
