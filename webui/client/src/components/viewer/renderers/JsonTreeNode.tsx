import { useState } from 'react';
import { ChevronRight } from 'lucide-react';

interface JsonTreeNodeProps {
  name: string;
  value: unknown;
  depth: number;
  defaultExpanded: boolean;
}

export function JsonTreeNode({ name, value, depth, defaultExpanded }: JsonTreeNodeProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  if (value === null) {
    return (
      <div style={{ paddingLeft: depth * 16 }} className="flex items-center gap-1 py-0.5 text-xs font-mono">
        <span className="text-gray-500">{name}:</span>
        <span className="text-gray-400 italic">null</span>
      </div>
    );
  }

  if (typeof value === 'object' && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div>
        <button
          style={{ paddingLeft: depth * 16 }}
          className="flex items-center gap-1 py-0.5 text-xs font-mono w-full text-left hover:bg-gray-50"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight size={12} className={`text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} />
          <span className="text-gray-500">{name}:</span>
          {!expanded && <span className="text-gray-400">{`{${entries.length} keys}`}</span>}
        </button>
        {expanded && entries.map(([k, v]) => (
          <JsonTreeNode key={k} name={k} value={v} depth={depth + 1} defaultExpanded={false} />
        ))}
      </div>
    );
  }

  if (Array.isArray(value)) {
    return (
      <div>
        <button
          style={{ paddingLeft: depth * 16 }}
          className="flex items-center gap-1 py-0.5 text-xs font-mono w-full text-left hover:bg-gray-50"
          onClick={() => setExpanded(!expanded)}
        >
          <ChevronRight size={12} className={`text-gray-400 transition-transform ${expanded ? 'rotate-90' : ''}`} />
          <span className="text-gray-500">{name}:</span>
          {!expanded && <span className="text-gray-400">{`[${value.length} items]`}</span>}
        </button>
        {expanded && value.map((v, i) => (
          <JsonTreeNode key={i} name={String(i)} value={v} depth={depth + 1} defaultExpanded={false} />
        ))}
      </div>
    );
  }

  const colorClass =
    typeof value === 'string' ? 'text-green-600' :
    typeof value === 'number' ? 'text-blue-600' :
    typeof value === 'boolean' ? 'text-purple-600' :
    'text-gray-600';

  return (
    <div style={{ paddingLeft: depth * 16 }} className="flex items-center gap-1 py-0.5 text-xs font-mono">
      <span className="text-gray-500">{name}:</span>
      <span className={colorClass}>{JSON.stringify(value)}</span>
    </div>
  );
}
