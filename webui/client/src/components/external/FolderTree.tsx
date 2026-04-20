/*
 * FolderTree — left-pane of the TaskDetail 3-pane body (iterate 3
 * section 04, FR-03.32 + FR-03.33).
 *
 * Fetches ONE level at a time via GET /api/external/projects/:id/tree —
 * lazy expand; collapsing a dir DOES NOT refetch on the next expand
 * inside the same mount. Ignored entries render muted by default; the
 * "Hide ignored entries" toggle (unchecked by default) flips to hide
 * them entirely. Per-project persistence via `useHideIgnored`.
 *
 * Keyboard: ArrowDown / ArrowUp focus next/prev row; ArrowRight on a
 * dir expands (or focuses first child if already expanded); ArrowLeft
 * collapses (or focuses parent); Enter selects.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ChevronRight,
  File as FileIcon,
  FileCode,
  FileJson,
  FileText,
  Folder,
  FolderOpen,
  ImageIcon,
  Loader2,
  RefreshCw,
} from "lucide-react";

import {
  ApiError,
  fetchProjectTree,
  type TreeEntry,
} from "../../lib/externalApi";
import { useHideIgnored } from "../../hooks/useHideIgnored";

interface Props {
  projectId: string;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

interface DirState {
  loading: boolean;
  error: string | null;
  entries: TreeEntry[] | null;
  expanded: boolean;
}

type DirCache = Record<string, DirState | undefined>;

const ROOT = "";

function joinPath(parent: string, name: string): string {
  if (!parent) return name;
  return `${parent}/${name}`;
}

function iconForEntry(name: string, kind: "file" | "dir", expanded: boolean) {
  if (kind === "dir") {
    return expanded ? (
      <FolderOpen size={14} className="shrink-0 text-[var(--color-accent,#857568)]" />
    ) : (
      <Folder size={14} className="shrink-0 text-[var(--color-accent,#857568)]" />
    );
  }
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  if (ext === "md" || ext === "markdown") {
    return <FileText size={14} className="shrink-0 text-[#2563EB]" />;
  }
  if (ext === "ts" || ext === "tsx" || ext === "js" || ext === "jsx") {
    return <FileCode size={14} className="shrink-0 text-[#2563EB]" />;
  }
  if (ext === "json" || ext === "yaml" || ext === "yml") {
    return <FileJson size={14} className="shrink-0 text-[#D97706]" />;
  }
  if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext)) {
    return <ImageIcon size={14} className="shrink-0 text-[#8B5CF6]" />;
  }
  return <FileIcon size={14} className="shrink-0 text-[var(--color-muted,#6b7280)]" />;
}

export function FolderTree({ projectId, selectedPath, onSelect }: Props) {
  const [cache, setCache] = useState<DirCache>({});
  const [hideIgnored, setHideIgnored] = useHideIgnored(projectId);
  const treeRef = useRef<HTMLDivElement | null>(null);
  const [focusedPath, setFocusedPath] = useState<string | null>(null);

  // Reset cache when project changes — different filesystem root.
  useEffect(() => {
    setCache({});
    setFocusedPath(null);
  }, [projectId]);

  const loadDir = useCallback(
    async (relpath: string) => {
      setCache((prev) => ({
        ...prev,
        [relpath]: {
          loading: true,
          error: null,
          entries: prev[relpath]?.entries ?? null,
          expanded: prev[relpath]?.expanded ?? true,
        },
      }));
      try {
        const res = await fetchProjectTree(projectId, relpath || undefined);
        setCache((prev) => ({
          ...prev,
          [relpath]: {
            loading: false,
            error: null,
            entries: res.entries,
            expanded: true,
          },
        }));
      } catch (err) {
        const msg = err instanceof ApiError ? err.code : err instanceof Error ? err.message : String(err);
        setCache((prev) => ({
          ...prev,
          [relpath]: {
            loading: false,
            error: msg,
            entries: prev[relpath]?.entries ?? null,
            expanded: prev[relpath]?.expanded ?? false,
          },
        }));
      }
    },
    [projectId],
  );

  // Load root on mount / projectId change.
  useEffect(() => {
    if (!cache[ROOT]) {
      void loadDir(ROOT);
    }
  }, [cache, loadDir]);

  const refreshTree = useCallback(() => {
    // Drop the whole cache so every level reloads fresh from the server.
    setCache({});
    void loadDir(ROOT);
  }, [loadDir]);

  const toggleDir = useCallback(
    (path: string) => {
      setCache((prev) => {
        const cur = prev[path];
        if (cur && cur.entries) {
          return {
            ...prev,
            [path]: { ...cur, expanded: !cur.expanded },
          };
        }
        return prev;
      });
      // If no entries yet: fetch.
      const cur = cache[path];
      if (!cur || cur.entries === null) {
        void loadDir(path);
      }
    },
    [cache, loadDir],
  );

  const rootState = cache[ROOT];

  // Flatten for keyboard navigation. Rebuild whenever cache or toggle
  // changes so ArrowDown/Up moves through what's visible.
  const visibleRows = useMemo(() => {
    const rows: Array<{
      path: string;
      name: string;
      kind: "file" | "dir";
      ignored: boolean;
      depth: number;
      expanded: boolean;
    }> = [];
    const walk = (parentPath: string, depth: number) => {
      const state = cache[parentPath];
      if (!state || !state.entries) return;
      for (const e of state.entries) {
        if (hideIgnored && e.ignored) continue;
        const p = joinPath(parentPath, e.name);
        const child = cache[p];
        const expanded = Boolean(child?.expanded);
        rows.push({
          path: p,
          name: e.name,
          kind: e.kind,
          ignored: e.ignored,
          depth,
          expanded,
        });
        if (e.kind === "dir" && expanded) {
          walk(p, depth + 1);
        }
      }
    };
    walk(ROOT, 0);
    return rows;
  }, [cache, hideIgnored]);

  const onRowKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    row: (typeof visibleRows)[number],
  ) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const idx = visibleRows.findIndex((r) => r.path === row.path);
      const next = visibleRows[idx + 1];
      if (next) {
        setFocusedPath(next.path);
        focusRow(treeRef.current, next.path);
      }
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      const idx = visibleRows.findIndex((r) => r.path === row.path);
      const prev = visibleRows[idx - 1];
      if (prev) {
        setFocusedPath(prev.path);
        focusRow(treeRef.current, prev.path);
      }
      return;
    }
    if (e.key === "ArrowRight" && row.kind === "dir") {
      e.preventDefault();
      if (!row.expanded) toggleDir(row.path);
      return;
    }
    if (e.key === "ArrowLeft" && row.kind === "dir" && row.expanded) {
      e.preventDefault();
      toggleDir(row.path);
      return;
    }
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (row.kind === "dir") toggleDir(row.path);
      else onSelect(row.path);
      return;
    }
  };

  return (
    <div
      className="flex h-full flex-col border-r border-[var(--color-border,#e0dbd4)]"
      style={{ background: "var(--color-surface, #ffffff)" }}
      data-testid="folder-tree"
    >
      <div
        className="flex items-center gap-1 border-b border-[var(--color-border,#e0dbd4)] px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: "var(--color-muted, #6b7280)", background: "var(--color-bg, #f5f0eb)" }}
        data-testid="folder-tree-header"
      >
        <span className="flex-1">Files</span>
        {rootState?.loading && (
          <Loader2 size={12} className="animate-spin" aria-label="Loading" />
        )}
        <button
          type="button"
          onClick={refreshTree}
          className="inline-flex h-6 w-6 items-center justify-center rounded-[6px] text-[var(--color-muted,#6b7280)] transition hover:bg-[var(--color-muted-bg,#ede8e1)] hover:text-[var(--color-text,#1a1a1a)]"
          title="Refresh tree"
          aria-label="Refresh tree"
          data-testid="folder-tree-refresh"
        >
          <RefreshCw size={12} aria-hidden="true" />
        </button>
      </div>
      <div
        ref={treeRef}
        role="tree"
        aria-label="Project files"
        className="flex-1 overflow-y-auto py-2"
        data-testid="folder-tree-body"
      >
        {rootState?.error && (
          <div
            className="mx-2 mb-2 rounded-md border border-[var(--color-error,#DC2626)]/30 bg-[var(--color-error,#DC2626)]/10 px-2 py-1.5 text-[11px]"
            style={{ color: "var(--color-error, #DC2626)" }}
            data-testid="folder-tree-error"
          >
            <AlertCircle size={12} className="mr-1 inline" />
            {rootState.error}
          </div>
        )}
        {visibleRows.map((row) => {
          const childState = cache[row.path];
          const isSelected = selectedPath === row.path;
          return (
            <div key={row.path} role="treeitem" aria-selected={isSelected}>
              <button
                type="button"
                onClick={() => {
                  setFocusedPath(row.path);
                  if (row.kind === "dir") toggleDir(row.path);
                  else onSelect(row.path);
                }}
                onKeyDown={(e) => onRowKeyDown(e, row)}
                data-testid={`folder-tree-row-${row.path}`}
                data-path={row.path}
                data-ignored={row.ignored || undefined}
                data-kind={row.kind}
                data-selected={isSelected || undefined}
                tabIndex={row.path === (focusedPath ?? visibleRows[0]?.path) ? 0 : -1}
                className={`flex w-full items-center gap-1 truncate rounded-sm px-1.5 py-0.5 text-left text-[12px] transition ${
                  row.ignored ? "opacity-60" : ""
                } ${
                  isSelected
                    ? "bg-[var(--color-primary,#6b5e56)]/15 font-medium"
                    : "hover:bg-[var(--color-muted-bg,#ede8e1)]"
                }`}
                style={{ paddingLeft: `${8 + row.depth * 14}px` }}
              >
                <span className="flex w-3 shrink-0 items-center justify-center">
                  {row.kind === "dir" ? (
                    <ChevronRight
                      size={12}
                      className="transition-transform"
                      style={{ transform: row.expanded ? "rotate(90deg)" : "none" }}
                    />
                  ) : (
                    <span aria-hidden="true" className="inline-block h-3 w-3" />
                  )}
                </span>
                {iconForEntry(row.name, row.kind, row.expanded)}
                <span className="truncate">{row.name}</span>
                {row.kind === "dir" && childState?.loading && (
                  <Loader2 size={10} className="ml-auto animate-spin opacity-60" />
                )}
              </button>
              {row.kind === "dir" && childState?.error && (
                <div
                  className="ml-8 mr-2 my-1 rounded-sm border border-[var(--color-error,#DC2626)]/30 bg-[var(--color-error,#DC2626)]/10 px-1.5 py-0.5 text-[10px]"
                  style={{ color: "var(--color-error, #DC2626)" }}
                  data-testid={`folder-tree-error-${row.path}`}
                >
                  {childState.error}
                </div>
              )}
            </div>
          );
        })}
        {rootState && !rootState.loading && visibleRows.length === 0 && !rootState.error && (
          <div
            className="px-4 py-3 text-[11px] italic"
            style={{ color: "var(--color-muted, #6b7280)" }}
            data-testid="folder-tree-empty"
          >
            No files to show.
          </div>
        )}
      </div>
      <label
        className="flex items-center gap-2 border-t border-[var(--color-border,#e0dbd4)] px-4 py-2 text-[11px] select-none"
        style={{ color: "var(--color-muted, #6b7280)" }}
        data-testid="folder-tree-hide-ignored-label"
      >
        <input
          type="checkbox"
          checked={hideIgnored}
          onChange={(e) => setHideIgnored(e.target.checked)}
          className="h-3 w-3 cursor-pointer"
          data-testid="folder-tree-hide-ignored-toggle"
        />
        <span className="cursor-pointer">Hide ignored entries</span>
        <span
          className="ml-auto text-[10px] italic opacity-70"
          data-testid="folder-tree-saved-hint"
        >
          saved per project
        </span>
      </label>
    </div>
  );
}

function focusRow(root: HTMLElement | null, path: string) {
  if (!root) return;
  const btn = root.querySelector<HTMLButtonElement>(
    `[data-testid="folder-tree-row-${CSS.escape(path)}"]`,
  );
  btn?.focus();
}
