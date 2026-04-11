import { useSettings, useSaveSettings } from '../hooks/useSettings';

export default function SettingsPage() {
  const { data: settings, isLoading } = useSettings();
  const saveMutation = useSaveSettings();

  if (isLoading) {
    return <div className="p-6"><div className="h-40 bg-gray-100 rounded-xl animate-pulse" /></div>;
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Settings</h1>

      <div className="space-y-6">
        {/* Global Settings */}
        <section className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">Global Settings</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Max Concurrent Tasks</div>
                <div className="text-xs text-gray-400">Maximum parallel Claude processes</div>
              </div>
              <input
                type="number"
                min={1}
                max={10}
                defaultValue={3}
                className="w-16 px-2 py-1 border border-gray-200 rounded text-sm text-center"
                onBlur={(e) => saveMutation.mutate({ maxConcurrent: Number(e.target.value) } as Record<string, unknown> as never)}
              />
            </div>
          </div>
        </section>

        {/* About */}
        <section className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-900 mb-2">About</h2>
          <p className="text-xs text-gray-500">
            Shipwright Command Center v0.1.0 — Local web UI for managing Shipwright SDLC projects.
          </p>
          {settings && (
            <pre className="mt-2 text-[10px] text-gray-400 bg-gray-50 rounded p-2">
              {JSON.stringify(settings, null, 2)}
            </pre>
          )}
        </section>
      </div>
    </div>
  );
}
