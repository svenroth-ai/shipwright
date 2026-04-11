interface ConfirmationStepProps {
  name: string;
  path: string;
  profile: string;
}

export function ConfirmationStep({ name, path, profile }: ConfirmationStepProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">Review your project settings:</p>
      <div className="bg-gray-50 rounded-lg p-4 space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Name</span>
          <span className="font-medium">{name}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Directory</span>
          <span className="font-mono text-xs">{path}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Profile</span>
          <span className="font-medium">{profile}</span>
        </div>
      </div>
      <p className="text-xs text-gray-400">
        Click "Create Project" to register the project and add it to your board.
      </p>
    </div>
  );
}
