import { useMemo } from 'react';
import type { RendererProps } from '../../../types/viewer';
import { JsonTreeNode } from './JsonTreeNode';

export function JsonTreeRenderer({ content }: RendererProps) {
  const parsed = useMemo(() => {
    try {
      return { data: JSON.parse(content) as unknown, error: null };
    } catch (e) {
      return { data: null, error: e instanceof Error ? e.message : 'Invalid JSON' };
    }
  }, [content]);

  if (parsed.error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-500 mb-2">JSON parse error: {parsed.error}</p>
        <pre className="text-xs bg-gray-50 p-3 rounded overflow-auto max-h-[300px]">{content}</pre>
      </div>
    );
  }

  return (
    <div className="p-4 overflow-auto h-full" data-testid="json-tree">
      <JsonTreeNode name="root" value={parsed.data} depth={0} defaultExpanded />
    </div>
  );
}
