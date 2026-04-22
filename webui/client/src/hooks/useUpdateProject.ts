/*
 * Iterate 3.7e-b3 (2026-04-22) — generic PATCH hook for projects.
 *
 * Used by the ProjectSettingsDialog to update name + settings.color in
 * one round trip. Mirrors useCreateProject's structure so both hooks
 * share the same error-surface UX (the caller reads `mutation.error`
 * and renders a banner).
 *
 * Server merges `settings` (as of 3.7e-b3) so partial patches like
 * `{ settings: { color } }` no longer clobber other settings keys
 * (phaseToStatusMapping, autonomy, envVars, claudePluginDirs).
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPatch } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { Project, ProjectSettings } from '../types';

interface UpdateProjectParams {
  id: string;
  patch: {
    name?: string;
    settings?: Partial<ProjectSettings>;
  };
}

export function useUpdateProject() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, patch }: UpdateProjectParams) =>
      apiPatch<Project>(`/projects/${id}`, patch),
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.detail(vars.id),
      });
    },
  });
}
