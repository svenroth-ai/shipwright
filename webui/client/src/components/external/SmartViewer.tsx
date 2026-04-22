/*
 * SmartViewer — right-pane of the TaskDetail 3-pane body (iterate 3
 * section 04, FR-03.34).
 *
 * Extension dispatch:
 *   .md / .markdown   → MarkdownRenderer
 *   .mmd / .mermaid   → MermaidRenderer (lazy-imported)
 *   .png .jpg .jpeg .gif .svg .webp → ImageRenderer (browser-streamed)
 *   known-code exts   → CodeRenderer (rehype-highlight common bundle)
 *   everything else   → TextRenderer
 *
 * Client-side cap: text/markdown/code files > 1 MB render the
 * "File too large to preview inline" chip instead of calling into
 * react-markdown / rehype-highlight (plan § 7 G4 + O33). Images use the
 * server's 5 MB budget directly.
 */

import { useEffect, useState } from "react";
import {
  AlertCircle,
  ChevronRight,
  FileQuestion,
  FileText,
  Folder,
} from "lucide-react";

import {
  CLIENT_FILE_TEXT_MAX_BYTES,
  FileTooLargeError,
  fetchFileText,
  ApiError,
} from "../../lib/externalApi";
import { MarkdownRenderer } from "./SmartViewer/MarkdownRenderer";
import { CodeRenderer } from "./SmartViewer/CodeRenderer";
import { TextRenderer } from "./SmartViewer/TextRenderer";
import { ImageRenderer } from "./SmartViewer/ImageRenderer";
import { MermaidRenderer } from "./SmartViewer/MermaidRenderer";

export type SmartViewerKind = "markdown" | "code" | "text" | "image" | "mermaid" | "unknown";

const MARKDOWN_EXTS = new Set(["md", "markdown"]);
const MERMAID_EXTS = new Set(["mmd", "mermaid"]);
const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp"]);
const CODE_EXTS = new Set([
  "ts",
  "tsx",
  "js",
  "jsx",
  "mjs",
  "cjs",
  "py",
  "rb",
  "go",
  "rs",
  "java",
  "kt",
  "c",
  "h",
  "cpp",
  "hpp",
  "json",
  "yaml",
  "yml",
  "toml",
  "sh",
  "bash",
  "zsh",
  "sql",
  "html",
  "xml",
  "css",
]);

export function resolveKind(path: string): { kind: SmartViewerKind; ext: string } {
  const dot = path.lastIndexOf(".");
  const ext = dot >= 0 ? path.slice(dot + 1).toLowerCase() : "";
  if (MARKDOWN_EXTS.has(ext)) return { kind: "markdown", ext };
  if (MERMAID_EXTS.has(ext)) return { kind: "mermaid", ext };
  if (IMAGE_EXTS.has(ext)) return { kind: "image", ext };
  if (CODE_EXTS.has(ext)) return { kind: "code", ext };
  if (ext === "txt" || ext === "log" || ext === "csv" || ext === "env" || ext === "gitignore") {
    return { kind: "text", ext };
  }
  return { kind: "unknown", ext };
}

interface Props {
  projectId: string;
  /** Project-root-relative POSIX path; null = empty state. */
  path: string | null;
}

