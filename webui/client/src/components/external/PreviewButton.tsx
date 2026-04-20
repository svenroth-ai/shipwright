/*
 * Preview dev-server CTA rendered on the TaskBoard header when the
 * project's resolved actions declare `preview.enabled === true`.
 *
 * Iterate 3 section 03 / FR-03.80..82. Phase B1 restyle (2026-04-20):
 *   - blue-info palette (text + border + hover bg) per mockup .btn-preview
 *     (lines 248–268 of kanban-with-projects.html).
 *   - 8px pulsing dot indicator when `loading` (a running dev-server spawn)
 *     via the `pulse-preview-dot` keyframes defined inline.
 *
 * Error handling is unchanged from section 03:
 *   - POST /api/external/projects/:id/preview
 *   - On success → open the returned url in a new tab.
 *   - On failure → map the 5 structured codes to specific toast copies.
 *     UI strings live here (the decoder in externalApi.ts is string-free
 *     per O11).
 */

import { useState } from "react";
import { Loader2 } from "lucide-react";

import { startPreview, PreviewApiError, ApiError } from "../../lib/externalApi";

interface PreviewButtonProps {
  projectId: string | null;
  /** Server-materialized preview.enabled flag. When false we render null. */
  enabled: boolean;
  /** Ready-timeout seconds from actions.preview — surfaced in the timeout toast. */
  readyTimeoutSeconds?: number | null;
  /** Injected for tests — default uses window.alert as a stand-in toast. */
  onToast?: (message: string, severity: "info" | "error") => void;
  /** Injected for tests — default calls window.open. */
  onOpenUrl?: (url: string) => void;
}

export function PreviewButton({
  projectId,
  enabled,
  readyTimeoutSeconds,
  onToast = (m, sev) => {
    if (typeof window !== "undefined") {
      // Minimal fallback — real toast integration lands when the common toast
      // surface ships. Keeping this here prevents the button from vanishing
      // silently in the meantime.
      if (sev === "error") console.error(m);
      else console.log(m);
      window.alert(m);
    }
  },
  onOpenUrl = (url) => {
    if (typeof window !== "undefined") {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  },
}: PreviewButtonProps) {
  const [loading, setLoading] = useState(false);

  if (!enabled) return null;

  const onClick = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const { url } = await startPreview(projectId);
      onOpenUrl(url);
    } catch (err) {
      const msg = previewErrorToToast(err, { readyTimeoutSeconds });
      onToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {/* Inline keyframes — scoped to this component so the global index.css
         stays Phase-A-authoritative (per B1 scope rules). */}
      <style>{`
        @keyframes pulse-preview-dot {
          0%, 100% { opacity: 1; }
          50%      { opacity: 0.4; }
        }
      `}</style>
      <button
        type="button"
        onClick={() => void onClick()}
        disabled={loading || !projectId}
        data-testid="preview-button"
        title="Spawn dev server for this project (npm run dev)"
        className="inline-flex items-center gap-1.5 rounded-[var(--radius-button)] border-[1.5px] border-[#bfdbfe] bg-[var(--color-surface)] px-3 py-1.5 text-[13px] font-medium text-[var(--color-info)] transition-colors hover:border-[#93c5fd] hover:bg-[var(--color-info-bg)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? (
          <Loader2 size={12} className="animate-spin" />
        ) : (
          <span
            aria-hidden="true"
            className="inline-block h-2 w-2 rounded-full bg-[var(--color-info)]"
            style={{
              animation: "pulse-preview-dot 1.4s infinite",
            }}
          />
        )}
        {/* Globe / browser-window glyph per mockup — kept inline to avoid a
            lucide bundle import just for one icon. */}
        <svg
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-3.5 w-3.5"
          aria-hidden="true"
        >
          <circle cx="8" cy="8" r="6.5" />
          <ellipse cx="8" cy="8" rx="3" ry="6.5" />
          <line x1="1.5" y1="8" x2="14.5" y2="8" />
        </svg>
        <span>Preview</span>
      </button>
    </>
  );
}

/**
 * Map a thrown API error from `startPreview` to its final toast copy.
 * Exported for unit tests.
 */
export function previewErrorToToast(
  err: unknown,
  opts: { readyTimeoutSeconds?: number | null } = {},
): string {
  if (err instanceof PreviewApiError) {
    switch (err.code) {
      case "preview_spawn_failed":
        return "Couldn't start the dev server. Check `dev_server.command` in the project profile.";
      case "preview_port_in_use":
        return `Port ${err.port ?? "?"} is already in use. Stop the existing dev server and retry.`;
      case "preview_exited_early":
        return "The dev server exited immediately. Check the server logs in your terminal.";
      case "preview_timeout":
        return `The dev server didn't start within ${err.seconds ?? opts.readyTimeoutSeconds ?? "?"} s. The command may be slow or hanging.`;
      case "preview_profile_invalid":
        return "Project profile is incomplete. The dev_server.command field must be a single executable plus args, not a shell pipeline.";
      case "preview_unavailable":
        return "Preview is not available on this server build.";
      default:
        return `Preview failed: ${err.detail ?? err.code}`;
    }
  }
  if (err instanceof ApiError) {
    return `Preview failed: ${err.detail ?? err.code}`;
  }
  return "Preview failed — unknown error.";
}
