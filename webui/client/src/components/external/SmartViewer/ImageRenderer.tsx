/*
 * ImageRenderer — lets the browser stream image bytes directly via the
 * file route (no JS copy). `onError` falls back to a broken-image chip
 * so a 415/413 on the server surfaces something actionable rather than a
 * silent blank square.
 */

import { useState } from "react";
import { ImageIcon } from "lucide-react";

import { fileUrl } from "../../../lib/externalApi";

interface Props {
  projectId: string;
  path: string;
}

export function ImageRenderer({ projectId, path }: Props) {
  const [broken, setBroken] = useState(false);
  const src = fileUrl(projectId, path);
  if (broken) {
    return (
      <div
        className="flex h-full flex-col items-center justify-center gap-2 p-6 text-[12px]"
        style={{ color: "var(--color-muted, #6b7280)" }}
        data-testid="smart-viewer-image-error"
      >
        <ImageIcon size={24} aria-hidden="true" />
        <span>Image could not be loaded.</span>
        <code className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[11px]">
          {path}
        </code>
      </div>
    );
  }
  return (
    <div
      className="flex h-full items-center justify-center overflow-auto p-4"
      style={{ background: "var(--color-surface, #ffffff)" }}
      data-testid="smart-viewer-image"
    >
      <img
        src={src}
        alt={path}
        onError={() => setBroken(true)}
        className="max-h-full max-w-full"
        style={{
          objectFit: "contain",
          borderRadius: "var(--radius-button, 8px)",
          boxShadow: "var(--shadow-sm, 0 2px 8px rgba(0,0,0,0.06))",
        }}
      />
    </div>
  );
}
