/*
 * In-place editable task title for TaskDetail header.
 *
 * Click → switches to text input. Enter saves; Escape cancels; blur saves.
 * Server PATCH validates length + characters (newlines rejected). On 409
 * (lock contention from a parallel writer), the surfaced error tells the
 * user to retry — we deliberately do NOT auto-retry here, since that would
 * mask the conflict.
 *
 * The new title becomes the source of truth for the next launch's
 * `--name` flag (Claude CLI picker title). No mid-session sync.
 */

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { Pencil } from "lucide-react";

import type { ExternalTask } from "../../lib/externalApi";
import { useRenameTask } from "../../hooks/useExternalTasks";

interface Props {
  task: ExternalTask;
}

export interface EditableTaskTitleHandle {
  /** Imperatively enter edit mode (used by the header "Rename" menu item). */
  startEdit: () => void;
}

export const EditableTaskTitle = forwardRef<EditableTaskTitleHandle, Props>(
  function EditableTaskTitle({ task }, ref) {
  const renameMut = useRenameTask();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(task.title);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useImperativeHandle(
    ref,
    () => ({
      startEdit: () => setEditing(true),
    }),
    [],
  );

  useEffect(() => {
    if (!editing) setDraft(task.title);
  }, [task.title, editing]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commit = async () => {
    const trimmed = draft.trim();
    if (trimmed === "" || trimmed === task.title) {
      setEditing(false);
      setDraft(task.title);
      setError(null);
      return;
    }
    try {
      await renameMut.mutateAsync({ taskId: task.taskId, title: trimmed });
      setEditing(false);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        className="inline-flex items-center gap-2 text-left text-lg font-semibold text-neutral-900 hover:text-blue-700"
        aria-label="Edit task title"
        data-testid="task-title-display"
      >
        <span>{task.title}</span>
        <Pencil size={14} className="text-neutral-400" />
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-1" data-testid="task-title-editor">
      <input
        ref={inputRef}
        type="text"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void commit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            setEditing(false);
            setDraft(task.title);
            setError(null);
          }
        }}
        onBlur={() => void commit()}
        disabled={renameMut.isPending}
        maxLength={200}
        className="w-full border border-blue-400 bg-white px-2 py-1 text-lg font-semibold focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        style={{ borderRadius: "var(--radius-button)" }}
        data-testid="task-title-input-edit"
      />
      {error && (
        <span className="text-xs text-red-700" data-testid="task-title-error">
          {error}
        </span>
      )}
    </div>
  );
  },
);
