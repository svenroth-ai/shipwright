/*
 * Preview dev-server CTA rendered on the TaskBoard header when the
 * project's resolved actions declare `preview.enabled === true`.
 *
 * Iterate 3 section 03 / FR-03.80..82:
 *   - POST /api/external/projects/:id/preview
 *   - On success → open the returned url in a new tab.
 *   - On failure → map the 5 structured codes to specific toast copies.
 *     UI strings live here (the decoder in externalApi.ts is string-free
 *     per O11).
 *
 * Toast copies (matching spec § 12 implementation-steps bulletpoints):
 *   preview_spawn_failed      → "Couldn't start the dev server. Check …"
 *   preview_port_in_use       → "Port {port} is already in use. …"
 *   preview_exited_early      → "The dev server exited immediately. …"
 *   preview_timeout           → "The dev server didn't start within {s}s. …"
 *   preview_profile_invalid   → "Project profile is incomplete. …"
 */

import { useState } from "react";
import { ExternalLink, Loader2, Monitor } from "lucide-react";

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
    <button
      type="button"
      onClick={() => void onClick()}
      disabled={loading || !projectId}
      data-testid="preview-button"
      className="inline-flex items-center gap-1.5 rounded border border-[var(--color-border,#e0dbd4)] bg-white px-3 py-1.5 text-[13px] font-medium text-neutral-800 transition-colors hover:bg-[var(--color-muted-bg,#ede8e1)] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {loading ? (
        <Loader2 size={14} className="animate-spin" />
      ) : (
        <Monitor size={14} />
      )}
      Preview
      {!loading && <ExternalLink size={12} className="opacity-60" />}
    </button>
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
