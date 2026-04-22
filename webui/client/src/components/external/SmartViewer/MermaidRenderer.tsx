/*
 * MermaidRenderer — lazy-imports mermaid, content-hash memoizes the
 * render output, and disposes the previous render's DOM subtree on
 * re-render (plan § 7 O28 — naive re-init leaks element nodes + event
 * listeners).
 *
 * Lazy import: mermaid is ~1.5 MB. We `import("mermaid")` inside an
 * effect so Vite code-splits it into its own chunk. TaskDetail's entry
 * chunk stays small; users only pay for mermaid if they open a `.mmd`.
 */

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

interface Props {
  text: string;
  /** Optional override; falls back to `text` itself for memoisation. */
  contentHash?: string;
}

/**
 * Tiny non-cryptographic hash — FNV-1a-style, sufficient for memo keys.
 * We never use this for security, only for "did the content change".
 */
function hashSource(input: string): string {
  let hash = 0x811c9dc5;
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(16);
}

export function MermaidRenderer({ text, contentHash }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastHashRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let disposed = false;
    const hash = contentHash ?? hashSource(text);

    // Memo: same content-hash as last render → keep the existing SVG;
    // mermaid is expensive and identical input produces identical output.
    if (lastHashRef.current === hash && containerRef.current?.querySelector("svg")) {
      setLoading(false);
      return;
    }

    const el = containerRef.current;
    if (!el) return;

    // DISPOSE before re-init. mermaid stamps <style> blocks into <head>
    // and leaves orphan <svg> nodes behind on naive replace — detach
    // everything the previous render inserted into our container, then
    // let GC claim it.
    while (el.firstChild) el.removeChild(el.firstChild);
    setError(null);
    setLoading(true);

    const renderId = `mermaid-${hash}-${Date.now().toString(36)}`;
    void import("mermaid")
      .then(async (mod) => {
        if (disposed) return;
        const mermaid = mod.default;
        try {
          mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
          const { svg } = await mermaid.render(renderId, text);
          if (disposed || !containerRef.current) return;
          containerRef.current.innerHTML = svg;
          lastHashRef.current = hash;
          setLoading(false);
        } catch (err) {
          if (disposed) return;
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      })
      .catch((err) => {
        if (disposed) return;
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      });

    // Cleanup — component unmounting or text changing. Clears subtree
    // so mermaid's orphan nodes don't survive past us.
    return () => {
      disposed = true;
      const cur = containerRef.current;
      if (cur) {
        while (cur.firstChild) cur.removeChild(cur.firstChild);
      }
      lastHashRef.current = null;
    };
  }, [text, contentHash]);

  return (
    <div
      className="smart-viewer-mermaid h-full overflow-auto p-4"
      style={{ background: "var(--color-surface, #ffffff)" }}
      data-testid="smart-viewer-mermaid"
    >
      {loading && !error && (
        <div
          className="flex items-center gap-2 text-[12px]"
          style={{ color: "var(--color-muted, #6b7280)" }}
          data-testid="smart-viewer-mermaid-loading"
        >
          <Loader2 size={14} className="animate-spin" aria-hidden="true" />
          Rendering diagram…
        </div>
      )}
      {error && (
        <div
          className="rounded-md border border-[var(--color-error,#DC2626)]/40 bg-[var(--color-error,#DC2626)]/10 p-3 text-[12px]"
          style={{ color: "var(--color-error, #DC2626)" }}
          data-testid="smart-viewer-mermaid-error"
        >
          Mermaid failed to render: {error}
        </div>
      )}
      <div ref={containerRef} data-testid="smart-viewer-mermaid-svg" />
    </div>
  );
}
