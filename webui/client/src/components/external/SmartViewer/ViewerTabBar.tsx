/*
 * ViewerTabBar — pill-style tab strip above the SmartViewer (iterate 3.7b,
 * Phase B3). Renders one tab per entry in `paths`; the `activePath` gets
 * a 2px `--color-primary` bottom border + surface background, inactive
 * tabs stay on the muted background with hover surface.
 *
 * Clicking a tab body: selects (activePath). Clicking the × button on a
 * tab: removes that path from the multi-file list via `onClose`. Close is
 * stopPropagation'd so it does not also trigger activate.
 *
 * Icon-by-extension is best-effort: uses the same lucide icon set as
 * FolderTree so the visual language is consistent.
 */

import {
  File as FileIcon,
  FileCode,
  FileJson,
  FileText,
  ImageIcon,
  X,
} from "lucide-react";

interface Props {
  paths: string[];
  activePath: string | null;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
}

function basename(path: string): string {
  const slash = path.lastIndexOf("/");
  return slash >= 0 ? path.slice(slash + 1) : path;
}

function iconFor(name: string) {
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  if (ext === "md" || ext === "markdown") {
    return <FileText size={12} className="shrink-0 text-[#2563EB]" />;
  }
  if (ext === "ts" || ext === "tsx" || ext === "js" || ext === "jsx") {
    return <FileCode size={12} className="shrink-0 text-[#2563EB]" />;
  }
  if (ext === "json" || ext === "yaml" || ext === "yml") {
    return <FileJson size={12} className="shrink-0 text-[#D97706]" />;
  }
  if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext)) {
    return <ImageIcon size={12} className="shrink-0 text-[#8B5CF6]" />;
  }
  if (ext === "mmd" || ext === "mermaid") {
    return <FileText size={12} className="shrink-0 text-[#059669]" />;
  }
  return (
    <FileIcon
      size={12}
      className="shrink-0 text-[var(--color-muted,#6b7280)]"
    />
  );
}

export function ViewerTabBar({ paths, activePath, onActivate, onClose }: Props) {
  if (paths.length === 0) return null;
  return (
    <div
      className="flex min-h-[40px] items-center overflow-x-auto border-b border-[var(--color-border,#e0dbd4)] bg-[var(--color-bg,#f5f0eb)] pr-2"
      data-testid="viewer-tab-bar"
      role="tablist"
    >
      {paths.map((p) => {
        const active = p === activePath;
        const name = basename(p);
        return (
          <button
            key={p}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onActivate(p)}
            data-testid={`viewer-tab-${p}`}
            data-active={active || undefined}
            className={`group flex min-h-[40px] shrink-0 items-center gap-2 whitespace-nowrap border-b-2 px-3 font-mono text-[12px] transition ${
              active
                ? "border-[var(--color-primary,#6b5e56)] bg-[var(--color-surface,#ffffff)] text-[var(--color-primary,#6b5e56)]"
                : "border-transparent text-[var(--color-muted,#6b7280)] hover:text-[var(--color-text,#1a1a1a)]"
            }`}
          >
            {iconFor(name)}
            <span className="truncate">{name}</span>
            <span
              role="button"
              tabIndex={-1}
              aria-label={`Close ${name}`}
              onClick={(e) => {
                e.stopPropagation();
                onClose(p);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  onClose(p);
                }
              }}
              data-testid={`viewer-tab-close-${p}`}
              className="flex h-[14px] w-[14px] items-center justify-center rounded-[3px] opacity-0 transition hover:bg-[var(--color-muted-bg,#ede8e1)] group-hover:opacity-60 hover:!opacity-100"
            >
              <X size={8} className="text-[var(--color-muted,#6b7280)]" />
            </span>
          </button>
        );
      })}
    </div>
  );
}
