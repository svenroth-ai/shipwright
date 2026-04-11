import { useState } from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import * as Select from '@radix-ui/react-select';
import { ChevronDown } from 'lucide-react';
import { useSettings, useSaveSettings } from '../hooks/useSettings';
import { useProjects } from '../hooks/useProjects';
import { PhaseMappingConfig } from '../components/board/PhaseMappingConfig';
import { DEFAULT_PHASE_MAPPING } from '../lib/phaseMapping';
import type { KanbanStatus } from '../types';
import type { AutonomyOption } from '../types/settings';

const TAB_CLASS =
  'px-4 py-2.5 text-sm font-medium text-gray-500 border-b-2 border-transparent data-[state=active]:text-[var(--color-primary)] data-[state=active]:border-[var(--color-primary)] hover:text-gray-700 transition-colors';

export default function SettingsPage() {
  const { data: settings, isLoading } = useSettings();
  const { data: projects = [] } = useProjects();
  const saveMutation = useSaveSettings();
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  if (isLoading) {
    return <div className="p-6"><div className="h-40 bg-gray-100 rounded-xl animate-pulse" /></div>;
  }

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Settings</h1>

      <Tabs.Root defaultValue="global">
        <Tabs.List className="flex gap-0 border-b border-[#e0dbd4] mb-6">
          <Tabs.Trigger value="global" className={TAB_CLASS}>Global</Tabs.Trigger>
          <Tabs.Trigger value="phases" className={TAB_CLASS}>Phase Mapping</Tabs.Trigger>
          <Tabs.Trigger value="project" className={TAB_CLASS}>Project</Tabs.Trigger>
          <Tabs.Trigger value="about" className={TAB_CLASS}>About</Tabs.Trigger>
        </Tabs.List>

        {/* Global Settings */}
        <Tabs.Content value="global">
          <section className="bg-white rounded-xl border-0 shadow-[var(--shadow-card)] p-5 space-y-5">
            <h2 className="text-sm font-semibold text-gray-900">Global Settings</h2>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Max Concurrent Tasks</div>
                <div className="text-xs text-gray-400">Maximum parallel Claude processes</div>
              </div>
              <input
                type="number"
                min={1}
                max={10}
                defaultValue={settings?.maxConcurrent ?? 3}
                className="w-16 px-2 py-1.5 border border-[#e0dbd4] rounded-lg text-sm text-center focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
                onBlur={(e) => saveMutation.mutate({ maxConcurrent: Number(e.target.value) })}
              />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Default Autonomy</div>
                <div className="text-xs text-gray-400">Autonomy level for new tasks</div>
              </div>
              <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
                {(['guided', 'autonomous'] as AutonomyOption[]).map((opt) => (
                  <button
                    key={opt}
                    className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                      (settings?.defaultAutonomy ?? 'guided') === opt
                        ? 'bg-white text-[var(--color-primary)] shadow-sm'
                        : 'text-gray-500 hover:text-gray-700'
                    }`}
                    onClick={() => saveMutation.mutate({ defaultAutonomy: opt })}
                  >
                    {opt === 'guided' ? 'Guided' : 'Autonomous'}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Default Profile</div>
                <div className="text-xs text-gray-400">Stack profile for new projects</div>
              </div>
              <span className="text-sm text-gray-600">{settings?.defaultProfile ?? 'auto-detect'}</span>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Heartbeat Interval</div>
                <div className="text-xs text-gray-400">Process health check frequency</div>
              </div>
              <span className="text-sm text-gray-600">{settings?.heartbeatIntervalMs ? `${settings.heartbeatIntervalMs / 1000}s` : '30s'}</span>
            </div>
          </section>
        </Tabs.Content>

        {/* Phase Mapping */}
        <Tabs.Content value="phases">
          <section className="bg-white rounded-xl border-0 shadow-[var(--shadow-card)] p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">Phase → Kanban Status Mapping</h2>
            <p className="text-xs text-gray-400 mb-4">Controls which Kanban column a task appears in based on its current pipeline phase.</p>
            <PhaseMappingConfig
              mapping={(settings?.phaseToStatusMapping as Record<string, KanbanStatus>) ?? DEFAULT_PHASE_MAPPING}
              onSave={(mapping: Record<string, KanbanStatus>) => {
                saveMutation.mutate({ phaseToStatusMapping: mapping });
              }}
            />
          </section>
        </Tabs.Content>

        {/* Per-Project Settings */}
        <Tabs.Content value="project">
          <section className="bg-white rounded-xl border-0 shadow-[var(--shadow-card)] p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-4">Project Settings</h2>

            {projects.length === 0 ? (
              <p className="text-sm text-gray-400">No projects registered yet.</p>
            ) : (
              <>
                <div className="mb-4">
                  <label className="block text-xs font-medium text-gray-500 uppercase mb-1.5">Select Project</label>
                  <Select.Root
                    value={selectedProjectId ?? ''}
                    onValueChange={(val) => setSelectedProjectId(val)}
                  >
                    <Select.Trigger className="flex items-center justify-between w-full px-3 py-2 text-sm border border-[#e0dbd4] rounded-lg hover:border-gray-400 transition-colors">
                      <Select.Value placeholder="Choose a project..." />
                      <Select.Icon><ChevronDown size={14} className="text-gray-400" /></Select.Icon>
                    </Select.Trigger>
                    <Select.Portal>
                      <Select.Content className="bg-white rounded-lg shadow-lg border border-[#e0dbd4] p-1 z-50" position="popper" sideOffset={4}>
                        <Select.Viewport>
                          {projects.map((p) => (
                            <Select.Item key={p.id} value={p.id} className="flex items-center px-3 py-2 text-sm rounded cursor-pointer hover:bg-gray-50 data-[highlighted]:bg-gray-50 outline-none">
                              <Select.ItemText>{p.name}</Select.ItemText>
                            </Select.Item>
                          ))}
                        </Select.Viewport>
                      </Select.Content>
                    </Select.Portal>
                  </Select.Root>
                </div>

                {selectedProject ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-gray-700">Profile</div>
                        <div className="text-xs text-gray-400">Stack profile for this project</div>
                      </div>
                      <span className="text-sm text-gray-600">{selectedProject.profile}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-gray-700">Status</div>
                        <div className="text-xs text-gray-400">Current project status</div>
                      </div>
                      <span className={`text-sm font-medium ${selectedProject.status === 'active' ? 'text-green-600' : selectedProject.status === 'error' ? 'text-red-600' : 'text-gray-500'}`}>
                        {selectedProject.status}
                      </span>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-gray-700">Path</div>
                      <div className="text-xs text-gray-500 font-mono mt-0.5">{selectedProject.path}</div>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">Select a project to view its settings.</p>
                )}
              </>
            )}
          </section>
        </Tabs.Content>

        {/* About */}
        <Tabs.Content value="about">
          <section className="bg-white rounded-xl border-0 shadow-[var(--shadow-card)] p-5">
            <h2 className="text-sm font-semibold text-gray-900 mb-2">About</h2>
            <p className="text-xs text-gray-500 mb-3">
              Shipwright Command Center v0.1.0 — Local web UI for managing Shipwright SDLC projects.
            </p>
            <div className="space-y-2 text-xs text-gray-500">
              <div className="flex gap-2"><span className="text-gray-400 w-24">Port:</span> {settings?.port ?? 3847}</div>
              <div className="flex gap-2"><span className="text-gray-400 w-24">Claude CLI:</span> {settings?.claudeCliPath ?? 'auto-detect'}</div>
              <div className="flex gap-2"><span className="text-gray-400 w-24">Max Concurrent:</span> {settings?.maxConcurrent ?? 3}</div>
              <div className="flex gap-2"><span className="text-gray-400 w-24">Autonomy:</span> {settings?.defaultAutonomy ?? 'guided'}</div>
            </div>
            <div className="mt-4 p-3 bg-gray-50 rounded-lg">
              <p className="text-xs font-medium text-gray-600 mb-1">Advanced: Plugin Directories</p>
              <p className="text-[11px] text-gray-400">
                Claude plugin directories are auto-detected from the Shipwright installation. To override per-project, edit the project entry in the registry file.
              </p>
            </div>
          </section>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
