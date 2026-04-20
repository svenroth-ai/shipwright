/*
 * Delete-task confirmation modal.
 *
 * Plan calls for an inline confirm when the task is `active`, `idle`,
 * or `awaiting_external_start` (anything that might have a live CLI
 * process attached). For `draft` / `done` / `jsonl_missing` /
 * `launch_failed` the caller skips this dialog and deletes directly.
 *
 * Copy mirrors the plan exactly: webui stops tracking; the user's
 * terminal session is unaffected.
 */

import * as Dialog from "@radix-ui/react-dialog";

import type { ExternalTask } from "../../lib/externalApi";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: ExternalTask;
  onConfirm: () => void;
}

export function ConfirmDeleteDialog({ open, onOpenChange, task, onConfirm }: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-neutral-200 bg-white p-4 shadow-xl"
          data-testid="confirm-delete-dialog"
        >
          <Dialog.Title className="text-base font-semibold text-neutral-900">
            Delete task?
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-neutral-700">
            <span className="font-medium">{task.title}</span> is currently{" "}
            <span className="font-mono text-xs">{task.state}</span>. The CLI may still be
            running in your terminal — webui stops tracking it, the terminal session
            continues. Files on disk are not deleted; only the webui registry entry.
          </Dialog.Description>
          <div className="mt-4 flex justify-end gap-2">
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded border border-neutral-300 bg-white px-3 py-1 text-sm text-neutral-800 hover:bg-neutral-50"
                data-testid="confirm-delete-cancel"
              >
                Cancel
              </button>
            </Dialog.Close>
            <button
              type="button"
              onClick={onConfirm}
              className="rounded bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-500"
              data-testid="confirm-delete-confirm"
            >
              Delete
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
