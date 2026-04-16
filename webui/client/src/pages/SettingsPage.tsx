import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import * as Tabs from '@radix-ui/react-tabs';
import * as Select from '@radix-ui/react-select';
import { ChevronDown, Plus, Trash2 } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useSettings, useSaveSettings } from '../hooks/useSettings';
import { useProjects } from '../hooks/useProjects';
import { apiPatch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { PhaseMappingConfig } from '../components/board/PhaseMappingConfig';
import { DEFAULT_PHASE_MAPPING } from '../lib/phaseMapping';
import { getProjectColor } from '../lib/projectColor';
import type { KanbanStatus, Project } from '../types';
import type { AutonomyOption } from '../types/settings';

const TAB_CLASS =
  'px-4 py-2.5 text-sm font-medium text-gray-500 border-b-2 border-transparent data-[state=active]:text-[var(--color-primary)] data-[state=active]:border-[var(--color-primary)] hover:text-gray-700 transition-colors';

// Iterate 14.8.2 — model options for the Default Model dropdown
// Iterate 14.9 — Opus 7 added as newest flagship.
const MODEL_OPTIONS = [
  { value: 'claude-opus-7-0', label: 'Opus 7.0 (1M)' },
  { value: 'claude-opus-4-6', label: 'Opus 4.6 (1M)' },
  { value: 'claude-opus-4-5', label: 'Opus 4.5 (200K)' },
  { value: 'claude-sonnet-4-6', label: 'Sonnet 4.6 (1M)' },
  { value: 'claude-sonnet-4-5', label: 'Sonnet 4.5 (200K)' },
  { value: 'claude-haiku-4-5', label: 'Haiku 4.5 (200K)' },
];

// Iterate 14.9 — Auto mode (Claude picks the best permission mode per turn)
// added as the new first option and new default.
const MODE_OPTIONS = [
  { value: 'auto', label: 'Auto mode' },
  { value: 'bypassPermissions', label: 'Bypass permissions' },
  { value: 'acceptEdits', label: 'Edit automatically' },
  { value: 'default', label: 'Ask for permission' },
  { value: 'plan', label: 'Plan mode' },
];

export default function SettingsPage() {
  const { data: settings, isLoading } = useSettings();
  const { data: projects = [] } = useProjects();
  const saveMutation = useSaveSettings();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  // Iterate 14.8.2 — deep-link: read ?projectId= and ?tab= from URL
  const initialTab = searchParams.get('tab') ?? 'global';
  const initialProjectId = searchParams.get('projectId') ?? null;
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(initialProjectId);

  // If deep-linked projectId doesn't match any known project, fall back
  // to the first project and log a warning.
  useEffect(() => {
    if (initialProjectId && projects.length > 0) {
      const exists = projects.some((p) => p.id === initialProjectId);
      if (!exists) {
        console.warn(`[SettingsPage] Deep-link projectId "${initialProjectId}" not found — falling back to first project.`);
        setSelectedProjectId(projects[0].id);
      }
    }
  }, [initialProjectId, projects]);

  const updateProject = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Project> }) =>
      apiPatch<Project>(`/projects/${id}`, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      if (selectedProjectId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.projects.detail(selectedProjectId) });
      }
    },
  });

  if (isLoading) {
    return <div className="p-6"><div className="h-40 bg-gray-100 rounded-xl animate-pulse" /></div>;
  }

  const selectedProject = projects.find((p) => p.id === selectedProjectId);

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold text-gray-900 mb-6">Settings</h1>

      <Tabs.Root defaultValue={initialTab}>
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
                <div className="text-xs text-gray-400">Fallback for projects without override</div>
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

            {/* Iterate 14.8.2 — Default Model dropdown */}
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Default Model</div>
                <div className="text-xs text-gray-400">Model used for new tasks when none specified</div>
              </div>
              <select
                data-testid="default-model-select"
                value={settings?.defaultModel ?? 'claude-opus-7-0'}
                onChange={(e) => saveMutation.mutate({ defaultModel: e.target.value })}
                className="px-2 py-1.5 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              >
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            {/* Iterate 14.8.2 — Default Permission Mode dropdown */}
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium text-gray-700">Default Permission Mode</div>
                <div className="text-xs text-gray-400">Permission mode for new tasks when none specified</div>
              </div>
              <select
                data-testid="default-mode-select"
                value={settings?.defaultMode ?? 'auto'}
                onChange={(e) => saveMutation.mutate({ defaultMode: e.target.value })}
                className="px-2 py-1.5 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              >
                {MODE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
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
            <h2 className="text-sm font-semibold text-gray-900 mb-2">Phase &rarr; Kanban Status Mapping</h2>
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
                  <ProjectSettingsPanel
                    project={selectedProject}
                    globalAutonomy={settings?.defaultAutonomy ?? 'guided'}
                    onUpdate={(patch) => updateProject.mutate({ id: selectedProject.id, patch })}
                  />
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

/* ── Per-Project Settings Panel ── */
interface ProjectSettingsPanelProps {
  project: Project;
  globalAutonomy: AutonomyOption;
  onUpdate: (patch: Partial<Project>) => void;
}

function ProjectSettingsPanel({ project, globalAutonomy, onUpdate }: ProjectSettingsPanelProps) {
  const projectAutonomy = project.settings?.autonomy;
  const envVars = project.settings?.envVars ?? {};
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');

  function handleAutonomyChange(opt: AutonomyOption | 'inherit') {
    const settings = { ...project.settings };
    if (opt === 'inherit') {
      delete settings.autonomy;
    } else {
      settings.autonomy = opt;
    }
    onUpdate({ settings });
  }

  function handleAddEnvVar() {
    const key = newKey.trim();
    if (!key) return;
    const settings = { ...project.settings, envVars: { ...envVars, [key]: newValue } };
    onUpdate({ settings });
    setNewKey('');
    setNewValue('');
  }

  function handleRemoveEnvVar(key: string) {
    const updated = { ...envVars };
    delete updated[key];
    const settings = { ...project.settings, envVars: updated };
    onUpdate({ settings });
  }

  return (
    <div className="space-y-6">
      {/* Basic info */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-gray-700">Profile</div>
            <div className="text-xs text-gray-400">Stack profile for this project</div>
          </div>
          <span className="text-sm text-gray-600">{project.profile}</span>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-gray-700">Status</div>
            <div className="text-xs text-gray-400">Current project status</div>
          </div>
          <span className={`text-sm font-medium ${project.status === 'active' ? 'text-green-600' : project.status === 'error' ? 'text-red-600' : 'text-gray-500'}`}>
            {project.status}
          </span>
        </div>
        <div>
          <div className="text-sm font-medium text-gray-700">Path</div>
          <div className="text-xs text-gray-500 font-mono mt-0.5">{project.path}</div>
        </div>
      </div>

      {/* Autonomy */}
      <div className="border-t border-gray-100 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-gray-700">Autonomy Level</div>
            <div className="text-xs text-gray-400">
              {!projectAutonomy
                ? `Inheriting global default: ${globalAutonomy}`
                : 'Overrides global default'}
            </div>
          </div>
          <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
            {(['inherit', 'guided', 'autonomous'] as const).map((opt) => {
              const isActive = opt === 'inherit'
                ? !projectAutonomy
                : projectAutonomy === opt;
              return (
                <button
                  key={opt}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    isActive
                      ? 'bg-white text-[var(--color-primary)] shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                  onClick={() => handleAutonomyChange(opt)}
                >
                  {opt === 'inherit' ? 'Inherit' : opt === 'guided' ? 'Guided' : 'Autonomous'}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Iterate 14.8.2 — Project Color */}
      <div className="border-t border-gray-100 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-gray-700">Project Color</div>
            <div className="text-xs text-gray-400">Used as the colored strip on task cards in the All Projects view</div>
          </div>
          <input
            type="color"
            data-testid="project-color-picker"
            value={project.settings?.color ?? getProjectColor(project.id).hsl}
            onChange={(e) => {
              const settings = { ...project.settings, color: e.target.value };
              onUpdate({ settings });
            }}
            className="w-10 h-8 border border-[#e0dbd4] rounded-lg cursor-pointer"
          />
        </div>
      </div>

      {/* Environment Variables */}
      <div className="border-t border-gray-100 pt-4">
        <h3 className="text-sm font-medium text-gray-700 mb-1">Environment Variables</h3>
        <p className="text-xs text-gray-400 mb-3">Passed to Claude CLI subprocess for this project.</p>

        {Object.keys(envVars).length > 0 && (
          <div className="space-y-1.5 mb-3">
            {Object.entries(envVars).map(([key, value]) => (
              <div key={key} className="flex items-center gap-2 text-xs">
                <span className="font-mono font-medium text-gray-700 min-w-[120px]">{key}</span>
                <span className="text-gray-400">=</span>
                <span className="font-mono text-gray-500 flex-1 truncate">{value}</span>
                <button
                  onClick={() => handleRemoveEnvVar(key)}
                  className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                  title="Remove"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2">
          <input
            value={newKey}
            onChange={(e) => setNewKey(e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, ''))}
            placeholder="KEY"
            className="w-32 px-2 py-1.5 text-xs font-mono border border-[#e0dbd4] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
            onKeyDown={(e) => e.key === 'Enter' && handleAddEnvVar()}
          />
          <span className="text-gray-400 text-xs">=</span>
          <input
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            placeholder="value"
            className="flex-1 px-2 py-1.5 text-xs font-mono border border-[#e0dbd4] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20"
            onKeyDown={(e) => e.key === 'Enter' && handleAddEnvVar()}
          />
          <button
            onClick={handleAddEnvVar}
            disabled={!newKey.trim()}
            className="p-1.5 rounded-lg bg-[var(--color-primary)] text-white disabled:opacity-40 hover:opacity-90 transition-opacity"
            title="Add variable"
          >
            <Plus size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
