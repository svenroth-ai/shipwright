/*
 * AttachmentCard — 2026-04-23 iterate-20260423-chat-rendering-polish AC-4.
 *
 * Renders `.attachment-card` per mockup bubble-states.html §Attachments.
 * Receives pre-sanitized basenames (parser strips paths — no full-path
 * leak). For multi-file snapshots, caller passes the first basename and
 * the extraCount suffix renders as `+N more`.
 *
 * Non-interactive for now — SmartViewer wire-up from click is deferred
 * (documented in iterate spec). When wired later, the outer wrapper
 * becomes a button and the whole card gains hover state.
 *
 * Security: `basename` rendered as React text node only. Mime-icon
 * selection uses a closed extension map (string lookup), never raw
 * filename interpolation into classNames.
 */

import {
  FileCode2,
  FileImage,
  FileText,
  FileIcon,
} from "lucide-react";

interface Props {
  basename: string;
  /** When > 0, renders `+N more` next to the filename (multi-file snapshot). */
  extraCount?: number;
}

type IconKind = "code" | "image" | "doc" | "generic";

const EXT_TO_KIND: Record<string, IconKind> = {
  ts: "code", tsx: "code", js: "code", jsx: "code",
  mjs: "code", cjs: "code", py: "code", rb: "code",
  go: "code", rs: "code", java: "code", kt: "code",
  c: "code", h: "code", cpp: "code", hpp: "code",
  json: "code", yaml: "code", yml: "code", toml: "code",
  sh: "code", bash: "code", zsh: "code", sql: "code",
  html: "code", xml: "code", css: "code",
  md: "doc", markdown: "doc", mmd: "doc", mermaid: "doc",
  txt: "doc", log: "doc", csv: "doc",
  png: "image", jpg: "image", jpeg: "image",
  gif: "image", svg: "image", webp: "image",
};

function kindFor(basename: string): IconKind {
  const dot = basename.lastIndexOf(".");
  if (dot < 0) return "generic";
  const ext = basename.slice(dot + 1).toLowerCase();
  return EXT_TO_KIND[ext] ?? "generic";
}

function iconFor(kind: IconKind) {
  if (kind === "code") return <FileCode2 size={18} aria-hidden="true" />;
  if (kind === "image") return <FileImage size={18} aria-hidden="true" />;
  if (kind === "doc") return <FileText size={18} aria-hidden="true" />;
  return <FileIcon size={18} aria-hidden="true" />;
}

export function AttachmentCard({ basename, extraCount = 0 }: Props) {
  const kind = kindFor(basename);
  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2 rounded-[8px] my-1.5"
      style={{
        background: "var(--color-surface, #ffffff)",
        border: "1px solid var(--color-border, #e0dbd4)",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        maxWidth: 380,
      }}
      data-testid="attachment-card"
    >
      <div
        className="flex items-center justify-center rounded-md shrink-0"
        style={{
          width: 36,
          height: 36,
          background: "linear-gradient(135deg, #F3E8FF, #DDD6FE)",
          color: "#7C3AED",
        }}
      >
        {iconFor(kind)}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className="font-mono text-[12px] truncate"
          style={{ color: "var(--color-text, #1a1a1a)" }}
          data-testid="attachment-basename"
        >
          {basename}
        </div>
        {extraCount > 0 && (
          <div
            className="text-[11px] mt-0.5"
            style={{ color: "var(--color-muted, #6b7280)" }}
            data-testid="attachment-extra-count"
          >
            +{extraCount} more
          </div>
        )}
      </div>
    </div>
  );
}