export function SmartViewer({ projectId, path }: Props) {
  if (!path) {
    return (
      <div
        className="flex h-full items-center justify-center p-6"
        data-testid="smart-viewer-empty"
      >
        <div
          className="flex flex-col items-center gap-2 text-[12px]"
          style={{ color: "var(--color-muted, #6b7280)" }}
        >
          <FileText size={24} aria-hidden="true" />
          <span>Select a file from the tree to preview.</span>
        </div>
      </div>
    );
  }

  const { kind, ext } = resolveKind(path);

  if (kind === "image") {
    return (
      <div
        className="flex h-full flex-col"
        data-testid="smart-viewer"
      >
        <PathStrip path={path} size={null} />
        <div className="min-h-0 flex-1">
          <ImageRenderer projectId={projectId} path={path} />
        </div>
      </div>
    );
  }

  if (kind === "unknown") {
    return (
      <div
        className="flex h-full flex-col"
        data-testid="smart-viewer"
      >
        <PathStrip path={path} size={null} />
        <div
          className="flex flex-1 items-center justify-center p-6 text-[12px]"
          style={{ color: "var(--color-muted, #6b7280)" }}
          data-testid="smart-viewer-unknown"
        >
          <div className="flex flex-col items-center gap-2">
            <FileQuestion size={24} aria-hidden="true" />
            <span>Unsupported file type ({ext || "no extension"}).</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <TextFileViewer projectId={projectId} path={path} kind={kind} ext={ext} />
  );
}

/**
 * Path breadcrumb strip shown below the tab bar. Renders folder segments
 * separated by chevrons so the user can see where the file lives inside
 * the project. When `size` is known (a text file has finished loading)
 * it renders the size badge next to the path.
 */
function PathStrip({ path, size }: { path: string; size: number | null }) {
  const segments = path.split("/").filter(Boolean);
  return (
    <div
      className="flex min-h-[26px] items-center gap-1.5 border-b border-[var(--color-border,#e0dbd4)] px-4 py-1 font-mono text-[11px] text-[var(--color-muted,#6b7280)]"
      data-testid="smart-viewer-path-strip"
    >
      <Folder
        size={11}
        className="shrink-0 text-[var(--color-accent,#857568)]"
        aria-hidden="true"
      />
      {segments.map((seg, i) => (
        <span key={`${seg}-${i}`} className="inline-flex items-center gap-1.5">
          <span className="truncate">{seg}</span>
          {i < segments.length - 1 && (
            <ChevronRight
              size={10}
              aria-hidden="true"
              className="opacity-50"
            />
          )}
        </span>
      ))}
      {size !== null && (
        <span
          className="ml-2 inline-flex items-center rounded-[3px] bg-[var(--color-muted-bg,#ede8e1)] px-1.5 py-[1px] text-[10px] font-semibold text-[var(--color-muted,#6b7280)]"
          data-testid="smart-viewer-size-badge"
        >
          {formatBytes(size)}
        </span>
      )}
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

interface TextProps {
  projectId: string;
  path: string;
  kind: Exclude<SmartViewerKind, "image" | "unknown">;
  ext: string;
}

function TextFileViewer({ projectId, path, kind, ext }: TextProps) {
  const [state, setState] = useState<
    | { status: "loading" }
    | { status: "ok"; text: string; size: number }
    | { status: "too_large"; maxBytes: number; source: "server" | "client" }
    | { status: "error"; message: string }
  >({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetchFileText(projectId, path)
      .then((res) => {
        if (cancelled) return;
        setState({ status: "ok", text: res.text, size: res.size });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof FileTooLargeError) {
          setState({
            status: "too_large",
            maxBytes: err.maxBytes,
            source: err.source,
          });
          return;
        }
        if (err instanceof ApiError) {
          setState({ status: "error", message: err.code });
          return;
        }
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, path]);

  const size = state.status === "ok" ? state.size : null;

  const inner = (() => {
    if (state.status === "loading") {
      return (
        <div
          className="flex h-full items-center justify-center p-6 text-[12px]"
          style={{ color: "var(--color-muted, #6b7280)" }}
          data-testid="smart-viewer-loading"
        >
          Loading…
        </div>
      );
    }
    if (state.status === "too_large") {
      const mb = (state.maxBytes / (1024 * 1024)).toFixed(1);
      return (
        <div
          className="flex h-full items-center justify-center p-6"
          data-testid="smart-viewer-too-large"
        >
          <div
            className="flex max-w-md flex-col items-start gap-2 rounded-md border border-[var(--color-border,#e0dbd4)] bg-[var(--color-muted-bg,#ede8e1)] p-4 text-[12px]"
            style={{ color: "var(--color-text, #1a1a1a)" }}
          >
            <div className="flex items-center gap-2 font-medium">
              <AlertCircle
                size={14}
                style={{ color: "var(--color-warning, #D97706)" }}
                aria-hidden="true"
              />
              File too large to preview inline
            </div>
            <div style={{ color: "var(--color-muted, #6b7280)" }}>
              {state.source === "client"
                ? `Preview cap is ${mb} MB for text / markdown / code.`
                : `Server cap is ${mb} MB.`}
            </div>
            <code className="max-w-full overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[11px]">
              {path}
            </code>
          </div>
        </div>
      );
    }
    if (state.status === "error") {
      return (
        <div
          className="flex h-full items-center justify-center p-6 text-[12px]"
          style={{ color: "var(--color-error, #DC2626)" }}
          data-testid="smart-viewer-error"
        >
          <div className="flex flex-col items-center gap-2">
            <AlertCircle size={20} aria-hidden="true" />
            <span>Failed to load file: {state.message}</span>
          </div>
        </div>
      );
    }
    if (kind === "markdown") return <MarkdownRenderer text={state.text} />;
    if (kind === "code") return <CodeRenderer text={state.text} extension={ext} />;
    if (kind === "mermaid") return <MermaidRenderer text={state.text} />;
    return <TextRenderer text={state.text} />;
  })();

  return (
    <div className="flex h-full flex-col" data-testid="smart-viewer">
      <PathStrip path={path} size={size} />
      <div className="min-h-0 flex-1 overflow-hidden">{inner}</div>
    </div>
  );
}

export { CLIENT_FILE_TEXT_MAX_BYTES };
