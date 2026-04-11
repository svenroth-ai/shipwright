import { useEffect, useRef, useState } from 'react';

let mermaidModule: typeof import('mermaid') | null = null;
let mermaidId = 0;

interface MermaidBlockProps {
  code: string;
}

export function MermaidBlock({ code }: MermaidBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        if (!mermaidModule) {
          mermaidModule = await import('mermaid');
          mermaidModule.default.initialize({ startOnLoad: false, theme: 'neutral' });
        }

        const id = `mermaid-${++mermaidId}`;
        const { svg } = await mermaidModule.default.render(id, code);

        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to render diagram');
        }
      }
    }

    render();
    return () => { cancelled = true; };
  }, [code]);

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded p-3">
        <p className="text-xs text-red-600 mb-1">Mermaid render error</p>
        <pre className="text-xs text-gray-600 whitespace-pre-wrap">{code}</pre>
      </div>
    );
  }

  return <div ref={containerRef} className="overflow-x-auto" />;
}
