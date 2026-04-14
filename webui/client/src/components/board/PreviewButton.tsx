import { Play } from 'lucide-react';
import { useState } from 'react';

/**
 * Iterate 14.1 — Preview button in the KanbanPage header.
 *
 * Only rendered when `activeProject.hasPreview === true` (derived
 * server-side from the project's profile.dev_server.command).
 *
 * Click → POST /api/projects/:id/preview → server spawns /shipwright-preview
 * as a background task via the usual governor/eventStore path. Response
 * arrives immediately with 202 + { taskId }; the dev-server URL lands in
 * chat output over SSE, same as any other task.
 */
interface PreviewButtonProps {
  projectId: string;
}

export function PreviewButton({ projectId }: PreviewButtonProps) {
  const [starting, setStarting] = useState(false);

  async function onClick() {
    if (starting) return;
    setStarting(true);
    try {
      const res = await fetch(`/api/projects/${projectId}/preview`, { method: 'POST' });
      if (!res.ok) {
        console.error('Preview start failed', res.status, await res.text().catch(() => ''));
      }
    } catch (err) {
      console.error('Preview start failed', err);
    } finally {
      // Brief UI lock — the server returns 202 instantly, so the disabled
      // state is only there to prevent double-clicks. No polling for ready.
      setStarting(false);
    }
  }

  return (
    <button
      onClick={onClick}
      disabled={starting}
      title={starting ? 'Dev server starting…' : 'Start preview'}
      className="flex items-center gap-1.5 px-4 py-[7px] rounded-lg text-[13px] font-semibold text-[var(--color-primary)] bg-white border border-[var(--color-border,#e0dbd4)] hover:bg-gray-50 hover:shadow-sm transition-all cursor-pointer whitespace-nowrap disabled:opacity-60 disabled:cursor-not-allowed"
    >
      <Play size={14} />
      Preview
    </button>
  );
}
