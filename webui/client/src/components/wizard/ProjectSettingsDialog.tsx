/*
 * Iterate 3.7e-b3 (2026-04-22) — Project Settings dialog.
 *
 * Opens from the gear icon in the Projects table row. Lets the user
 * rename the project and pick a color. Path is displayed read-only
 * (changing the project path is destructive — Shipwright plugin chain
 * reads this from shipwright_run_config.json and changing it would
 * orphan an existing JSONL in ~/.claude/projects; user can unregister
 * + re-register via the wizard).
 *
 * Submit = PATCH /api/projects/:id { name, settings: { color } }.
 * Server deep-merges settings (see project-manager.ts update()).
 *
 * On error: inline red banner with role="alert"; dialog stays open
 * so the user can edit + retry.
 *
 * Testids:
 *   project-settings-dialog     — root
 *   project-settings-name       — name input
 *   project-settings-path       — path (read-only) display
 *   project-settings-color-<v>  — swatches (delegated to ProjectColorPicker)
 *   project-settings-save       — submit button
 *   project-settings-cancel     — cancel button
 *   project-settings-error      — inline error banner (role="alert")
 */
import { useEffect, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { useUpdateProject } from '../../hooks/useUpdateProject';
import { ProjectColorPicker } from './ProjectColorPicker';
import type { Project } from '../../types';

interface ProjectSettingsDialogProps {
  project: Project | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ProjectSettingsDialog({
  project,
  open,
  onOpenChange,
}: ProjectSettingsDialogProps) {
  const [name, setName] = useState('');
  const [color, setColor] = useState<string | null>(null);
  const updateProject = useUpdateProject();

  // Re-seed local state every time the dialog is opened with a new project.
  useEffect(() => {
    if (open && project) {
      setName(project.name);
      setColor(project.settings?.color ?? null);
      updateProject.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, project?.id]);

  if (!project) return null;

  const canSubmit = name.trim().length > 0 && !updateProject.isPending;

  async function handleSave() {
    if (!project || !canSubmit) return;
    try {
      await updateProject.mutateAsync({
        id: project.id,
        patch: {
          name: name.trim(),
          // Explicit null → clear custom color (Auto). Settings payload
          // is merged server-side so this only touches `color`.
          settings: { color: color ?? undefined },
        },
      });
      onOpenChange(false);
    } catch {
      // Error surfaced via updateProject.error — banner is already
      // rendered. Keep the dialog open so the user can edit + retry.
    }
  }

  const errorMessage =
    updateProject.error instanceof Error
      ? updateProject.error.message
      : updateProject.error
        ? String(updateProject.error)
        : null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-[4px] z-40" />
        <Dialog.Content
          data-testid="project-settings-dialog"
          className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[var(--color-surface)] rounded-[var(--radius-card)] shadow-[var(--shadow-card)] w-full max-w-[520px] max-h-[90vh] overflow-hidden flex flex-col z-50"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-7 pt-6">
            <Dialog.Title className="text-xl font-semibold text-[var(--color-text)] tracking-tight">
              Project Settings
            </Dialog.Title>
            <Dialog.Description className="sr-only">
              Edit project name and color
            </Dialog.Description>
            <Dialog.Close asChild>
              <button
                className="w-8 h-8 flex items-center justify-center rounded-md text-[var(--color-muted)] hover:bg-[var(--color-muted-bg)] hover:text-[var(--color-text)] transition-colors"
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="px-7 py-6 flex-1 overflow-y-auto space-y-5">
            {/* Error banner (inline, role=alert) */}
            {errorMessage && (
              <div
                data-testid="project-settings-error"
                role="alert"
                className="rounded-[var(--radius-button)] border px-4 py-3 text-[13px]"
                style={{
                  background: 'var(--color-error-bg)',
                  borderColor: 'var(--color-error)',
                  color: 'var(--color-error)',
                }}
              >
                <strong className="font-semibold">Save failed:</strong>{' '}
                {errorMessage}
              </div>
            )}

            {/* Name */}
            <div>
              <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5 tracking-tight">
                Project Name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                data-testid="project-settings-name"
                placeholder="My Awesome App"
                className="w-full h-12 px-3.5 border-[1.5px] border-[var(--color-border)] rounded-[var(--radius-button)] text-sm text-[var(--color-text)] bg-[var(--color-surface)] placeholder:text-[#b0a99f] hover:border-[var(--color-accent)] focus:outline-none focus:border-[var(--color-primary)] focus:ring-[3px] focus:ring-[var(--color-primary)]/10 transition-colors"
              />
            </div>

            {/* Path (read-only) */}
            <div>
              <label className="block text-[13px] font-semibold text-[var(--color-text)] mb-1.5 tracking-tight">
                Project Directory
              </label>
              <div
                data-testid="project-settings-path"
                className="w-full h-12 px-3.5 flex items-center rounded-[var(--radius-button)] text-[13px] font-mono truncate"
                style={{
                  background: 'var(--color-muted-bg)',
                  border: '1.5px solid var(--color-border)',
                  color: 'var(--color-muted)',
                }}
                title={project.path}
              >
                {project.path}
              </div>
              <p className="text-xs text-[var(--color-muted)] mt-1.5">
                Path cannot be changed. Unregister and re-add the project to move it.
              </p>
            </div>

            {/* Color picker */}
            <ProjectColorPicker
              value={color}
              onChange={setColor}
              testidPrefix="project-settings-color"
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-2.5 px-7 pb-6">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              data-testid="project-settings-cancel"
              className="h-10 px-5 text-sm font-medium rounded-[var(--radius-button)] border-[1.5px] border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)] hover:bg-[var(--color-muted-bg)] hover:border-[var(--color-accent)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSubmit}
              data-testid="project-settings-save"
              className="h-10 px-5 text-sm font-medium rounded-[var(--radius-button)] bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] active:scale-[0.98] transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[var(--color-primary)]"
            >
              {updateProject.isPending ? 'Saving...' : 'Save'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
