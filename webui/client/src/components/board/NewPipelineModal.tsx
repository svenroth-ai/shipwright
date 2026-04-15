import { useEffect, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { X, Workflow, ClipboardPaste } from 'lucide-react';
import { apiFetch, apiPost, ApiError } from '../../lib/api';
import { queryKeys } from '../../lib/queryKeys';
import { pasteFromClipboard, looksLikePath } from '../../lib/filePicker';

export interface ProfileSummary {
  name: string;
  label?: string;
  description?: string;
}

interface NewPipelineModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface CreatePipelineResponse {
  projectId: string;
  taskId?: string;
}

interface CreatePipelineParams {
  name: string;
  path: string;
  profile: string;
}

/**
 * Iterate 14.4 — modal for registering a brand-new pipeline-mode project.
 *
 * Three fields: project name, project path, stack profile. Profile list is
 * loaded from `GET /api/profiles` via TanStack Query. Submission posts to
 * `POST /api/projects/pipeline`, which writes shipwright_run_config.json,
 * registers the project, and spawns the initial `project` phase task.
 */
export function NewPipelineModal({ open, onOpenChange }: NewPipelineModalProps) {
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [path, setPath] = useState('');
  const [profile, setProfile] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const { data: profiles = [], isLoading: profilesLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => apiFetch<ProfileSummary[]>('/profiles'),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });

  // Default profile selection once list arrives
  useEffect(() => {
    if (open && !profile && profiles.length > 0) {
      setProfile(profiles[0].name);
    }
  }, [open, profile, profiles]);

  // Reset state on close
  useEffect(() => {
    if (!open) {
      setName('');
      setPath('');
      setProfile('');
      setErrorMessage(null);
    } else {
      setTimeout(() => nameRef.current?.focus(), 50);
    }
  }, [open]);

  const mutation = useMutation({
    mutationFn: (params: CreatePipelineParams) =>
      apiPost<CreatePipelineResponse>('/projects/pipeline', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setErrorMessage(err.error || 'Project already exists at this path.');
        } else if (err.status === 400) {
          setErrorMessage(err.error || 'Invalid input.');
        } else {
          setErrorMessage(err.error || 'Failed to create pipeline.');
        }
      } else {
        setErrorMessage('Unexpected error creating pipeline.');
      }
    },
  });

  function handleSubmit() {
    setErrorMessage(null);
    if (!name.trim() || !path.trim() || !profile) return;
    mutation.mutate({ name: name.trim(), path: path.trim(), profile });
  }

  // Iterate 14.7.1 — clipboard-paste helper for the path field. Mirrors the
  // New Project wizard behaviour (see ProjectInfoStep) so the two forms stay
  // consistent. Non-path clipboard contents are ignored with an inline hint.
  async function handlePastePath() {
    const raw = await pasteFromClipboard();
    if (raw && looksLikePath(raw)) {
      setPath(raw.trim());
      setErrorMessage(null);
    } else {
      setErrorMessage("Clipboard doesn't look like a path — paste manually with Ctrl+V.");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 z-40" />
        <Dialog.Content
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-xl p-6 w-full max-w-[480px] z-50"
          onKeyDown={handleKeyDown}
        >
          <div className="flex items-center justify-between mb-4">
            <Dialog.Title className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Workflow size={18} />
              New Pipeline
            </Dialog.Title>
            <Dialog.Description className="sr-only">
              Register a new shipwright pipeline project
            </Dialog.Description>
            <Dialog.Close asChild>
              <button className="p-1 rounded hover:bg-gray-100" aria-label="Close">
                <X size={18} className="text-gray-400" />
              </button>
            </Dialog.Close>
          </div>

          <div className="mb-3">
            <label htmlFor="pipeline-name" className="block text-sm font-medium text-gray-700 mb-1">
              Project name
            </label>
            <input
              ref={nameRef}
              id="pipeline-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-app"
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
            />
          </div>

          <div className="mb-3">
            <label htmlFor="pipeline-path" className="block text-sm font-medium text-gray-700 mb-1">
              Project path
            </label>
            <div className="flex gap-2">
              <input
                id="pipeline-path"
                type="text"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/absolute/path/to/folder"
                className="flex-1 px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
              />
              <button
                type="button"
                onClick={handlePastePath}
                data-testid="pipeline-path-paste"
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-600 border border-[#e0dbd4] rounded-lg hover:bg-gray-50 transition-colors shrink-0"
              >
                <ClipboardPaste size={14} />
                Paste
              </button>
            </div>
          </div>

          <div className="mb-4">
            <label htmlFor="pipeline-profile" className="block text-sm font-medium text-gray-700 mb-1">
              Stack profile
            </label>
            <select
              id="pipeline-profile"
              value={profile}
              onChange={(e) => setProfile(e.target.value)}
              disabled={profilesLoading || profiles.length === 0}
              className="w-full px-3 py-2 border border-[#e0dbd4] rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20 focus:border-[var(--color-primary)]"
            >
              {profilesLoading && <option value="">Loading profiles…</option>}
              {!profilesLoading && profiles.length === 0 && (
                <option value="">No profiles available</option>
              )}
              {profiles.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label ?? p.name}
                </option>
              ))}
            </select>
            {profile && profiles.find((p) => p.name === profile)?.description && (
              <p className="text-xs text-gray-500 mt-1">
                {profiles.find((p) => p.name === profile)?.description}
              </p>
            )}
          </div>

          {errorMessage && (
            <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <Dialog.Close asChild>
              <button className="px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-lg">
                Cancel
              </button>
            </Dialog.Close>
            <button
              disabled={!name.trim() || !path.trim() || !profile || mutation.isPending}
              onClick={handleSubmit}
              className="px-4 py-2 text-sm font-semibold text-white bg-[var(--color-primary)] rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {mutation.isPending ? 'Creating…' : 'Create Pipeline'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
